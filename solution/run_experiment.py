#!/usr/bin/env python3
"""
CEG5101 CA2 - experiment driver (Task 4 / Task 5)

Starts the controller and the mesh topology, keeps a legitimate h1->h6 flow
running, and injects the three ICMP floods one after another:
    a) h2 -> h3   (link s2-s3)
    b) h2 -> h6   (link s2-s6)
    c) h5 -> h6   (link s5-s6)
Everything needed for the plots is written to the output directory.

Usage:
    sudo python3 run_experiment.py --out results/run1
"""

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'ceg_code'))

from mininet.net import Mininet                      # noqa: E402
from mininet.node import RemoteController, OVSKernelSwitch   # noqa: E402
from mininet.link import TCLink                      # noqa: E402
from mininet.log import setLogLevel, info            # noqa: E402
from ceg_mesh_topo import MeshTopo                   # noqa: E402

SCENARIOS = {
    'a': {'attacker': 'h2', 'victim': 'h3', 'link': 's2-s3'},
    'b': {'attacker': 'h2', 'victim': 'h6', 'link': 's2-s6'},
    'c': {'attacker': 'h5', 'victim': 'h6', 'link': 's5-s6'},
}
# low-rate pings that give every source a "normal" baseline
BACKGROUND_PINGS = [('h2', 'h3'), ('h2', 'h6'), ('h5', 'h6'), ('h3', 'h4'), ('h4', 'h1')]
LEGIT_SRC, LEGIT_DST = 'h1', 'h6'
EXPECTED_LINKS = 11


def wait_for_topology(log_path, timeout=60):
    """Block until the controller has discovered every switch-to-switch link"""
    pattern = re.compile(r'Topology: \d+ switches, (\d+) links')
    deadline = time.time() + timeout
    while time.time() < deadline:
        with open(log_path) as f:
            found = [int(n) for n in pattern.findall(f.read())]
        if found and found[-1] >= EXPECTED_LINKS:
            return True
        time.sleep(0.5)
    return False


def port_map(net):
    """{switch: {port_no: name of the node behind that port}}"""
    ports = {}
    for switch in net.switches:
        ports[switch.name] = {}
        for intf in switch.intfList():
            if not intf.link:
                continue
            other = intf.link.intf1 if intf.link.intf2 is intf else intf.link.intf2
            ports[switch.name][switch.ports[intf]] = other.node.name
    return ports


