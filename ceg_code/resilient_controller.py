from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types
from ryu.topology import event
from ryu.topology.api import get_switch, get_link
import heapq
import time
import threading

class Assignment2Controller(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    
    def __init__(self, *args, **kwargs):
        super(Assignment2Controller, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.switch_ports = {}
        self.network_graph = {}
        self.mst = {}
        self.link_costs = {}
        self.host_ports = {}
        self.datapaths = {}
        self.links = []
        self.topology_lock = threading.Lock()
        
        # Predefined link costs from topology (delay in ms)
        self.predefined_costs = {
            ('0000000000000001', '0000000000000002'): 5,
            ('0000000000000002', '0000000000000001'): 5,
            ('0000000000000002', '0000000000000003'): 10,
            ('0000000000000003', '0000000000000002'): 10,
            ('0000000000000003', '0000000000000004'): 15,
            ('0000000000000004', '0000000000000003'): 15,
            ('0000000000000004', '0000000000000001'): 20,
            ('0000000000000001', '0000000000000004'): 20,
            ('0000000000000002', '0000000000000004'): 8,
            ('0000000000000004', '0000000000000002'): 8,
        }

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER])
    def state_change_handler(self, ev):
        """Track connected datapaths"""
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[datapath.id] = datapath
            # Update topology when a new switch connects
            self.discover_topology()

    @set_ev_cls(event.EventSwitchEnter)
    def switch_enter_handler(self, ev):
        """Handle switch connection event"""
        switch = ev.switch
        dpid = format(switch.dp.id, '016x')
        self.logger.info("Switch connected: %s", dpid)
        self.discover_topology()

    @set_ev_cls(event.EventSwitchLeave)
    def switch_leave_handler(self, ev):
        """Handle switch disconnection event"""
        switch = ev.switch
        dpid = format(switch.dp.id, '016x')
        self.logger.warning("Switch disconnected: %s", dpid)
        self.discover_topology()

    @set_ev_cls(event.EventLinkAdd)
    def link_add_handler(self, ev):
        """Handle link addition event"""
        link = ev.link
        src_dpid = format(link.src.dpid, '016x')
        dst_dpid = format(link.dst.dpid, '016x')
        self.logger.info("Link added: %s -> %s", src_dpid, dst_dpid)
        self.discover_topology()

    @set_ev_cls(event.EventLinkDelete)
    def link_delete_handler(self, ev):
        """Handle link deletion event"""
        link = ev.link
        src_dpid = format(link.src.dpid, '016x')
        dst_dpid = format(link.dst.dpid, '016x')
        self.logger.warning("Link deleted: %s -> %s", src_dpid, dst_dpid)
        self.discover_topology()

    def discover_topology(self):
        """Discover network topology"""
        with self.topology_lock:
            try:
                self.logger.info("Discovering topology...")
                
                # Clear previous data
                self.network_graph = {}
                self.links = []
                
                # Get all switches
                switch_list = get_switch(self, None)
                for switch in switch_list:
                    dpid = format(switch.dp.id, '016x')
                    self.network_graph[dpid] = {}
                    self.switch_ports[dpid] = [p.port_no for p in switch.ports]
                    self.logger.info("Found switch: %s with ports: %s", dpid, self.switch_ports[dpid])
                
                # Get all links
                link_list = get_link(self, None)
                for link in link_list:
                    src_dpid = format(link.src.dpid, '016x')
                    dst_dpid = format(link.dst.dpid, '016x')
                    src_port = link.src.port_no
                    dst_port = link.dst.port_no
                    
                    # Store the link
                    self.links.append({
                        'src_dpid': src_dpid,
                        'src_port': src_port,
                        'dst_dpid': dst_dpid,
                        'dst_port': dst_port
                    })
                    
                    # Add link to graph with cost
                    cost = self.get_link_cost(src_dpid, dst_dpid)
                    if src_dpid not in self.network_graph:
                        self.network_graph[src_dpid] = {}
                    self.network_graph[src_dpid][dst_dpid] = cost
                    
                    if dst_dpid not in self.network_graph:
                        self.network_graph[dst_dpid] = {}
                    self.network_graph[dst_dpid][src_dpid] = cost
                    
                    self.link_costs[(src_dpid, dst_dpid)] = cost
                    self.link_costs[(dst_dpid, src_dpid)] = cost
                    
                    self.logger.info("Found link: %s:%s -> %s:%s (cost: %s)", 
                                    src_dpid, src_port, dst_dpid, dst_port, cost)
                
                # Identify host ports (ports not connected to other switches)
                self.identify_host_ports()
                
                # Compute MST for flooding
                self.compute_mst()
                
                self.logger.info("Network graph: %s", self.network_graph)
                self.logger.info("MST: %s", self.mst)
                self.logger.info("Host ports: %s", self.host_ports)
                
            except Exception as e:
                self.logger.error("Topology discovery error: %s", e)

    def get_link_cost(self, src_dpid, dst_dpid):
        """Get cost for a link between two switches"""
        # Try to find predefined cost
        if (src_dpid, dst_dpid) in self.predefined_costs:
            return self.predefined_costs[(src_dpid, dst_dpid)]
        elif (dst_dpid, src_dpid) in self.predefined_costs:
            return self.predefined_costs[(dst_dpid, src_dpid)]
        else:
            # Default cost if not predefined
            return 10

    def identify_host_ports(self):
        """Identify which ports are connected to hosts and initialize mac_to_port mapping"""
        self.host_ports = {}
    
        # Start by assuming all ports are host ports
        for dpid in self.switch_ports:
            self.host_ports[dpid] = set(self.switch_ports[dpid])
    
        # Remove ports that are connected to other switches
        for link in self.links:
            src_dpid = link['src_dpid']
            src_port = link['src_port']
            dst_dpid = link['dst_dpid']
            dst_port = link['dst_port']
        
            if src_port in self.host_ports.get(src_dpid, []):
                self.host_ports[src_dpid].remove(src_port)
            if dst_port in self.host_ports.get(dst_dpid, []):
                self.host_ports[dst_dpid].remove(dst_port)
    
        # Convert sets to lists
        for dpid in self.host_ports:
            self.host_ports[dpid] = list(self.host_ports[dpid])

        # Optional: proactively log and prepare host learning
        for dpid, ports in self.host_ports.items():
            for port in ports:
                self.logger.info("Host port detected: switch %s port %s", dpid, port)
                # Note: we don't know the host MAC yet, but we now know this is a host-facing port.
                # When a new source MAC appears on this port in _packet_in_handler,
            # we can safely record it as (dpid, port).

    def compute_mst(self):
        """Compute Minimum Spanning Tree using Prim's algorithm"""
        if not self.network_graph:
            self.mst = {}
            return
            
        # Initialize MST
        self.mst = {node: [] for node in self.network_graph}
        
        # Start with first node
        start_node = next(iter(self.network_graph))
        visited = set([start_node])
        edges = []
        
        # Add all edges from start node to priority queue
        for neighbor, cost in self.network_graph[start_node].items():
            heapq.heappush(edges, (cost, start_node, neighbor))
        
        # Build MST
        while edges and len(visited) < len(self.network_graph):
            cost, u, v = heapq.heappop(edges)
            if v not in visited:
                visited.add(v)
                self.mst[u].append(v)
                self.mst[v].append(u)
                
                # Add all edges from v to unvisited nodes
                for neighbor, neighbor_cost in self.network_graph[v].items():
                    if neighbor not in visited:
                        heapq.heappush(edges, (neighbor_cost, v, neighbor))

    def dijkstra(self, start, end):
        """Calculate shortest path using Dijkstra's algorithm"""
        # Convert to string if needed
        start = str(start)
        end = str(end)
        
        # Check if nodes exist in graph
        if start not in self.network_graph or end not in self.network_graph:
            return None
            
        # Initialize distances and previous nodes
        distances = {node: float('inf') for node in self.network_graph}
        previous = {node: None for node in self.network_graph}
        distances[start] = 0
        
        # Priority queue: (distance, node)
        queue = [(0, start)]
        
        while queue:
            current_distance, current_node = heapq.heappop(queue)
            
            # If we reached the end node, reconstruct the path
            if current_node == end:
                path = []
                while current_node is not None:
                    path.append(current_node)
                    current_node = previous[current_node]
                return path[::-1]  # Reverse the path
            
            # If we found a better path already, skip
            if current_distance > distances[current_node]:
                continue
                
            # Check all neighbors
            for neighbor, cost in self.network_graph[current_node].items():
                distance = current_distance + cost
                if distance < distances[neighbor]:
                    distances[neighbor] = distance
                    previous[neighbor] = current_node
                    heapq.heappush(queue, (distance, neighbor))
        
        # No path found
        return None
        
    def get_port_to_node(self, src_dpid, dst_dpid):
        for link in self.links:
            if (link['src_dpid'] == src_dpid and link['dst_dpid'] == dst_dpid):
                return link['src_port']
            elif (link['dst_dpid'] == src_dpid and link['src_dpid'] == dst_dpid):
                 return link['dst_port']
        return None
        
        
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Handle switch features to install table-miss flow entry"""
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        # Install table-miss flow entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        """Add a flow entry to the switch"""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        """Handle packet_in messages"""
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            # Ignore LLDP packets
            return
            
        dst = eth.dst
        src = eth.src
        
        
        dpid = format(datapath.id, '016x')
        self.logger.debug("[DEBUG] Packet in: switch=%s, in_port=%s, host_ports=%s",
                  dpid, in_port, self.host_ports.get(dpid, []))

        if in_port in self.host_ports.get(dpid, []):
            self.logger.info("[PACKET_IN] Host %s detected on switch %s port %s",
                     src, dpid, in_port)
            # This is a host-facing port
            self.mac_to_port[src] = (dpid, in_port)

            # Add host into graph explicitly
            if src not in self.network_graph:
                self.network_graph[src] = {}
            self.network_graph[src][dpid] = 1
            if dpid not in self.network_graph:
                self.network_graph[dpid] = {}
            self.network_graph[dpid][src] = 1

            # LOGGING

            self.logger.debug("[GRAPH] Added edge %s <-> %s", src, dpid)
        else:
            self.logger.debug("[PACKET_IN] Non-host packet: src=%s switch=%s port=%s",
                      src, dpid, in_port)


        if dst in self.mac_to_port:
            # Known destination - use Dijkstra to find path
            dest_dpid, dest_port = self.mac_to_port[dst]
    
            if dpid == dest_dpid:
                # Destination is on the same switch
                out_port = dest_port
            else:
                # Calculate path using Dijkstra
                path = self.dijkstra(dpid, dest_dpid)
        
                if path and len(path) >= 2:
                    # Find next hop in the path
                    next_hop = path[1]
            
                    # Find the port that connects to the next hop using helper function
                    out_port = self.get_port_to_node(dpid, next_hop)
            
                    if out_port is None:
                       self.logger.warning("Could not find port to next hop")
                       self.flood_packet(msg)
                       return
                else:
                    self.logger.warning("No path found to destination")
                    self.flood_packet(msg)
                    return
                    
            # Install flow rule for future packets
            actions = [parser.OFPActionOutput(out_port)]
            match = parser.OFPMatch(eth_dst=dst)
            self.add_flow(datapath, 1, match, actions, msg.buffer_id)
            
            # Send packet out
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.send_packet_out(datapath, msg.buffer_id, in_port, actions)
            else:
                self.send_packet_out(datapath, ofproto.OFP_NO_BUFFER, in_port, actions, msg.data)
        else:
            # Unknown destination - flood using MST
            # self.logger.info("Flooding packet from %s to %s", src, dst)
            self.flood_packet(msg)

    def flood_packet(self, msg):
        """Flood packet using MST to prevent broadcast storms"""
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        dpid = format(datapath.id, '016x')
        
        # Get MST ports for this switch
        mst_ports = []
        if dpid in self.mst:
            for neighbor in self.mst[dpid]:
                # Find port that connects to this neighbor
                for link in self.links:
                    if (link['src_dpid'] == dpid and link['dst_dpid'] == neighbor):
                        mst_ports.append(link['src_port'])
                        break
                    elif (link['dst_dpid'] == dpid and link['src_dpid'] == neighbor):
                        mst_ports.append(link['dst_port'])
                        break
        
        # Get host ports for this switch
        host_ports = self.host_ports.get(dpid, [])
        
        # Combine MST ports and host ports, exclude incoming port
        out_ports = [p for p in set(mst_ports + host_ports) if p != in_port]
        
        # Send packet out through all out_ports
        for out_port in out_ports:
            actions = [parser.OFPActionOutput(out_port)]
            self.send_packet_out(datapath, ofproto.OFP_NO_BUFFER, in_port, actions, msg.data)

    def send_packet_out(self, datapath, buffer_id, in_port, actions, data=None):
        """Send packet out message to switch"""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        if data is None:
            data = b''
            
        out = parser.OFPPacketOut(
            datapath=datapath, buffer_id=buffer_id, in_port=in_port,
            actions=actions, data=data)
        datapath.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        """Handle port status changes for link failure detection"""
        msg = ev.msg
        reason = msg.reason
        datapath = msg.datapath
        ofproto = datapath.ofproto
        dpid = format(datapath.id, '016x')
        port_no = msg.desc.port_no
        
        if reason == ofproto.OFPPR_DELETE:
            self.logger.warning("Port %s on switch %s deleted", port_no, dpid)
            self.handle_link_failure(dpid, port_no)
        elif reason == ofproto.OFPPR_ADD:
            self.logger.info("Port %s on switch %s added", port_no, dpid)
        elif reason == ofproto.OFPPR_MODIFY:
            self.logger.info("Port %s on switch %s modified", port_no, dpid)

    def handle_link_failure(self, dpid, port_no):
        """Handle link failure by updating graph and recalculating paths"""
        # Find which link failed
        failed_link = None
        for link in self.links:
            if (link['src_dpid'] == dpid and link['src_port'] == port_no) or \
               (link['dst_dpid'] == dpid and link['dst_port'] == port_no):
                failed_link = (link['src_dpid'], link['dst_dpid'])
                break
        
        if failed_link:
            self.logger.warning("Link failure detected: %s", failed_link)
            
            # Remove failed link from graph
            if failed_link[0] in self.network_graph and failed_link[1] in self.network_graph[failed_link[0]]:
                del self.network_graph[failed_link[0]][failed_link[1]]
            if failed_link[1] in self.network_graph and failed_link[0] in self.network_graph[failed_link[1]]:
                del self.network_graph[failed_link[1]][failed_link[0]]
            
            # Recompute MST
            self.compute_mst()
            
            # Clear flow tables on all switches to force recalculation
            self.clear_flow_tables()
            
            self.logger.info("Network updated after link failure")

    def clear_flow_tables(self):
        """Clear all flow tables on all switches"""
        for datapath in self.datapaths.values():
            ofproto = datapath.ofproto
            parser = datapath.ofproto_parser
            
            # Create flow mod message to delete all flows
            match = parser.OFPMatch()
            instructions = []
            flow_mod = parser.OFPFlowMod(
                datapath=datapath,
                command=ofproto.OFPFC_DELETE,
                out_port=ofproto.OFPP_ANY,
                out_group=ofproto.OFPG_ANY,
                match=match,
                instructions=instructions
            )
            datapath.send_msg(flow_mod)
            
            # Reinstall table-miss flow entry
            actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                              ofproto.OFPCML_NO_BUFFER)]
            self.add_flow(datapath, 0, match, actions)
