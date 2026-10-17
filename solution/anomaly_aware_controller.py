"""
CEG5101 CA2 - Anomaly-aware Routing and Blocking Controller

Integrates the two reference controllers:
  * resilient_controller.py  -> topology discovery + Dijkstra routing
  * anomaly_detection.py     -> EMA traffic baseline + source blocking
and adds what both of them are missing:
  * a dynamic link cost   C_ij(t) = C0_ij + ALPHA * R_ij(t)/Rmax + BETA * A_ij(t)
  * rerouting of the installed flows whenever the costs change
  * recovery (cost reset + unblock) once the anomalous traffic stops

Run:
    ryu-manager --observe-links anomaly_aware_controller.py

Environment variables (all optional):
    CA2_LOG_DIR    directory for the CSV logs            (default ./ca2_logs)
    CA2_COST_MODE  "controller" = base costs of the provided resilient_controller.py
                   "delay"      = base costs = TCLink delay in ceg_mesh_topo.py
    CA2_ALPHA / CA2_BETA / CA2_POLL   override COST_ALPHA / COST_BETA / POLL_INTERVAL
"""

import csv
import heapq
import os
import time
from collections import namedtuple

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import (CONFIG_DISPATCHER, MAIN_DISPATCHER,
                                    DEAD_DISPATCHER, set_ev_cls)
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub
from ryu.lib.packet import packet, ethernet, ether_types, arp, ipv4
from ryu.topology import event
from ryu.topology.api import get_switch, get_link


# ----------------------------------------------------------------------
# Parameters
# ----------------------------------------------------------------------
POLL_INTERVAL = float(os.environ.get('CA2_POLL', 2.0))   # s between stats polls
STATS_WAIT = 0.5               # s to wait for the stats replies of one poll
TOPOLOGY_SETTLE = 3.0          # s without a new link before hosts are learned

# Anomaly detection (per source IP, measured at the host's access switch)
EMA_ALPHA = 0.3                # baseline = a*rate + (1-a)*baseline
THRESHOLD_MULT = 3.0           # anomalous if rate > 3 x baseline ...
MIN_ANOMALY_PPS = 1000.0       # ... and above this floor (a 5 Mbit/s UDP flow is ~430 pps)
WARMUP_SAMPLES = 3             # samples a source needs before it can be flagged
RECOVERY_POLLS = 3             # quiet polls before a blocked source is released
HEAVY_FLOW_SHARE = 0.2         # flows carrying >= 20% of an anomalous source mark their links

# Dynamic link cost  C = C0 + ALPHA * R/Rmax + BETA * A
COST_ALPHA = float(os.environ.get('CA2_ALPHA', 10.0))
COST_BETA = float(os.environ.get('CA2_BETA', 20.0))
LINK_CAPACITY_BPS = 40e6       # bw=40 on every TCLink of ceg_mesh_topo.py
LOAD_SMOOTHING = 0.5           # weight of the newest rate sample
REROUTE_MARGIN = 2.0           # a new path must be cheaper by this much (hysteresis)

# Base costs C0, keyed by (lower dpid, higher dpid)
# "controller": what resilient_controller.py actually uses on the mesh topology -
#               its predefined table where it applies, its default cost of 10 elsewhere.
CONTROLLER_COSTS = {(1, 2): 5, (2, 3): 10, (1, 4): 20, (2, 4): 8}
CONTROLLER_DEFAULT_COST = 10
# "delay": the TCLink delay (ms) of every link in ceg_mesh_topo.py
DELAY_COSTS = {(1, 2): 5, (2, 3): 10, (4, 5): 15, (5, 6): 20, (1, 4): 8, (2, 5): 12,
               (3, 6): 7, (1, 5): 18, (2, 4): 6, (2, 6): 14, (3, 5): 9}
COST_MODE = os.environ.get('CA2_COST_MODE', 'controller')

FWD_COOKIE = 0xCA20001         # forwarding rules installed by this app
DROP_COOKIE = 0xCA20002        # drop rules for blocked sources
ICMP_RATE_COOKIE = 0xCA20003   # typed echo counters on each source's access switch
FWD_PRIORITY = 10
ICMP_RATE_PRIORITY = FWD_PRIORITY + 1
DROP_PRIORITY = 5000
ICMPV4_PROTO = 1               # IPv4 protocol number for ICMP
ICMP_ECHO_REPLY = 0
ICMP_ECHO_REQUEST = 8

