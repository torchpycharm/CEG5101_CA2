from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, arp, ipv4, icmp, tcp, udp
from ryu.lib.dpid import dpid_to_str

class LearningSwitchWithFirewall13(app_manager.RyuApp):
    """
    A Layer-2 learning switch with firewall functionality.
    Blocks HTTP (port 80) and ICMP traffic from specific hosts.
    """
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(LearningSwitchWithFirewall13, self).__init__(*args, **kwargs)
        # MAC address table: MAC -> (switch_id, port)
        self.mac_to_port = {}
        
        # Firewall rules: Block HTTP and ICMP from these IPs
        self.blocked_ips = ['10.0.0.2', '10.0.0.3']
        
        # IP to MAC mapping for firewall enforcement
        self.ip_to_mac = {}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Handles switch connection. Installs table-miss flow entry."""
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        self.logger.info("Switch connected: %s", dpid_to_str(datapath.id))
        
        # Install table-miss flow entry to send packets to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        """Helper function to install a flow rule."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        datapath.send_msg(mod)

    def should_block_packet(self, pkt):
        """Check if the packet should be blocked based on firewall rules"""
        # Extract IP packet
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if not ip_pkt:
            return False
            
        # Check if source IP is in blocked list
        if ip_pkt.src not in self.blocked_ips:
            return False
            
        # Check for HTTP traffic (TCP port 80)
        tcp_pkt = pkt.get_protocol(tcp.tcp)
        if tcp_pkt and (tcp_pkt.dst_port == 80 or tcp_pkt.src_port == 80):
            self.logger.info("Blocking HTTP traffic from %s", ip_pkt.src)
            return True
            
        # Check for ICMP traffic
        icmp_pkt = pkt.get_protocol(icmp.icmp)
        if icmp_pkt:
            self.logger.info("Blocking ICMP traffic from %s", ip_pkt.src)
            return True
            
        return False

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        """Handles incoming packets. Implements MAC learning and firewall."""
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if not eth:
            return

        # Check if packet should be blocked by firewall
        if self.should_block_packet(pkt):
            self.logger.info("Dropping packet due to firewall rule")
            return  # Drop the packet

        dst = eth.dst
        src = eth.src
        dpid = datapath.id
        
        # Learn the source MAC address
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port
        
        # Learn IP to MAC mapping for firewall enforcement
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if ip_pkt:
            self.ip_to_mac[ip_pkt.src] = src
            
        self.logger.info("Learned MAC: %s -> switch %s, port %s", src, dpid, in_port)

        if dst in self.mac_to_port[dpid]:
            # Destination is known - forward to specific port
            out_port = self.mac_to_port[dpid][dst]
            self.logger.info("Forwarding to known host: port %s", out_port)
        else:
            # Destination unknown - flood the packet
            out_port = ofproto.OFPP_FLOOD
            self.logger.info("Flooding packet")

        # Construct actions
        actions = [parser.OFPActionOutput(out_port)]

        # Install a flow rule if we know the destination (avoid future PacketIns)
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions, msg.buffer_id)
                return
            else:
                self.add_flow(datapath, 1, match, actions)
                
        # Send the packet out
        data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
