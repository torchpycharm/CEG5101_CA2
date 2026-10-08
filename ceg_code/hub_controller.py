"""

CEG5101
Ryu Controller as a forwarding Hub
Credits: https://github.com/scc365/tutorial-ryu
"""

from ryu.base.app_manager import RyuApp
from ryu.controller import ofp_event
from ryu.ofproto import ofproto_v1_3
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib.dpid import dpid_to_str
from ryu.lib.packet import packet


class HubController(RyuApp):

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(HubController, self).__init__(*args, **kwargs)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def features_handler(self, ev):
        '''
        When a datapath sets up a connection with the controller,
        the controller sends a Features Request
        This function responds to the event of the Features Request

        Installs a low level flow table modification that sends packets to
        the controller. This happens when there are misses in the flow-table.
        '''
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.logger.info("Handshake done with network device {}".format(dpid_to_str(datapath.id)))
        self.__add_flow(datapath, 0, match, actions)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        '''

        The packets sent to the controller are handled by this function
        and floods them to all ports (Ethernet Hub)
        
        '''
        msg = ev.msg
        datapath = msg.datapath
        ofproto = msg.datapath.ofproto
        parser = msg.datapath.ofproto_parser
        dpid = msg.datapath.id
        pkt = packet.Packet(msg.data)
        in_port = msg.match['in_port']
        data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
        actions = [datapath.ofproto_parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id, in_port=in_port, actions=actions, data=data)
        self.logger.info("Flooding packet")
        datapath.send_msg(out)
        return

    def __add_flow(self, datapath, priority, match, actions):
        '''
        Creates a Flow-Mod using a list of OpenFlow Actions and a OpenFlow Packet Match, 
        added to the datapath priority-wise.
        '''
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst)
        self.logger.info("Flow-Mod added to {}".format(dpid_to_str(datapath.id)))
        datapath.send_msg(mod)