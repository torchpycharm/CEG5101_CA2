"""
CEG5101 CA2 - loaders for the files written by run_experiment.py.
Shared by summarize_run.py and plot_results.py. All times are seconds since t0
(the start of the baseline phase).
"""

import csv
import json
import os
import re

UNITS = {'bits/sec': 1e-6, 'Kbits/sec': 1e-3, 'Mbits/sec': 1.0, 'Gbits/sec': 1e3}
IPERF_LINE = re.compile(
    r'\]\s+([\d.]+)-([\d.]+)\s+sec\s+[\d.]+\s+\w?Bytes\s+([\d.]+)\s+(\w*bits/sec)'
    r'\s+[\d.]+\s+ms\s+(\d+)/\s*(\d+)\s+\(')
PING_LINE = re.compile(r'^\[([\d.]+)\].*icmp_seq=(\d+).*time=([\d.]+) ms')


class Run(object):
    def __init__(self, run_dir):
        self.dir = run_dir
        with open(self._p('timeline.json')) as f:
            self.timeline = json.load(f)
        self.t0 = self.timeline['t0']
        self.t_end = self.timeline['t_end'] - self.t0
        self.scenarios = [dict(s, start=s['start'] - self.t0, end=s['end'] - self.t0)
                          for s in self.timeline['scenarios']]

    def _p(self, *parts):
        return os.path.join(self.dir, *parts)

    def _rel(self, stamp):
        return float(stamp) - self.t0

    # ---------------- controller logs ----------------
    def link_costs(self):
        """{link: [(t, utilisation, anomaly, base_cost, cost, norm_cost), ...]}"""
        out = {}
        with open(self._p('controller', 'link_costs.csv')) as f:
            for r in csv.DictReader(f):
                t = self._rel(r['time'])
                if t > self.t_end:
                    continue
                out.setdefault(r['link'], []).append((
                    t, float(r['utilisation']), int(r['anomaly']), float(r['base_cost']),
                    float(r['cost']), float(r['norm_cost'])))
        return out

    def events(self):
        """[(t, event, detail)] up to the end of the experiment"""
        out = []
        with open(self._p('controller', 'events.csv')) as f:
            for r in csv.DictReader(f):
                t = self._rel(r['time'])
                if t <= self.t_end:
                    out.append((t, r['event'], r['detail']))
        return out

    # ---------------- measurements ----------------
    def iperf(self):
        """[(t_start, t_end, throughput_mbps, lost, total)] from the iperf3 server (receiver)"""
        t_offset = self.timeline['t_iperf'] - self.t0
        out = []
        with open(self._p('iperf_server.txt')) as f:
            for line in f:
                m = IPERF_LINE.search(line)
                if not m:
                    continue
                a, b = float(m.group(1)), float(m.group(2))
                if b - a > 1.5:          # final summary line
                    continue
                mbps = float(m.group(3)) * UNITS[m.group(4)]
                out.append((a + t_offset, b + t_offset, mbps, int(m.group(5)), int(m.group(6))))
        return out

    def ping(self):
        """(replies, lost_send_times): replies = [(send_t, rtt_ms)] for h1 -> h6 (0.1 s interval)"""
        replies = {}
        with open(self._p('ping_h1_h6.txt')) as f:
            for line in f:
                m = PING_LINE.search(line)
                if m:
                    recv, seq, rtt = float(m.group(1)), int(m.group(2)), float(m.group(3))
                    replies[seq] = (self._rel(recv) - rtt / 1000.0, rtt)
        if not replies:
            return [], []
        seqs = sorted(replies)
        # send time of a lost probe: interpolate between its received neighbours
        lost = []
        for lo, hi in zip(seqs, seqs[1:]):
            for s in range(lo + 1, hi):
                t_lo, t_hi = replies[lo][0], replies[hi][0]
                lost.append(t_lo + (t_hi - t_lo) * (s - lo) / float(hi - lo))
        return [replies[s] for s in seqs], lost

    def dataplane_path(self):
        """[(t, path)] - the h1 -> h6 path traced from the installed rules once per second"""
        out = []
        with open(self._p('dataplane_path.csv')) as f:
            for r in csv.DictReader(f):
                t = self._rel(r['time'])
                if t <= self.t_end:
                    out.append((t, r['path']))
        return out


def ping_loss_per_second(replies, lost, t_from, t_to):
    """[(t_bin_start, loss_percent)] in 1 s bins"""
    bins = {}
    for t, _rtt in replies:
        bins.setdefault(int(t // 1), [0, 0])[0] += 1
    for t in lost:
        bins.setdefault(int(t // 1), [0, 0])[1] += 1
    out = []
    for b in range(int(t_from), int(t_to)):
        ok, bad = bins.get(b, (0, 0))
        if ok + bad:
            out.append((float(b), 100.0 * bad / (ok + bad)))
    return out


def ip_of(host):
    return '10.0.0.%d' % int(host[1:])
