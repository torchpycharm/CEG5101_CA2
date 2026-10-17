#!/usr/bin/env python3
"""
CEG5101 CA2 - Task 3 / Task 4 numbers for one experiment run.

Reads the output of run_experiment.py and writes summary.md into the run
directory (also printed):
  * Task 3: base cost, peak load and peak dynamic cost of each loaded link
  * Task 4: items a-f for every scenario

Usage:
    python3 summarize_run.py results/run1
"""

import os
import sys

from run_data import Run, ip_of, ping_loss_per_second

LEGIT = ('10.0.0.1', '10.0.0.6')
BEFORE = 10.0     # s before a scenario used as "before"
# "after" window: past the ~8 s release delay, and still inside the iperf3 run
# of the last scenario in run1
AFTER_FROM, AFTER_TO = 10.0, 16.0


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else float('nan')


def window(rows, t_from, t_to, key=lambda r: r[0]):
    return [r for r in rows if t_from <= key(r) < t_to]


def path_at(paths, t):
    best = None
    for tp, p in paths:
        if tp <= t:
            best = p
    return best


def distinct(seq):
    out = []
    for x in seq:
        if not out or out[-1] != x:
            out.append(x)
    return out


def traffic_stats(iperf, ping_loss, t_from, t_to):
    ip = [r for r in iperf if t_from <= r[0] < t_to]
    lost = sum(r[3] for r in ip)
    total = sum(r[4] for r in ip)
    pl = window(ping_loss, t_from, t_to)
    return {
        'thr': mean(r[2] for r in ip),
        'thr_min': min((r[2] for r in ip), default=float('nan')),
        'udp_loss': 100.0 * lost / total if total else float('nan'),
        'ping_loss': mean(r[1] for r in pl),
        'ping_loss_peak': max((r[1] for r in pl), default=float('nan')),
        'ping_dead_s': sum(1 for r in pl if r[1] >= 100.0),
    }


def fmt(x, spec='%.2f'):
    return '-' if x != x else spec % x