def trace_path(ports, src_ip, dst_ip, first_switch):
    """Follow the installed OpenFlow rules of one flow through the data plane"""
    path, switch = [first_switch], first_switch
    for _ in range(10):
        out = subprocess.run(
            ['ovs-ofctl', '-O', 'OpenFlow13', 'dump-flows', switch,
             'ip,nw_src=%s,nw_dst=%s' % (src_ip, dst_ip)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True).stdout
        match = re.search(r'priority=10,.*actions=output:(\d+)', out)
        if not match:
            path.append('?')
            break
        nxt = ports[switch].get(int(match.group(1)), '?')
        path.append(nxt)
        if not nxt.startswith('s'):
            break
        switch = nxt
    return '>'.join(path)


class Sampler(threading.Thread):
    """Once per second: interface counters and the data-plane path of the legit flow"""

    def __init__(self, net, out_dir, src_ip, dst_ip, first_switch):
        super(Sampler, self).__init__(daemon=True)
        self.ports = port_map(net)
        self.ifaces = sorted(intf.name for s in net.switches for intf in s.intfList()
                             if intf.link)
        self.out_dir = out_dir
        self.flow = (src_ip, dst_ip, first_switch)
        self.stop_flag = threading.Event()

    @staticmethod
    def _read(iface, counter):
        try:
            with open('/sys/class/net/%s/statistics/%s' % (iface, counter)) as f:
                return f.read().strip()
        except IOError:
            return ''

    def run(self):
        with open(os.path.join(self.out_dir, 'ifstats.csv'), 'w') as stats, \
                open(os.path.join(self.out_dir, 'dataplane_path.csv'), 'w') as paths:
            stats.write('time,iface,rx_bytes,tx_bytes,rx_packets,tx_packets\n')
            paths.write('time,path\n')
            while not self.stop_flag.is_set():
                now = time.time()
                for iface in self.ifaces:
                    stats.write('%.3f,%s,%s\n' % (now, iface, ','.join(
                        self._read(iface, c) for c in
                        ('rx_bytes', 'tx_bytes', 'rx_packets', 'tx_packets'))))
                paths.write('%.3f,%s\n' % (now, trace_path(self.ports, *self.flow)))
                stats.flush()
                paths.flush()
                self.stop_flag.wait(max(0.0, 1.0 - (time.time() - now)))


def dump_flows(net, out_dir, label):
    with open(os.path.join(out_dir, 'flows_%s.txt' % label), 'w') as f:
        f.write('# %s  t=%.3f\n' % (label, time.time()))
        for switch in net.switches:
            f.write('== %s\n' % switch.name)
            f.write(subprocess.run(
                ['ovs-ofctl', '-O', 'OpenFlow13', 'dump-flows', switch.name],
                stdout=subprocess.PIPE, universal_newlines=True).stdout)


def open_monitors(out_dir, ryu_log):
    """Pop up xterm windows (shown on the Windows desktop through WSLg) with the
    controller output and the live dashboard. They stay open after the run."""
    env = dict(os.environ)
    env.setdefault('DISPLAY', ':0')          # plain `sudo` drops DISPLAY
    windows = [
        ('CA2 controller', '-geometry 120x45+0+0', 'tail -n +1 -f %s' % ryu_log),
        ('CA2 live view', '-geometry 100x45-0+0',
         '%s %s --run %s' % (sys.executable, os.path.join(HERE, 'live_view.py'), out_dir)),
    ]
    for title, geometry, cmd in windows:
        try:
            subprocess.Popen(['xterm', '-T', title] + geometry.split() +
                             ['-fa', 'Monospace', '-fs', '10', '-e', 'bash', '-c', cmd],
                             env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as err:
            print('could not open %s window: %s' % (title, err))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', default=os.path.join(HERE, 'results', time.strftime('run_%Y%m%d_%H%M%S')))
    parser.add_argument('--controller', default=os.path.join(HERE, 'anomaly_aware_controller.py'))
    parser.add_argument('--scenarios', default='a,b,c', help='comma separated subset of a,b,c')
    parser.add_argument('--baseline', type=int, default=30, help='seconds before the first attack')
    parser.add_argument('--attack', type=int, default=30, help='seconds each flood lasts')
    parser.add_argument('--recover', type=int, default=30, help='seconds after each flood')
    parser.add_argument('--rate', default='5M', help='rate of the legitimate UDP flow')
    parser.add_argument('--cost-mode', default='controller', choices=['controller', 'delay'])
    parser.add_argument('--alpha', default=None, help='override COST_ALPHA')
    parser.add_argument('--beta', default=None, help='override COST_BETA')
    parser.add_argument('--monitor', action='store_true',
                        help='open xterm windows with the controller output and live_view.py')
    args = parser.parse_args()

    if os.geteuid() != 0:
        sys.exit('run with sudo')
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    scenarios = [s for s in args.scenarios.split(',') if s]
    total = args.baseline + len(scenarios) * (args.attack + args.recover)

    subprocess.run(['mn', '-c'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    setLogLevel('warning')

    # ---- controller ----
    env = dict(os.environ, CA2_LOG_DIR=os.path.join(out_dir, 'controller'),
               CA2_COST_MODE=args.cost_mode)
    if args.alpha:
        env['CA2_ALPHA'] = args.alpha
    if args.beta:
        env['CA2_BETA'] = args.beta
    ryu_log = os.path.join(out_dir, 'controller.log')
    ryu = subprocess.Popen(['ryu-manager', '--observe-links', args.controller],
                           stdout=open(ryu_log, 'w'), stderr=subprocess.STDOUT, env=env)
    if args.monitor:
        open_monitors(out_dir, ryu_log)
    time.sleep(3)

    # ---- topology ----
    net = Mininet(topo=MeshTopo(), controller=None, switch=OVSKernelSwitch,
                  link=TCLink, autoSetMacs=True)
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)
    net.start()
    procs, files = [], []

    def run_on(host, cmd, logname):
        f = open(os.path.join(out_dir, logname), 'w')
        files.append(f)
        proc = net.get(host).popen(cmd, shell=True, stdout=f, stderr=subprocess.STDOUT)
        procs.append(proc)
        return proc

    timeline = {'scenarios': [], 'args': vars(args)}
    sampler = None
    try:
        print('waiting for link discovery ...')
        if not wait_for_topology(ryu_log):
            raise RuntimeError('controller did not discover %d links' % EXPECTED_LINKS)
        time.sleep(5)
        net.pingAll(timeout=1)
        loss = net.pingAll(timeout=1)
        print('pingall loss: %.0f%%' % loss)
        timeline['pingall_loss'] = loss

        src, dst = net.get(LEGIT_SRC), net.get(LEGIT_DST)
        sampler = Sampler(net, out_dir, src.IP(), dst.IP(), 's1')
        sampler.start()

        # ---- legitimate traffic + normal background traffic ----
        run_on(LEGIT_DST, 'iperf3 -s -p 5201 -i 1 --forceflush', 'iperf_server.txt')
        time.sleep(1)
        timeline['t_iperf'] = time.time()
        run_on(LEGIT_SRC, 'iperf3 -c %s -p 5201 -u -b %s -l 1200 -t %d -i 1 --forceflush'
               % (dst.IP(), args.rate, total + 30), 'iperf_client.txt')   # outlasts the last recovery
        timeline['t_ping'] = time.time()
        run_on(LEGIT_SRC, 'ping -D -i 0.1 -W 1 %s' % dst.IP(), 'ping_h1_h6.txt')
        for a, b in BACKGROUND_PINGS:
            run_on(a, 'ping -i 1 %s' % net.get(b).IP(), 'bgping_%s_%s.txt' % (a, b))

        t0 = time.time()
        timeline['t0'] = t0
        print('t=0    baseline (%d s)' % args.baseline)
        time.sleep(args.baseline)
        dump_flows(net, out_dir, 'before')

        # ---- the three floods, one after another ----
        for name in scenarios:
            sc = SCENARIOS[name]
            victim_ip = net.get(sc['victim']).IP()
            start = time.time()
            print('t=%-4.0f scenario %s: %s floods %s (link %s)' % (
                start - t0, name, sc['attacker'], sc['victim'], sc['link']))
            run_on(sc['attacker'], 'timeout -s INT %d hping3 --icmp --flood %s'
                   % (args.attack, victim_ip), 'hping3_%s.txt' % name)
            time.sleep(args.attack / 2.0)
            dump_flows(net, out_dir, 'during_%s' % name)
            time.sleep(args.attack / 2.0)
            end = time.time()
            print('t=%-4.0f flood stopped, recovering (%d s)' % (end - t0, args.recover))
            time.sleep(args.recover)
            dump_flows(net, out_dir, 'after_%s' % name)
            timeline['scenarios'].append(dict(sc, name=name, start=start, end=end))

        timeline['t_end'] = time.time()
    finally:
        with open(os.path.join(out_dir, 'timeline.json'), 'w') as f:
            json.dump(timeline, f, indent=2)
        if sampler:
            sampler.stop_flag.set()
            sampler.join(timeout=3)
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
        time.sleep(1)
        subprocess.run('pkill -f "hping3 --icmp"; pkill -f "iperf3 -[sc]"; pkill -f "ping -D"',
                       shell=True)
        for f in files:
            f.close()
        net.stop()
        ryu.terminate()
        ryu.wait(timeout=10)
        owner = os.environ.get('SUDO_UID')
        if owner:
            subprocess.run(['chown', '-R', '%s:%s' % (owner, os.environ.get('SUDO_GID', owner)),
                            os.path.dirname(out_dir)])
    print('results in', out_dir)


if __name__ == '__main__':
    main()