Host = namedtuple('Host', 'mac dpid port')


def sw(dpid):
    return 's%d' % dpid


def link_key(u, v):
    return (u, v) if u < v else (v, u)


class AnomalyAwareController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(AnomalyAwareController, self).__init__(*args, **kwargs)

        # --- topology (from resilient_controller.py, dpids kept as ints) ---
        self.datapaths = {}
        self.switch_ports = {}        # dpid -> set(port_no)
        self.link_port = {}           # (u, v) -> port on u that faces v
        self.down_ports = set()       # (dpid, port_no) reported link-down
        self.graph = {}               # u -> {v: current cost}
        self.last_topo_change = time.time()

        # --- hosts and installed flows ---
        self.hosts = {}               # ip -> Host(mac, dpid, port)
        self.flows = {}               # (src_ip, dst_ip) -> {'path': [dpid], 'rules': {dpid: out_port}}

        # --- traffic monitoring ---
        self.flow_sample = {}         # dpid -> {'time': t, 'fwd': typed counters, 'drop': {ip: pkts}}
        self.flow_pending = {}        # dpid -> sample being assembled from multipart replies
        self.flow_prev = {}           # dpid -> previous completed sample
        self.port_sample = {}         # dpid -> {'time': t, 'tx': {port: tx_bytes}}
        self.port_prev = {}
        self.link_rate = {}           # (u, v) directed -> smoothed bit/s

        # --- anomaly detection (from anomaly_detection.py) ---
        self.sources = {}             # ip -> {'baseline': pps, 'samples': n, 'rate': pps}
        self.blocked = {}             # ip -> {'since', 'baseline', 'links', 'quiet', 'peak'}

        # --- dynamic cost ---
        self.base_cost = {}           # link_key -> C0
        self.link_state = {}          # link_key -> dict written to link_costs.csv

        self._open_logs()
        self.monitor_thread = hub.spawn(self._monitor)
        self.logger.info("CA2 controller: cost mode=%s alpha=%.1f beta=%.1f poll=%.1fs",
                         COST_MODE, COST_ALPHA, COST_BETA, POLL_INTERVAL)

    # ==================================================================
    # CSV logging
    # ==================================================================
    def _open_logs(self):
        log_dir = os.environ.get('CA2_LOG_DIR', 'ca2_logs')
        os.makedirs(log_dir, exist_ok=True)
        self._logs = {}
        headers = {
            'link_costs': ['time', 'link', 'rate_fwd_mbps', 'rate_rev_mbps', 'utilisation',
                           'anomaly', 'base_cost', 'cost', 'norm_cost'],
            'sources': ['time', 'ip', 'pps', 'baseline_pps', 'threshold_pps', 'state'],
            'paths': ['time', 'src', 'dst', 'path', 'cost'],
            'events': ['time', 'event', 'detail'],
        }
        for name, header in headers.items():
            f = open(os.path.join(log_dir, name + '.csv'), 'w', newline='')
            writer = csv.writer(f)
            writer.writerow(header)
            self._logs[name] = (f, writer)

    def _log_row(self, name, row):
        self._logs[name][1].writerow(row)

    def _flush_logs(self):
        for f, _ in self._logs.values():
            f.flush()

    def _event(self, name, detail):
        self.logger.warning("[%s] %s", name, detail)
        self._log_row('events', ['%.3f' % time.time(), name, detail])
        self._logs['events'][0].flush()

    # ==================================================================
    # Switch connection
    # ==================================================================
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Remove our stale rules and install the table-miss entry"""
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        for cookie in (FWD_COOKIE, DROP_COOKIE, ICMP_RATE_COOKIE):
            datapath.send_msg(parser.OFPFlowMod(
                datapath=datapath, cookie=cookie, cookie_mask=0xffffffffffffffff,
                table_id=ofproto.OFPTT_ALL, command=ofproto.OFPFC_DELETE,
                out_port=ofproto.OFPP_ANY, out_group=ofproto.OFPG_ANY,
                match=parser.OFPMatch()))

        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self._add_flow(datapath, 0, parser.OFPMatch(), actions)

        # A switch that (re)connects starts with fresh ports: forget the ports and
        # links recorded as down for it (e.g. after Mininet was stopped and restarted
        # while the controller kept running), otherwise its links are never re-learned.
        self.down_ports = set(p for p in self.down_ports if p[0] != datapath.id)
        self.flow_prev.pop(datapath.id, None)
        self.port_prev.pop(datapath.id, None)

        # flows that crossed this switch have lost a rule: let them be set up again
        for key, flow in list(self.flows.items()):
            if datapath.id in flow['rules']:
                del self.flows[key]

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def state_change_handler(self, ev):
        """Track connected datapaths"""
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[datapath.id] = datapath
        elif ev.state == DEAD_DISPATCHER and datapath.id in self.datapaths:
            del self.datapaths[datapath.id]

    def _add_flow(self, datapath, priority, match, actions, cookie=0,
                  command=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath, cookie=cookie, priority=priority, match=match,
            command=ofproto.OFPFC_ADD if command is None else command,
            instructions=inst)
        datapath.send_msg(mod)

    def _del_flow(self, datapath, priority, match, cookie):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        datapath.send_msg(parser.OFPFlowMod(
            datapath=datapath, cookie=cookie, cookie_mask=0xffffffffffffffff,
            priority=priority, match=match, command=ofproto.OFPFC_DELETE_STRICT,
            out_port=ofproto.OFPP_ANY, out_group=ofproto.OFPG_ANY))

    # ==================================================================
    # Topology discovery
    # ==================================================================
    @set_ev_cls(event.EventSwitchEnter)
    def switch_enter_handler(self, ev):
        self.discover_topology()

    @set_ev_cls(event.EventLinkAdd)
    def link_add_handler(self, ev):
        self.discover_topology()

    @set_ev_cls(event.EventLinkDelete)
    def link_delete_handler(self, ev):
        # LLDP can time out on a congested link while the link is still up, so a
        # link is only removed when its port reports link-down (port_status_handler).
        self.logger.debug("LLDP link delete ignored: %s", ev.link)

    def discover_topology(self):
        """Read switches and links from the Ryu topology module"""
        for switch in get_switch(self, None):
            self.switch_ports[switch.dp.id] = set(p.port_no for p in switch.ports)

        changed = False
        for link in get_link(self, None):
            src, dst = link.src, link.dst
            if (src.dpid, src.port_no) in self.down_ports or \
                    (dst.dpid, dst.port_no) in self.down_ports:
                continue
            if self.link_port.get((src.dpid, dst.dpid)) != src.port_no:
                self.link_port[(src.dpid, dst.dpid)] = src.port_no
                self._forget_hosts_on(src.dpid, src.port_no)
                changed = True

        if changed:
            self.last_topo_change = time.time()
            self._rebuild_graph()
            n_links = len(set(link_key(u, v) for u in self.graph for v in self.graph[u]))
            self.logger.info("Topology: %d switches, %d links",
                             len(self.switch_ports), n_links)

    def _rebuild_graph(self):
        """Graph of bidirectionally discovered links, weighted with the current cost"""
        graph = {dpid: {} for dpid in self.switch_ports}
        for (u, v) in self.link_port:
            if (v, u) not in self.link_port:
                continue
            key = link_key(u, v)
            if key not in self.base_cost:
                self.base_cost[key] = self._base_cost(key)
            cost = self.link_state.get(key, {}).get('cost', self.base_cost[key])
            graph.setdefault(u, {})[v] = cost
            graph.setdefault(v, {})[u] = cost
        self.graph = graph

    @staticmethod
    def _base_cost(key):
        if COST_MODE == 'delay':
            return float(DELAY_COSTS.get(key, CONTROLLER_DEFAULT_COST))
        return float(CONTROLLER_COSTS.get(key, CONTROLLER_DEFAULT_COST))

    def _topology_settled(self):
        return time.time() - self.last_topo_change > TOPOLOGY_SETTLE

    def _is_host_port(self, dpid, port_no):
        for (u, _v), port in self.link_port.items():
            if u == dpid and port == port_no:
                return False
        return True

    def _host_ports(self):
        for dpid, ports in self.switch_ports.items():
            for port_no in ports:
                if self._is_host_port(dpid, port_no):
                    yield dpid, port_no

    def _forget_hosts_on(self, dpid, port_no):
        """A port turned out to be a switch link: drop hosts wrongly learned on it"""
        for ip, host in list(self.hosts.items()):
            if host.dpid == dpid and host.port == port_no:
                del self.hosts[ip]

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        """Link failure / recovery, detected from the port state"""
        msg = ev.msg
        ofproto = msg.datapath.ofproto
        dpid = msg.datapath.id
        port_no = msg.desc.port_no
        is_down = (msg.reason == ofproto.OFPPR_DELETE or
                   bool(msg.desc.state & ofproto.OFPPS_LINK_DOWN))

        if not is_down:
            self.down_ports.discard((dpid, port_no))
            return
        if (dpid, port_no) in self.down_ports:
            return
        self.down_ports.add((dpid, port_no))

        failed = [(u, v) for (u, v), port in self.link_port.items()
                  if u == dpid and port == port_no]
        for (u, v) in failed:
            self.link_port.pop((u, v), None)
            self.link_port.pop((v, u), None)
            self._event('LINK_DOWN', '%s-%s' % (sw(u), sw(v)))
        if failed:
            self._rebuild_graph()
            self._reroute_flows('link failure')

    # ==================================================================
    # Routing (Dijkstra from resilient_controller.py)
    # ==================================================================
    def dijkstra(self, start, end):
        """Lowest-cost switch path under the current dynamic costs"""
        if start not in self.graph or end not in self.graph:
            return None
        distances = {node: float('inf') for node in self.graph}
        previous = {node: None for node in self.graph}
        distances[start] = 0
        queue = [(0, start)]

        while queue:
            current_distance, current_node = heapq.heappop(queue)
            if current_node == end:
                path = []
                while current_node is not None:
                    path.append(current_node)
                    current_node = previous[current_node]
                return path[::-1]
            if current_distance > distances[current_node]:
                continue
            for neighbor, cost in self.graph[current_node].items():
                distance = current_distance + cost
                if distance < distances[neighbor]:
                    distances[neighbor] = distance
                    previous[neighbor] = current_node
                    heapq.heappush(queue, (distance, neighbor))
        return None

    def _path_cost(self, path):
        total = 0.0
        for u, v in zip(path, path[1:]):
            if v not in self.graph.get(u, {}):
                return float('inf')
            total += self.graph[u][v]
        return total

    def _path_rules(self, path, dst_host):
        """{dpid: output port} that carries a flow along path to dst_host"""
        rules = {}
        for i, dpid in enumerate(path):
            if i == len(path) - 1:
                rules[dpid] = dst_host.port
            else:
                rules[dpid] = self.link_port[(dpid, path[i + 1])]
        return rules

    def _install_path(self, src_ip, dst_ip, path):
        """Install or move the (src_ip, dst_ip) flow onto path.

        Rules are written from the destination switch backwards so that a packet
        never reaches a switch that has no rule yet, and rules that are only
        changed use MODIFY so their counters (used for the rate estimate) survive.
        """
        dst_host = self.hosts[dst_ip]
        new_rules = self._path_rules(path, dst_host)
        old_flow = self.flows.get((src_ip, dst_ip), {})
        old_rules = old_flow.get('rules', {})
        old_path = old_flow.get('path', [])
        old_source_dpid = old_path[0] if old_path else None
        source_dpid = path[0]

        for dpid in reversed(path):
            datapath = self.datapaths.get(dpid)
            if datapath is None or old_rules.get(dpid) == new_rules[dpid]:
                continue
            parser = datapath.ofproto_parser
            match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP,
                                    ipv4_src=src_ip, ipv4_dst=dst_ip)
            actions = [parser.OFPActionOutput(new_rules[dpid])]
            command = (datapath.ofproto.OFPFC_MODIFY_STRICT if dpid in old_rules
                       else datapath.ofproto.OFPFC_ADD)
            self._add_flow(datapath, FWD_PRIORITY, match, actions,
                           cookie=FWD_COOKIE, command=command)

        # Separate ICMP Echo Request and Reply counters at the source access
        # switch.  The forwarding actions are identical to the general rule.
        datapath = self.datapaths.get(source_dpid)
        if datapath is not None:
            command = (datapath.ofproto.OFPFC_MODIFY_STRICT
                       if old_source_dpid == source_dpid
                       else datapath.ofproto.OFPFC_ADD)
            self._install_icmp_rate_flows(
                datapath, src_ip, dst_ip, new_rules[source_dpid], command)

        # A host may move to another access switch.  Remove its old typed
        # counters even if that switch remains on the new path as a transit hop.
        if old_source_dpid is not None and old_source_dpid != source_dpid:
            old_datapath = self.datapaths.get(old_source_dpid)
            if old_datapath is not None:
                self._delete_icmp_rate_flows(old_datapath, src_ip, dst_ip)

        for dpid in old_rules:
            if dpid in new_rules or dpid not in self.datapaths:
                continue
            datapath = self.datapaths[dpid]
            match = datapath.ofproto_parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP, ipv4_src=src_ip, ipv4_dst=dst_ip)
            self._del_flow(datapath, FWD_PRIORITY, match, FWD_COOKIE)

        self.flows[(src_ip, dst_ip)] = {'path': list(path), 'rules': new_rules}

    def _install_icmp_rate_flows(self, datapath, src_ip, dst_ip, out_port,
                                 command):
        """Install type-specific counters without changing forwarding behavior"""
        parser = datapath.ofproto_parser
        actions = [parser.OFPActionOutput(out_port)]
        for icmp_type in (ICMP_ECHO_REQUEST, ICMP_ECHO_REPLY):
            match = parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=src_ip, ipv4_dst=dst_ip,
                ip_proto=ICMPV4_PROTO, icmpv4_type=icmp_type)
            self._add_flow(datapath, ICMP_RATE_PRIORITY, match, actions,
                           cookie=ICMP_RATE_COOKIE, command=command)

    def _delete_icmp_rate_flows(self, datapath, src_ip, dst_ip):
        """Remove the type-specific counters for one source/destination pair"""
        parser = datapath.ofproto_parser
        for icmp_type in (ICMP_ECHO_REQUEST, ICMP_ECHO_REPLY):
            match = parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=src_ip, ipv4_dst=dst_ip,
                ip_proto=ICMPV4_PROTO, icmpv4_type=icmp_type)
            self._del_flow(datapath, ICMP_RATE_PRIORITY, match,
                           ICMP_RATE_COOKIE)

    def _ensure_flow(self, src_ip, dst_ip):
        """Route a new (src_ip, dst_ip) pair"""
        if (src_ip, dst_ip) in self.flows:
            return
        src_host, dst_host = self.hosts[src_ip], self.hosts[dst_ip]
        path = self.dijkstra(src_host.dpid, dst_host.dpid)
        if path is None:
            self.logger.warning("No path %s -> %s", src_ip, dst_ip)
            return
        self._install_path(src_ip, dst_ip, path)
        self.logger.info("New flow %s -> %s via %s (cost %.2f)", src_ip, dst_ip,
                         '>'.join(sw(d) for d in path), self._path_cost(path))

    def _reroute_flows(self, reason):
        """Move every flow whose current path is no longer the cheapest one"""
        for (src_ip, dst_ip), flow in list(self.flows.items()):
            if src_ip in self.blocked:
                continue
            src_host, dst_host = self.hosts.get(src_ip), self.hosts.get(dst_ip)
            if src_host is None or dst_host is None:
                continue
            best = self.dijkstra(src_host.dpid, dst_host.dpid)
            if best is None or best == flow['path']:
                continue
            current_cost = self._path_cost(flow['path'])
            best_cost = self._path_cost(best)
            if best_cost + REROUTE_MARGIN < current_cost:
                old = '>'.join(sw(d) for d in flow['path'])
                self._install_path(src_ip, dst_ip, best)
                self._event('REROUTE', '%s->%s %s (%.2f) => %s (%.2f) [%s]' % (
                    src_ip, dst_ip, old, current_cost,
                    '>'.join(sw(d) for d in best), best_cost, reason))

    # ==================================================================
    # Packet handling
    # ==================================================================
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        dpid = msg.datapath.id
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None or eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return
        if not self._topology_settled():
            return   # host ports are not known until link discovery has finished

        from_host = self._is_host_port(dpid, in_port)

        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt:
            if from_host:
                self._learn_host(arp_pkt.src_ip, arp_pkt.src_mac, dpid, in_port)
            self._handle_arp(msg, arp_pkt, dpid, in_port)
            return

        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if ip_pkt:
            if from_host:
                self._learn_host(ip_pkt.src, eth.src, dpid, in_port)
            self._handle_ipv4(msg, ip_pkt)

    def _learn_host(self, ip, mac, dpid, port):
        if ip == '0.0.0.0':
            return
        host = Host(mac, dpid, port)
        if self.hosts.get(ip) != host:
            self.hosts[ip] = host
            self.logger.info("Host %s (%s) at %s port %s", ip, mac, sw(dpid), port)

    def _handle_arp(self, msg, arp_pkt, dpid, in_port):
        """Deliver ARP straight to the target's port; flood only to host ports"""
        target = self.hosts.get(arp_pkt.dst_ip)
        if target:
            self._packet_out(target.dpid, target.port, msg.data)
        elif arp_pkt.opcode == arp.ARP_REQUEST:
            for out_dpid, out_port in self._host_ports():
                if (out_dpid, out_port) != (dpid, in_port):
                    self._packet_out(out_dpid, out_port, msg.data)

    def _handle_ipv4(self, msg, ip_pkt):
        src_ip, dst_ip = ip_pkt.src, ip_pkt.dst
        if src_ip in self.blocked:
            return   # immediate drop if blocked
        dst_host = self.hosts.get(dst_ip)
        if dst_host is None:
            return   # location unknown until the destination has sent ARP
        if src_ip in self.hosts:
            self._ensure_flow(src_ip, dst_ip)
        # hand the packet that missed the flow table directly to the destination
        self._packet_out(dst_host.dpid, dst_host.port, msg.data)

    def _packet_out(self, dpid, port, data):
        datapath = self.datapaths.get(dpid)
        if datapath is None:
            return
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        datapath.send_msg(parser.OFPPacketOut(
            datapath=datapath, buffer_id=ofproto.OFP_NO_BUFFER,
            in_port=ofproto.OFPP_CONTROLLER,
            actions=[parser.OFPActionOutput(port)], data=data))

    # ==================================================================
    # Monitoring loop
    # ==================================================================
    def _monitor(self):
        hub.sleep(5)   # give switches time to connect
        while True:
            for datapath in list(self.datapaths.values()):
                self._request_stats(datapath)
            hub.sleep(STATS_WAIT)
            try:
                self._evaluate()
            except Exception:
                self.logger.exception("monitor iteration failed")
            hub.sleep(max(0.1, POLL_INTERVAL - STATS_WAIT))

    def _request_stats(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        datapath.send_msg(parser.OFPFlowStatsRequest(datapath))
        datapath.send_msg(parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY))

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply_handler(self, ev):
        msg = ev.msg
        dpid = msg.datapath.id
        pending = self.flow_pending.setdefault(dpid, {'fwd': {}, 'drop': {}})
        for stat in msg.body:
            ip_src = stat.match.get('ipv4_src')
            if not ip_src:
                continue
            if stat.cookie == FWD_COOKIE:
                pending['fwd'][(ip_src, stat.match.get('ipv4_dst'), None)] = \
                    (stat.packet_count, stat.byte_count)
            elif stat.cookie == ICMP_RATE_COOKIE:
                icmp_type = stat.match.get('icmpv4_type')
                if icmp_type not in (ICMP_ECHO_REQUEST, ICMP_ECHO_REPLY):
                    continue
                pending['fwd'][(ip_src, stat.match.get('ipv4_dst'), icmp_type)] = \
                    (stat.packet_count, stat.byte_count)
            elif stat.cookie == DROP_COOKIE:
                pending['drop'][ip_src] = stat.packet_count
        if not msg.flags & msg.datapath.ofproto.OFPMPF_REPLY_MORE:
            pending['time'] = time.time()
            self.flow_sample[dpid] = pending
            del self.flow_pending[dpid]

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        dpid = ev.msg.datapath.id
        self.port_sample[dpid] = {
            'time': time.time(),
            'tx': {stat.port_no: stat.tx_bytes for stat in ev.msg.body}}

    def _evaluate(self):
        """One monitoring step: rates -> detection -> costs -> rerouting -> logs"""
        now = time.time()
        source_pps, flow_pps, drop_pps = self._measure_sources()
        self._measure_links()

        self._check_anomalies(source_pps, flow_pps, now)
        self._check_recovery(drop_pps, now)
        self._update_costs(now)
        self._reroute_flows('cost update')
        self._log_state(now, source_pps, drop_pps)

    # ------------------------------------------------------------------
    # Rate estimation
    # ------------------------------------------------------------------
    def _measure_sources(self):
        """Per-source pps at access switches, excluding ICMP echo responses"""
        source_pps, flow_pps, drop_pps = {}, {}, {}
        measured_flow_pps = {}
        access = {}
        for ip, host in self.hosts.items():
            access.setdefault(host.dpid, set()).add(ip)

        for dpid, sample in list(self.flow_sample.items()):
            prev = self.flow_prev.get(dpid)
            self.flow_prev[dpid] = sample
            del self.flow_sample[dpid]
            if prev is None or sample['time'] <= prev['time']:
                continue
            dt = sample['time'] - prev['time']
            local_ips = access.get(dpid, set())

            for ip in local_ips:
                source_pps[ip] = 0.0
            for (src, dst, icmp_type), (pkts, _bytes) in sample['fwd'].items():
                if src not in local_ips:
                    continue
                key = (src, dst, icmp_type)
                before = prev['fwd'].get(key, (0, 0))[0]
                delta = pkts - before if pkts >= before else pkts
                measured_flow_pps[key] = delta / dt

            for ip, pkts in sample['drop'].items():
                if ip not in local_ips:
                    continue
                before = prev['drop'].get(ip, 0)
                delta = pkts - before if pkts >= before else pkts
                drop_pps[ip] = delta / dt

        # Echo Replies are response traffic generated by the destination.  Do
        # not treat them as that host's independently initiated traffic: the
        # matching Echo Request can fall in a different stats poll (or already
        # be blocked), since OpenFlow stats arrive asynchronously per switch.
        # Echo Requests and all non-echo IPv4 traffic remain eligible for
        # source anomaly detection. Port counters still include replies when
        # measuring link load.
        for (src, dst, icmp_type), rate in measured_flow_pps.items():
            if icmp_type == ICMP_ECHO_REPLY:
                continue
            if rate <= 0.0:
                continue
            flow_pps[(src, dst)] = flow_pps.get((src, dst), 0.0) + rate
            source_pps[src] += rate
        return source_pps, flow_pps, drop_pps

    def _measure_links(self):
        """Bit/s per directed switch-to-switch link from the port tx counters"""
        for dpid, sample in list(self.port_sample.items()):
            prev = self.port_prev.get(dpid)
            self.port_prev[dpid] = sample
            del self.port_sample[dpid]
            if prev is None or sample['time'] <= prev['time']:
                continue
            dt = sample['time'] - prev['time']
            for (u, v), port in self.link_port.items():
                if u != dpid or port not in sample['tx'] or port not in prev['tx']:
                    continue
                rate = max(0, sample['tx'][port] - prev['tx'][port]) * 8.0 / dt
                old = self.link_rate.get((u, v))
                self.link_rate[(u, v)] = rate if old is None else \
                    LOAD_SMOOTHING * rate + (1 - LOAD_SMOOTHING) * old

    # ------------------------------------------------------------------
    # Anomaly detection and blocking (from anomaly_detection.py)
    # ------------------------------------------------------------------
    def _check_anomalies(self, source_pps, flow_pps, now):
        for ip, pps in source_pps.items():
            if ip in self.blocked:
                continue
            stats = self.sources.setdefault(ip, {'baseline': None, 'samples': 0})
            stats['rate'] = pps
            if stats['baseline'] is None:
                stats['baseline'] = pps
                stats['samples'] = 1
                continue

            # The sample is compared with the baseline *before* it is folded in,
            # and an anomalous sample never updates the baseline.
            threshold = max(THRESHOLD_MULT * stats['baseline'], MIN_ANOMALY_PPS)
            if stats['samples'] >= WARMUP_SAMPLES and pps > threshold:
                self._block_ip(ip, pps, stats['baseline'], flow_pps, now)
            else:
                stats['baseline'] = EMA_ALPHA * pps + (1 - EMA_ALPHA) * stats['baseline']
                stats['samples'] += 1

    def _block_ip(self, ip, pps, baseline, flow_pps, now):
        # Links carrying the anomalous traffic: the paths of the source's heavy flows
        links = set()
        for (src, dst), rate in flow_pps.items():
            if src != ip or rate < HEAVY_FLOW_SHARE * pps or (src, dst) not in self.flows:
                continue
            path = self.flows[(src, dst)]['path']
            links.update(link_key(u, v) for u, v in zip(path, path[1:]))

        self._event('ANOMALY', '%s rate=%.0f pps baseline=%.1f pps threshold=%.0f pps links=%s' % (
            ip, pps, baseline, max(THRESHOLD_MULT * baseline, MIN_ANOMALY_PPS),
            ','.join('%s-%s' % (sw(u), sw(v)) for u, v in sorted(links))))

        for datapath in self.datapaths.values():
            parser = datapath.ofproto_parser
            match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_src=ip)
            self._add_flow(datapath, DROP_PRIORITY, match, [], cookie=DROP_COOKIE)  # drop

        self.blocked[ip] = {'since': now, 'baseline': baseline, 'links': links,
                            'quiet': 0, 'peak': pps}
        self._event('BLOCK', '%s blocked on all switches' % ip)

    def _check_recovery(self, drop_pps, now):
        """Release a blocked source once the drop rule stops seeing anomalous traffic"""
        for ip, info in list(self.blocked.items()):
            if ip not in drop_pps:
                continue
            limit = max(THRESHOLD_MULT * info['baseline'], MIN_ANOMALY_PPS)
            info['rate'] = drop_pps[ip]
            info['quiet'] = info['quiet'] + 1 if drop_pps[ip] <= limit else 0
            if info['quiet'] < RECOVERY_POLLS:
                continue
            for datapath in self.datapaths.values():
                parser = datapath.ofproto_parser
                match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_src=ip)
                self._del_flow(datapath, DROP_PRIORITY, match, DROP_COOKIE)
            del self.blocked[ip]
            self._event('UNBLOCK', '%s released after %.0f s (anomalous traffic stopped)' % (
                ip, now - info['since']))

    # ------------------------------------------------------------------
    # Dynamic link cost
    # ------------------------------------------------------------------
    def _update_costs(self, now):
        """C_ij(t) = C0_ij + ALPHA * R_ij(t)/Rmax + BETA * A_ij(t)"""
        anomaly_links = set()
        for info in self.blocked.values():
            anomaly_links |= info['links']

        # links that are no longer in the graph must not linger in the logs
        for key in list(self.link_state):
            if key[1] not in self.graph.get(key[0], {}):
                del self.link_state[key]

        for u in self.graph:
            for v in self.graph[u]:
                if u > v:
                    continue
                key = (u, v)
                fwd = self.link_rate.get((u, v), 0.0)
                rev = self.link_rate.get((v, u), 0.0)
                utilisation = min(1.0, max(fwd, rev) / LINK_CAPACITY_BPS)
                anomaly = 1 if key in anomaly_links else 0
                cost = self.base_cost[key] + COST_ALPHA * utilisation + COST_BETA * anomaly
                self.graph[u][v] = cost
                self.graph[v][u] = cost
                self.link_state[key] = {'fwd': fwd, 'rev': rev, 'utilisation': utilisation,
                                        'anomaly': anomaly, 'cost': cost}

    def _log_state(self, now, source_pps, drop_pps):
        stamp = '%.3f' % now
        for (u, v), state in sorted(self.link_state.items()):
            base = self.base_cost[(u, v)]
            self._log_row('link_costs', [
                stamp, '%s-%s' % (sw(u), sw(v)),
                '%.3f' % (state['fwd'] / 1e6), '%.3f' % (state['rev'] / 1e6),
                '%.4f' % state['utilisation'], state['anomaly'],
                '%.2f' % base, '%.3f' % state['cost'], '%.4f' % (state['cost'] / base)])

        for ip in sorted(self.hosts):
            if ip in self.blocked:
                info = self.blocked[ip]
                limit = max(THRESHOLD_MULT * info['baseline'], MIN_ANOMALY_PPS)
                self._log_row('sources', [stamp, ip, '%.1f' % drop_pps.get(ip, info.get('rate', 0.0)),
                                          '%.2f' % info['baseline'], '%.1f' % limit, 'blocked'])
            elif ip in self.sources and self.sources[ip]['baseline'] is not None:
                stats = self.sources[ip]
                limit = max(THRESHOLD_MULT * stats['baseline'], MIN_ANOMALY_PPS)
                self._log_row('sources', [stamp, ip, '%.1f' % source_pps.get(ip, stats.get('rate', 0.0)),
                                          '%.2f' % stats['baseline'], '%.1f' % limit, 'normal'])

        for (src_ip, dst_ip), flow in sorted(self.flows.items()):
            self._log_row('paths', [stamp, src_ip, dst_ip,
                                    '>'.join(sw(d) for d in flow['path']),
                                    '%.3f' % self._path_cost(flow['path'])])
        self._flush_logs()
