"""
CEG5101
Topology file
Credits: https://github.com/scc365/tutorial-ryu

"""
from mininet.topo import Topo
from mininet.link import TCLink


class cegTopology(Topo):

    def build(self):

        # Add the central switch
        s1 = self.addSwitch('s1')

        # connect n hosts to the switch
        hosts = []
        for h in range(0, 5):
            hosts.append(self.addHost("h{}".format(h+1)))
            self.addLink(s1, hosts[h], cls=TCLink, bw=40, delay='15ms')


# the topology is supposed to be accessed via the mn tool's `--topo` flag
topos = {
    'cegTopo': (lambda: cegTopology())
}