def summarize(run_dir):
    run = Run(run_dir)
    costs = run.link_costs()
    events = run.events()
    iperf = run.iperf()
    replies, lost = run.ping()
    ping_loss = ping_loss_per_second(replies, lost, 0, run.t_end)
    paths = run.dataplane_path()
    legit = '%s->%s' % LEGIT

    lines = ['# Run summary: %s' % os.path.basename(os.path.abspath(run_dir)), '']
    lines.append('Legitimate flow: h1 -> h6, UDP %s; time 0 = start of the baseline phase.'
                 % run.timeline['args']['rate'])
    lines.append('')

    # ---------------- Task 3 ----------------
    lines += ['## Task 3 - dynamic cost of the loaded links', '',
              '| Scenario | Link | C0 | Peak utilisation | Peak cost | Peak normalised cost | '
              'Cost 10-16 s after |',
              '|---|---|---|---|---|---|---|']
    for sc in run.scenarios:
        rows = costs.get(sc['link']) or costs.get('-'.join(reversed(sc['link'].split('-'))), [])
        during = window(rows, sc['start'], sc['end'] + 4)
        after = window(rows, sc['end'] + AFTER_FROM, sc['end'] + AFTER_TO)
        base = rows[0][3] if rows else float('nan')
        lines.append('| %s | %s | %s | %s | %s | %s | %s |' % (
            sc['name'], sc['link'], fmt(base, '%.0f'),
            fmt(max((r[1] for r in during), default=float('nan')), '%.3f'),
            fmt(max((r[4] for r in during), default=float('nan'))),
            fmt(max((r[5] for r in during), default=float('nan'))),
            fmt(mean(r[4] for r in after))))
    lines.append('')

    # ---------------- Task 4 ----------------
    lines += ['## Task 4 - per scenario', '']
    for sc in run.scenarios:
        start, end = sc['start'], sc['end']
        src_ip = ip_of(sc['attacker'])
        dst_ip = ip_of(sc['victim'])
        lines += ['### Scenario %s: %s -> %s, link %s (%.0f-%.0f s)'
                  % (sc['name'], sc['attacker'], sc['victim'], sc['link'], start, end), '']

        # a. load and cost
        rows = costs.get(sc['link'], [])
        during = window(rows, start, end + 4)
        lines.append('- **a. Load / cost of %s**: utilisation peak %s, cost %s -> peak %s '
                     '(normalised %s)' % (
                         sc['link'], fmt(max((r[1] for r in during), default=float('nan')), '%.3f'),
                         fmt(rows[0][3] if rows else float('nan'), '%.0f'),
                         fmt(max((r[4] for r in during), default=float('nan'))),
                         fmt(max((r[5] for r in during), default=float('nan')))))

        # b. detection and blocking
        win_ev = window(events, start - 1, end + AFTER_TO)
        det = [(t, d) for t, e, d in win_ev if e == 'ANOMALY' and d.startswith(src_ip + ' ')]
        blocked = [d.split(' ')[0] for t, e, d in win_ev if e == 'BLOCK']
        unblock = [(t, d.split(' ')[0]) for t, e, d in win_ev if e == 'UNBLOCK']
        if det:
            t_det, d = det[0]
            lines.append('- **b. Detection**: %s flagged %.1f s after the start (%s); '
                         'IPs blocked in this scenario: %s'
                         % (src_ip, t_det - start, ' '.join(d.split(' ')[1:4]),
                            ', '.join(blocked) or '-'))
        else:
            lines.append('- **b. Detection**: %s not flagged in this window' % src_ip)

        # c. rerouting
        reroutes = [(t, d) for t, e, d in win_ev if e == 'REROUTE' and d.startswith(legit + ' ')]
        p_before = path_at(paths, start - 1)
        p_during = distinct(p for t, p in window(paths, start, end))
        if reroutes:
            lines.append('- **c. Rerouted**: yes - %s' % '; '.join(
                '%.1f s: %s' % (t - start, d.split(' ', 1)[1].split(' [')[0])
                for t, d in reroutes))
        else:
            lines.append('- **c. Rerouted**: no (h1->h6 path did not use a penalised link '
                         'or no cheaper path existed)')

        # d. path, loss and throughput before / during
        b = traffic_stats(iperf, ping_loss, start - BEFORE, start)
        dg = traffic_stats(iperf, ping_loss, start, end)
        lines.append('- **d. h1->h6 path**: before `%s`; during %s'
                     % (p_before, ', '.join('`%s`' % p for p in p_during)))
        lines.append('')
        lines.append('  | Phase | Throughput mean (Mbps) | Throughput min (Mbps) | UDP loss (%) '
                     '| Ping loss mean (%) | Ping loss peak (%) | Seconds with 100% ping loss |')
        lines.append('  |---|---|---|---|---|---|---|')
        a = traffic_stats(iperf, ping_loss, end + AFTER_FROM, end + AFTER_TO)
        for name, s in (('before (10 s)', b), ('during', dg), ('after (+10-16 s)', a)):
            lines.append('  | %s | %s | %s | %s | %s | %s | %d |' % (
                name, fmt(s['thr']), fmt(s['thr_min']), fmt(s['udp_loss']),
                fmt(s['ping_loss']), fmt(s['ping_loss_peak'], '%.0f'), s['ping_dead_s']))
        lines.append('')

        # e. connectivity
        lines.append('- **e. Connectivity**: UDP throughput never below %s Mbps during the '
                     'scenario; %d s with every ping lost'
                     % (fmt(dg['thr_min']), dg['ping_dead_s']))

        # f. recovery
        own = [t for t, ip in unblock if ip == src_ip]
        cost_back = next((r[0] for r in rows if r[0] > end and r[2] == 0), None)
        path_back = next((t for t, p in paths if t > end and p == p_before), None)
        lines.append('- **f. Recovery**: %s released %s; anomaly flag on %s cleared %s; '
                     'h1->h6 back on `%s` %s' % (
                         src_ip, '%.1f s after the traffic stopped' % (own[0] - end) if own else '-',
                         sc['link'],
                         '%.1f s after' % (cost_back - end) if cost_back else '-',
                         p_before,
                         '%.1f s after' % (path_back - end) if path_back is not None and
                         path_back > end + 0.5 else '(path unchanged)'))
        lines.append('')

    text = '\n'.join(lines)
    with open(os.path.join(run_dir, 'summary.md'), 'w') as f:
        f.write(text + '\n')
    return text


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(summarize(sys.argv[1]))
