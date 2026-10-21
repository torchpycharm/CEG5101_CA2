#!/usr/bin/env python3
"""
CEG5101 CA2 - live dashboard for the Task 4 demo

Refreshes once per second and shows, from the files the controller and the
experiment write while they run:
    h1->h6 path (controller and data plane), path cost
    load / anomaly flag / cost of the links that matter for h1->h6
    rate, baseline and state of every source
    the latest ANOMALY / BLOCK / REROUTE / UNBLOCK events
    h1->h6 throughput, UDP loss and RTT

Usage:
    # next to run_experiment.py (third terminal):
    python3 live_view.py --run results/demo

    # manual demo in the Mininet CLI (controller started in solution/):
    sudo python3 live_view.py --logs ca2_logs --iperf /tmp/iperf_h6.txt --ping /tmp/ping_h1h6.txt --trace

    # replay a finished run, 5x speed (fallback if the live demo fails):
    python3 live_view.py --run results/run4 --replay 5
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time

LINKS = ['s1-s2', 's2-s6', 's1-s5', 's5-s6', 's2-s3', 's2-s5', 's3-s6']
SRC, DST = '10.0.0.1', '10.0.0.6'
NAMES = {'10.0.0.%d' % i: 'h%d' % i for i in range(1, 7)}
# switch port -> neighbour, in the addLink order of ceg_mesh_topo.py
PORTS = {'s1': {1: 'h1', 2: 's2', 3: 's4', 4: 's5'},
         's2': {1: 'h2', 2: 's1', 3: 's3', 4: 's5', 5: 's4', 6: 's6'},
         's3': {1: 'h3', 2: 's2', 3: 's6', 4: 's5'},
         's4': {1: 'h4', 2: 's5', 3: 's1', 4: 's2'},
         's5': {1: 'h5', 2: 's4', 3: 's6', 4: 's2', 5: 's1', 6: 's3'},
         's6': {1: 'h6', 2: 's5', 3: 's3', 4: 's2'}}
IPERF = re.compile(r'\]\s+([\d.]+)-([\d.]+)\s+sec.*?([\d.]+)\s+(\w?)bits/sec\s+[\d.]+\s+ms\s+(\d+)/\s*(\d+)')
PING = re.compile(r'^\[([\d.]+)\].*icmp_seq=(\d+).*time=([\d.]+) ms')

RED, GREEN, YELLOW, BOLD, DIM, RESET = '\033[31m', '\033[32m', '\033[33m', '\033[1m', '\033[2m', '\033[0m'


def read_csv(path, until):
    if not path or not os.path.exists(path):
        return []
    with open(path) as f:
        return [r for r in csv.DictReader(f) if r.get('time') and float(r['time']) <= until]


def latest(rows):
    """rows of the newest timestamp"""
    if not rows:
        return []
    t = rows[-1]['time']
    return [r for r in rows if r['time'] == t]


def iperf_last(path, t_start, until):
    if not path or not os.path.exists(path):
        return None
    last = None
    with open(path) as f:
        for line in f:
            m = IPERF.search(line)
            if not m or float(m.group(2)) - float(m.group(1)) > 1.5:
                continue
            if t_start is not None and t_start + float(m.group(2)) > until:
                break
            scale = {'': 1e-6, 'K': 1e-3, 'M': 1.0, 'G': 1e3}[m.group(4)]
            last = (float(m.group(2)), float(m.group(3)) * scale, int(m.group(5)), int(m.group(6)))
    return last


def ping_window(path, until, window=5.0):
    """(last rtt, replies, lost) over the last `window` seconds"""
    if not path or not os.path.exists(path):
        return None
    pts = []
    with open(path) as f:
        for line in f:
            m = PING.search(line)
            if m and float(m.group(1)) <= until:
                pts.append((float(m.group(1)), int(m.group(2)), float(m.group(3))))
    if not pts:
        return None
    recent = [p for p in pts if p[0] > pts[-1][0] - window]
    lost = (recent[-1][1] - recent[0][1] + 1) - len(recent)
    return pts[-1][2], len(recent), lost


def trace_dataplane():
    """follow the installed h1->h6 rules through the switches (needs root)"""
    hops, sw = ['s1'], 's1'
    for _ in range(8):
        out = subprocess.run(['ovs-ofctl', '-O', 'OpenFlow13', 'dump-flows', sw,
                              'ip,nw_src=%s,nw_dst=%s' % (SRC, DST)],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             universal_newlines=True).stdout
        m = re.search(r'priority=10,.*actions=output:(\d+)', out)
        if not m:
            return '>'.join(hops + ['?'])
        nxt = PORTS[sw].get(int(m.group(1)), '?')
        hops.append(nxt)
        if not nxt.startswith('s'):
            break
        sw = nxt
    return '>'.join(hops)


def frame(a, until, t0, t_iperf, timeline):
    out = []
    clock = time.strftime('%H:%M:%S', time.localtime(until))
    rel = ' t=%.0f s' % (until - t0) if t0 else ''
    phase = ''
    for sc in timeline:
        if sc['start'] <= until <= sc['end']:
            phase = '%s  ATTACK %s: %s -> %s on %s%s' % (RED, sc['name'], sc['attacker'], sc['victim'], sc['link'], RESET)
        elif sc['end'] < until <= sc['end'] + 30:
            phase = '%s  recovery after %s%s' % (GREEN, sc['name'], RESET)
    out.append('%sCA2 live view%s  %s%s%s' % (BOLD, RESET, clock, rel, phase))
    out.append('')

    # ---- h1 -> h6 path ----
    paths = [r for r in read_csv(os.path.join(a.logs, 'paths.csv'), until) if r['src'] == SRC and r['dst'] == DST]
    ctrl = '%s  (cost %s)' % (paths[-1]['path'], paths[-1]['cost']) if paths else '(no flow yet)'
    dp = None
    if a.dataplane and os.path.exists(a.dataplane):
        rows = read_csv(a.dataplane, until)
        dp = rows[-1]['path'] if rows else None
    elif a.trace:
        dp = trace_dataplane()
    out.append('%sh1 -> h6 path%s  controller: %s%s%s' % (BOLD, RESET, YELLOW, ctrl, RESET))
    if dp:
        out.append('               data plane: %s' % dp)

    # ---- h1 -> h6 performance ----
    ip = iperf_last(a.iperf, t_iperf, until)
    pg = ping_window(a.ping, until)
    perf = []
    if ip:
        loss = 100.0 * ip[2] / ip[3] if ip[3] else 0.0
        colour = RED if loss > 0 else GREEN
        perf.append('UDP %.2f Mbit/s, loss %s%d/%d (%.1f %%)%s' % (ip[1], colour, ip[2], ip[3], loss, RESET))
    if pg:
        colour = RED if pg[2] > 0 else GREEN
        perf.append('ping RTT %.1f ms, last 5 s lost %s%d/%d%s' % (pg[0], colour, pg[2], pg[1] + pg[2], RESET))
    out.append('               ' + ('   |   '.join(perf) if perf else '(no iperf / ping data)'))
    out.append('')

    # ---- links ----
    out.append('%s%-7s %9s %9s %6s %3s %5s %8s %6s%s' % (BOLD, 'link', 'fwd Mb/s', 'rev Mb/s', 'util', 'A', 'C0', 'cost', 'C/C0', RESET))
    rows = {r['link']: r for r in latest(read_csv(os.path.join(a.logs, 'link_costs.csv'), until))}
    for name in LINKS:
        r = rows.get(name)
        if not r:
            continue
        colour = RED if r['anomaly'] == '1' else (YELLOW if float(r['norm_cost']) > 1.05 else '')
        out.append('%s%-7s %9s %9s %6s %3s %5s %8s %6s%s' % (
            colour, name, r['rate_fwd_mbps'], r['rate_rev_mbps'], r['utilisation'], r['anomaly'],
            r['base_cost'], r['cost'], r['norm_cost'], RESET if colour else ''))
    out.append('')

    # ---- sources ----
    out.append('%s%-4s %10s %10s %10s  %s%s' % (BOLD, 'src', 'pps', 'baseline', 'threshold', 'state', RESET))
    for r in latest(read_csv(os.path.join(a.logs, 'sources.csv'), until)):
        colour = RED if r['state'] == 'blocked' else ''
        out.append('%s%-4s %10s %10s %10s  %s%s' % (colour, NAMES.get(r['ip'], r['ip']), r['pps'], r['baseline_pps'],
                                                   r['threshold_pps'], r['state'], RESET if colour else ''))
    out.append('')

    # ---- events ----
    out.append('%sevents%s' % (BOLD, RESET))
    events = [r for r in read_csv(os.path.join(a.logs, 'events.csv'), until) if r['event'] != 'LINK_DOWN']
    for r in events[-a.events:]:
        colour = {'ANOMALY': RED, 'BLOCK': RED, 'UNBLOCK': GREEN, 'REROUTE': YELLOW}.get(r['event'], '')
        stamp = ('%6.1f s' % (float(r['time']) - t0)) if t0 else time.strftime('%H:%M:%S', time.localtime(float(r['time'])))
        out.append('%s %s%-8s%s %s' % (stamp, colour, r['event'], RESET, r['detail'][:100]))
    if not events:
        out.append('%s(none yet)%s' % (DIM, RESET))
    return '\n'.join(out)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--run', help='result directory of run_experiment.py (sets the paths below)')
    p.add_argument('--logs', default='ca2_logs', help='controller CSV directory')
    p.add_argument('--iperf', help='iperf3 server output of h6')
    p.add_argument('--ping', help='ping -D output of h1 -> h6')
    p.add_argument('--dataplane', help='dataplane_path.csv')
    p.add_argument('--trace', action='store_true', help='trace the h1->h6 rules with ovs-ofctl (needs sudo)')
    p.add_argument('--events', type=int, default=10, help='number of events shown')
    p.add_argument('--replay', type=float, help='replay a finished --run at this speed')
    p.add_argument('--once', type=float, help='print a single frame at this time (s after t0) of a finished --run')
    a = p.parse_args()

    t0, t_iperf, timeline = None, None, []
    if a.run:
        a.logs = os.path.join(a.run, 'controller')
        a.iperf = a.iperf or os.path.join(a.run, 'iperf_server.txt')
        a.ping = a.ping or os.path.join(a.run, 'ping_h1_h6.txt')
        a.dataplane = a.dataplane or os.path.join(a.run, 'dataplane_path.csv')
        tl_path = os.path.join(a.run, 'timeline.json')
        if os.path.exists(tl_path):          # written only when the run has finished
            with open(tl_path) as f:
                tl = json.load(f)
            t0, t_iperf, timeline = tl.get('t0'), tl.get('t_iperf'), tl.get('scenarios', [])

    if a.once is not None:
        print(frame(a, t0 + a.once, t0, t_iperf, timeline))
        return
    try:
        start = time.time()
        while True:
            now = time.time()
            until = t0 + (now - start) * a.replay if a.replay and t0 else now
            text = frame(a, until, t0 if a.replay else None, t_iperf if a.replay else None,
                         timeline if a.replay else [])
            sys.stdout.write('\033[2J\033[H' + text + '\n')
            sys.stdout.flush()
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
