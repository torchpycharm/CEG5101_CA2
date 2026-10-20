"""Build the CEG5101 CA2 report (.docx) from run4 results."""
import os
import re
import sys

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

REPORT_DIR = sys.argv[1]
FIG = os.path.join(REPORT_DIR, 'figures')
OUT = os.path.join(REPORT_DIR, 'CEG5101_CA2_Report.docx')

HEAD_COLOR = RGBColor(0x1F, 0x38, 0x64)
MUTED = RGBColor(0x59, 0x59, 0x59)

doc = Document()

# ------------------------------------------------------------------ page + styles
for s in doc.sections:
    s.page_height, s.page_width = Cm(29.7), Cm(21.0)
    s.top_margin = s.bottom_margin = Cm(2.2)
    s.left_margin = s.right_margin = Cm(2.3)

st = doc.styles['Normal']
st.font.name = 'Calibri'
st.font.size = Pt(10.5)
st.element.rPr.rFonts.set(qn('w:eastAsia'), 'Calibri')
st.paragraph_format.space_after = Pt(5)
st.paragraph_format.line_spacing = 1.12

for name, size, before, after in (('Heading 1', 14, 14, 6), ('Heading 2', 12, 10, 4), ('Heading 3', 11, 8, 3)):
    h = doc.styles[name]
    h.font.name = 'Calibri'
    h.element.rPr.rFonts.set(qn('w:eastAsia'), 'Calibri')
    h.font.size = Pt(size)
    h.font.bold = True
    h.font.color.rgb = HEAD_COLOR
    h.paragraph_format.space_before = Pt(before)
    h.paragraph_format.space_after = Pt(after)
    h.paragraph_format.keep_with_next = True

cap = doc.styles['Caption']
cap.font.name = 'Calibri'
cap.font.size = Pt(9)
cap.font.italic = False
cap.font.bold = False
cap.font.color.rgb = MUTED
cap.paragraph_format.space_after = Pt(8)

for lst in ('List Bullet', 'List Number'):
    doc.styles[lst].font.size = Pt(10.5)
    doc.styles[lst].paragraph_format.space_after = Pt(2)

# footer page number
def add_page_number(section):
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    for tag, text in (('begin', None), (None, 'PAGE'), ('end', None)):
        if tag:
            el = OxmlElement('w:fldChar')
            el.set(qn('w:fldCharType'), tag)
        else:
            el = OxmlElement('w:instrText')
            el.set(qn('xml:space'), 'preserve')
            el.text = text
        run._r.append(el)
    run.font.size = Pt(9)
    run.font.color.rgb = MUTED


# ------------------------------------------------------------------ inline markup
TOKEN = re.compile(r'(\*\*.+?\*\*|`.+?`|\*[^*\s][^*]*?\*|_\{.+?\}|\^\{.+?\})')


def add_runs(p, text, size=None, color=None, bold=None):
    for part in TOKEN.split(text):
        if not part:
            continue
        if part.startswith('**'):
            r = p.add_run(part[2:-2]); r.bold = True
        elif part.startswith('`'):
            r = p.add_run(part[1:-1]); r.font.name = 'Consolas'
            r._element.rPr.rFonts.set(qn('w:eastAsia'), 'Consolas')
            r.font.size = Pt((size or 10.5) - 1)
        elif part.startswith('_{'):
            r = p.add_run(part[2:-1]); r.font.subscript = True
        elif part.startswith('^{'):
            r = p.add_run(part[2:-1]); r.font.superscript = True
        elif part.startswith('*'):
            r = p.add_run(part[1:-1]); r.italic = True
        else:
            r = p.add_run(part)
        if size and not part.startswith('`'):
            r.font.size = Pt(size)
        if color:
            r.font.color.rgb = color
        if bold:
            r.bold = True
    return p


def para(text, align=None, size=None, space_after=None, color=None, bold=None, keep=False):
    p = doc.add_paragraph()
    add_runs(p, text, size=size, color=color, bold=bold)
    if align == 'center':
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif align == 'justify':
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    if space_after is not None:
        p.paragraph_format.space_after = Pt(space_after)
    if keep:
        p.paragraph_format.keep_with_next = True
    return p


def body(text):
    return para(text, align='justify')


def bullets(items, style='List Bullet'):
    for it in items:
        p = doc.add_paragraph(style=style)
        add_runs(p, it)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY


def h1(t):
    doc.add_heading(t, level=1)


def h2(t):
    doc.add_heading(t, level=2)


def h3(t):
    doc.add_heading(t, level=3)


def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), fill)
    tcPr.append(shd)


def caption(text, keep=False):
    p = doc.add_paragraph(style='Caption')
    add_runs(p, text, size=9, color=MUTED)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if keep:
        p.paragraph_format.keep_with_next = True
    return p


def table(headers, rows, widths, cap=None, size=8.8, first_col_bold=False, align_cols=None):
    if cap:
        c = caption(cap, keep=True)
        c.paragraph_format.space_after = Pt(3)
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = 'Table Grid'
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, htext in enumerate(headers):
        cell = t.rows[0].cells[i]
        cell.text = ''
        add_runs(cell.paragraphs[0], htext, size=size, bold=True)
        shade(cell, 'DCE4F0')
    for row in rows:
        cells = t.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ''
            add_runs(cells[i].paragraphs[0], str(val), size=size, bold=(first_col_bold and i == 0) or None)
    for row in t.rows:
        for i, w in enumerate(widths):
            row.cells[i].width = Cm(w)
            row.cells[i].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            for p in row.cells[i].paragraphs:
                p.paragraph_format.space_after = Pt(1)
                p.paragraph_format.space_before = Pt(1)
                p.paragraph_format.line_spacing = 1.0
                if align_cols and i in align_cols:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    keep_together(t)
    # repeat header row
    trPr = t.rows[0]._tr.get_or_add_trPr()
    el = OxmlElement('w:tblHeader'); el.set(qn('w:val'), 'true'); trPr.append(el)
    sp = doc.add_paragraph(); sp.paragraph_format.space_after = Pt(4)
    return t


def keep_together(t):
    rows = t.rows
    for k, row in enumerate(rows):
        trPr = row._tr.get_or_add_trPr()
        el = OxmlElement('w:cantSplit'); el.set(qn('w:val'), 'true'); trPr.append(el)
        for cell in row.cells:
            for p in cell.paragraphs:
                p.paragraph_format.keep_with_next = True if k < len(rows) - 1 else p.paragraph_format.keep_with_next
                p.paragraph_format.keep_together = True


def figure(fname, width_cm, cap_text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.space_after = Pt(2)
    p.add_run().add_picture(os.path.join(FIG, fname), width=Cm(width_cm))
    caption(cap_text)


def code(text, cap_text=None, size=8):
    if cap_text:
        caption(cap_text, keep=True).paragraph_format.space_after = Pt(2)
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = t.rows[0].cells[0]
    cell.width = Cm(16.2)
    shade(cell, 'F4F5F7')
    cell.text = ''
    lines = text.strip('\n').split('\n')
    p = cell.paragraphs[0]
    for i, line in enumerate(lines):
        r = p.add_run(line)
        r.font.name = 'Consolas'
        r._element.rPr.rFonts.set(qn('w:eastAsia'), 'Consolas')
        r.font.size = Pt(size)
        if i < len(lines) - 1:
            r.add_break()
    p.paragraph_format.line_spacing = 1.0
    p.paragraph_format.space_after = Pt(2)
    keep_together(t)
    sp = doc.add_paragraph(); sp.paragraph_format.space_after = Pt(4)


def placeholder(title, lines, cap_text, height_lines=6):
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = t.rows[0].cells[0]
    cell.width = Cm(15.5)
    shade(cell, 'F2F2F2')
    tcPr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement('w:tcBorders')
    for side in ('top', 'left', 'bottom', 'right'):
        b = OxmlElement('w:%s' % side)
        b.set(qn('w:val'), 'dashed'); b.set(qn('w:sz'), '12'); b.set(qn('w:color'), 'C00000')
        borders.append(b)
    tcPr.append(borders)
    cell.text = ''
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run('[SCREENSHOT TO INSERT] ' + title); r.bold = True; r.font.color.rgb = RGBColor(0xC0, 0, 0)
    r.font.size = Pt(9.5)
    for line in lines:
        q = cell.add_paragraph(); q.alignment = WD_ALIGN_PARAGRAPH.CENTER
        add_runs(q, line, size=8.8, color=MUTED)
    for _ in range(height_lines):
        cell.add_paragraph()
    keep_together(t)
    for p in cell.paragraphs:
        p.paragraph_format.keep_with_next = True
    caption(cap_text)


def page_break():
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# ================================================================== COVER
for _ in range(5):
    doc.add_paragraph()
para('CEG5101 Modern Computer Networking', align='center', size=13, color=MUTED, space_after=4)
para('CA2: Laboratory Assignment', align='center', size=13, color=MUTED, space_after=24)
para('Anomaly-aware Routing and Blocking Controller', align='center', size=22, bold=True,
     color=HEAD_COLOR, space_after=6)
para('Design, implementation and evaluation on the CEG mesh topology (Ryu / OpenFlow 1.3 / Mininet)',
     align='center', size=11.5, color=MUTED, space_after=48)
para('Group members', align='center', size=11, bold=True, space_after=4)
cover = doc.add_table(rows=1, cols=2)
cover.style = 'Table Grid'
cover.alignment = WD_TABLE_ALIGNMENT.CENTER
for i, htext in enumerate(('Name', 'Student number')):
    c = cover.rows[0].cells[i]; c.text = ''; add_runs(c.paragraphs[0], htext, size=10, bold=True); shade(c, 'DCE4F0')
for _ in range(3):
    cells = cover.add_row().cells
    cells[0].text = '[Name]'; cells[1].text = '[A0XXXXXXX]'
for row in cover.rows:
    row.cells[0].width = Cm(7); row.cells[1].width = Cm(5)
for _ in range(6):
    doc.add_paragraph()
para('Lecturer: Assoc. Prof. Mohan Gurusamy', align='center', size=10.5, color=MUTED, space_after=2)
para('ECE Department, CDE, National University of Singapore', align='center', size=10.5, color=MUTED, space_after=2)
para('Semester 1, AY 2026/27', align='center', size=10.5, color=MUTED, space_after=2)

new = doc.add_section(WD_SECTION.NEW_PAGE)
add_page_number(new)
new.footer.is_linked_to_previous = False

# ================================================================== 1 INTRODUCTION
h1('1  Introduction')
body('This report presents an anomaly-aware routing and blocking controller for the six-switch mesh '
     'network defined in `ceg_mesh_topo.py`. The controller, `solution/anomaly_aware_controller.py`, is a '
     'Ryu application for OpenFlow 1.3. It integrates the two reference programs: topology discovery and '
     'Dijkstra routing from `resilient_controller.py`, and EMA-based anomaly detection with source blocking '
     'from `anomaly_detection.py`. It then adds the parts that neither program provides: a dynamic cost for '
     'every switch-to-switch link driven by the measured load and by the anomaly state, continuous '
     're-optimisation of the installed paths, and automatic recovery once an attack stops. These additions '
     'address the limitations listed in References A and B of the assignment: static routing costs, a purely '
     'relative detection threshold, and no rerouting after a source has been blocked.')

h2('1.1  Experimental setup')
body('All experiments ran on Ubuntu 20.04.6 LTS under WSL2 (16 vCPU, 7 GB RAM) with Mininet 2.3.1b4, '
     'Open vSwitch 2.13.8, Ryu 4.34 (Python 3.8.10), hping3 3.0.0-alpha-2 and iperf 3.7. Every quantitative '
     'result in this report comes from one complete automated run, `solution/results/run4`, produced by '
     '`solution/run_experiment.py` with its default parameters. The script starts the controller, builds the '
     'topology with TCLinks, waits until all 11 inter-switch links have been discovered, and confirms full '
     'connectivity with `pingall` (0 % loss). It then drives the traffic shown in Table 1.')
table(['Phase', 'Time (s)', 'Traffic'],
      [['Baseline', '0 – 30.1', 'Legitimate h1→h6 flow only, plus normal background pings'],
       ['Scenario a', '30.1 – 60.1 attack\n60.1 – 90.2 recovery', '`hping3 --icmp --flood` h2→h3, loads link s2–s3'],
       ['Scenario b', '90.2 – 120.2 attack\n120.2 – 150.3 recovery', '`hping3 --icmp --flood` h2→h6, loads link s2–s6'],
       ['Scenario c', '150.3 – 180.3 attack\n180.3 – 210.4 recovery', '`hping3 --icmp --flood` h5→h6, loads link s5–s6'],
       ['Throughout', '0 – 210.4', 'h1→h6: iperf3 UDP 5 Mbit/s (1200-byte datagrams) and ping every 0.1 s.\n'
        'Normal traffic for the baselines: ping every 1 s on h2→h3, h2→h6, h5→h6, h3→h4 and h4→h1.']],
      [2.4, 4.0, 9.8], cap='Table 1. Timeline of the evaluated run (time 0 = start of the baseline phase).')
body('A constant-rate UDP flow is used for the legitimate traffic because it exposes loss and throughput '
     'directly; TCP would retransmit and back off and so hide short losses. The 10 Hz ping on the same pair '
     'gives per-packet loss and the round-trip time, and the RTT reveals every path change. The following data '
     'were recorded:')
bullets(['**Controller logs, every 2 s:** `link_costs.csv` (rate, utilisation, anomaly flag, cost and '
         'normalised cost of each link), `sources.csv` (rate, baseline, threshold and state of each source IP), '
         '`paths.csv` (path and path cost of each installed flow) and `events.csv` (ANOMALY, BLOCK, REROUTE and '
         'UNBLOCK events).',
         '**Host measurements:** the iperf3 server report every 1 s (throughput and UDP loss of h1→h6), and the '
         'timestamped ping output (`ping -D`) of h1→h6.',
         '**Data-plane evidence:** the h1→h6 path traced once per second from the installed OpenFlow rules, '
         'interface packet counters once per second, and full flow-table dumps before, during and after each '
         'scenario.'])

# ================================================================== 2 TASK 1
h1('2  Task 1: Topology in MiniEdit')
body('The topology of `ceg_mesh_topo.py` was rebuilt in MiniEdit (Figure 1) and saved as '
     '`solution/miniedit.mn`. It contains six Open vSwitch switches s1–s6 with OpenFlow 1.3 enabled, six hosts '
     'h1–h6 (10.0.0.1–10.0.0.6, one per switch), and 17 TCLinks: six host links and 11 switch-to-switch '
     'links. Every link has bw = 40 Mbit/s and the delay given in the topology file. A remote controller c0 '
     'points to 127.0.0.1:6633. With Ryu started as `ryu-manager --observe-links anomaly_aware_controller.py` '
     'and the network run from MiniEdit, `ovs-vsctl show` reports `is_connected: true` for every bridge. The '
     'controller log grows to "Topology: 6 switches, 11 links", which means LLDP discovered every '
     'inter-switch link.')
figure('miniedit.png', 15.5, 'Figure 1. The mesh topology running in MiniEdit (top). Bottom left: the Ryu controller log '
       'reaching 6 switches and 11 links. Bottom right: `ovs-vsctl show` with the bridge connected to the controller.')
body('Figure 2 redraws the topology with the parameters used by the routing logic. The assignment defines '
     'C^{0}_{ij} as "the original link cost from the provided controller". `resilient_controller.py` has a '
     'predefined table (s1–s2 = 5, s2–s3 = 10, s1–s4 = 20, s2–s4 = 8, plus s3–s4 = 15, which is not a link in this '
     'mesh) and a default cost of 10 for every other link, so these are the C^{0} values used (Table 2). The '
     'controller can instead set C^{0} equal to the link delay (`CA2_COST_MODE=delay`); Section 8 discusses the '
     'consequences of that choice. With these costs the h1→h6 flow initially takes s1–s2–s6 (cost 15), and the '
     'next-best path is s1–s5–s6 (cost 20).')
figure('topology_costs.png', 14.5, 'Figure 2. Switch-level view with the base cost C0 and the delay of each link. Blue: initial '
       'h1→h6 path. Orange: its cheapest alternative. Red labels: the link loaded by the flood in each scenario.')
table(['Link', 'Delay (ms)', 'Bandwidth', 'C^{0} (from resilient_controller.py)', 'Role in the experiment'],
      [['s1–s2', '5', '40 Mbit/s', '5 (predefined)', 'h1→h6 initial path'],
       ['s2–s3', '10', '40 Mbit/s', '10 (predefined)', 'flooded in scenario a'],
       ['s1–s4', '8', '40 Mbit/s', '20 (predefined)', ''],
       ['s2–s4', '6', '40 Mbit/s', '8 (predefined)', ''],
       ['s2–s6', '14', '40 Mbit/s', '10 (default)', 'h1→h6 initial path; flooded in scenario b'],
       ['s1–s5', '18', '40 Mbit/s', '10 (default)', 'h1→h6 alternative path'],
       ['s5–s6', '20', '40 Mbit/s', '10 (default)', 'h1→h6 alternative path; flooded in scenario c'],
       ['s4–s5', '15', '40 Mbit/s', '10 (default)', ''],
       ['s2–s5', '12', '40 Mbit/s', '10 (default)', ''],
       ['s3–s6', '7', '40 Mbit/s', '10 (default)', ''],
       ['s3–s5', '9', '40 Mbit/s', '10 (default)', '']],
      [1.6, 1.8, 2.0, 4.6, 6.2], cap='Table 2. Switch-to-switch links (host links: 40 Mbit/s, 15 ms).',
      align_cols=[1, 2])

# ================================================================== 3 OVERVIEW
h1('3  Controller Design Overview')
body('Figure 3 shows the structure of the controller. A monitoring loop runs every 2 s and carries out the '
     'detection and routing logic of Tasks 2–4 in a fixed order. Event handlers deal with new hosts, new flows '
     'and link failures as they occur.')
figure('controller_loop.png', 15.0, 'Figure 3. Control loop and OpenFlow rule layout of anomaly_aware_controller.py.')
bullets(['**Explicit per-pair forwarding.** Instead of MAC learning, every (source IP, destination IP) pair gets '
         'its own priority-10 rule on each switch of its Dijkstra path. Each pair therefore has an explicit '
         'path that can be moved on its own, and the rule counters give per-flow rates.',
         '**Host learning and ARP.** Host locations are learned from ARP and IPv4 packet-ins that arrive on '
         'host-facing ports, i.e. ports that are not part of an LLDP-discovered link. The controller delivers '
         'ARP itself: it sends the packet straight to the target\'s port if the target is known, and otherwise '
         'floods it only to host-facing ports. This replaces the MST flooding of the reference controller and '
         'cannot cause a broadcast storm in the meshed topology.',
         '**Rule priorities and cookies.** Drop rules for blocked sources (5000) override everything. Typed '
         'ICMP counters (11) sit just above forwarding (10), and the table-miss rule (0) sends packets to the '
         'controller. Each rule type has its own cookie, so statistics replies can be classified and stale rules '
         'removed when a switch reconnects.',
         '**Robust link state.** Link failures are taken from OpenFlow PortStatus messages. LLDP '
         '"link deleted" events are ignored because LLDP probes can time out on a congested link that is '
         'still up, and a flood would otherwise appear to "remove" the very link it is congesting.'])

# ================================================================== 4 TASK 2
h1('4  Task 2: Traffic Monitoring, Anomaly Detection and Source Blocking')
h2('4.1  Traffic monitoring')
body('Every 2 s the controller sends an `OFPFlowStatsRequest` and an `OFPPortStatsRequest` to all switches. '
     'It waits 0.5 s for the replies and then evaluates them. The rate of a source IP is the packet-count '
     'increase of its flows divided by the elapsed time, measured **only at the source\'s access switch**. '
     'The reference `anomaly_detection.py` keeps a separate baseline for every (switch, IP) pair, so a flow '
     'that crosses three switches is measured three times. Measuring at the ingress gives exactly one value '
     'per host, taken at the point where the block later takes effect.')
body('**Excluding ICMP Echo Replies.** An ICMP flood makes the victim answer every request, so the victim '
     'sends Echo Replies at the same rate as the flood. If these replies counted as the victim\'s own traffic, '
     'the victim would exceed the threshold and be blocked too. In scenarios b and c that victim is h6, the '
     'destination of the legitimate flow, so a correct-looking detector would cut exactly the traffic it is '
     'meant to protect. An early prototype of our controller did exactly this. The controller therefore '
     'installs two extra priority-11 rules for each (source, destination) pair on the source\'s access switch. '
     'They match ICMP type 8 (Echo Request) and type 0 (Echo Reply) and use the same output action as the '
     'forwarding rule, so forwarding is unchanged but the two message types are counted separately. Echo '
     'Replies are excluded from the source rate, while Echo Requests and all non-ICMP traffic still count. Link '
     'load (Task 3) is measured from port counters and still includes the replies. In run4, h3 sent '
     '41,311 replies per second into s3 during the first second of scenario a, yet its measured source rate '
     'stayed at 1.0 pps (its background ping) and it was never flagged.')

h2('4.2  EMA baseline and anomaly threshold')
body('For each source *s* with measured rate *r*_{s} (packets/s), the baseline *B*_{s} and threshold '
     '*T*_{s} are')
para('*B*_{s} ← 0.3 · *r*_{s} + 0.7 · *B*_{s}          *T*_{s} = max(3 · *B*_{s} , 1000 pps)', align='center')
body('and the source is anomalous if *r*_{s} > *T*_{s}. Three design decisions refine the reference detector:')
bullets(['**Compare first, then update.** Each sample is tested against the baseline before it is folded in, and '
         'an anomalous sample never updates the baseline. Otherwise a sustained flood would raise its own '
         'baseline (baseline poisoning) until it no longer looked anomalous.',
         '**Absolute floor of 1000 pps.** Background pings give baselines of 1–2 pps, so 3 × B alone would '
         'be only 3–6 pps, and a `pingall` or an ARP burst would trigger a block. The floor is far above any '
         'normal ping traffic yet about 60 times below the observed flood rate (≈ 63k pps). For h1, which '
         'carries the 5 Mbit/s flow, the relative term dominates (T = 1574 pps).',
         '**Warm-up.** A source must have three samples (6 s) before it can be flagged, so the first, '
         'unrepresentative sample cannot trigger a block.'],
        style='List Number')
code('''threshold = max(THRESHOLD_MULT * stats['baseline'], MIN_ANOMALY_PPS)      # max(3B, 1000)
if stats['samples'] >= WARMUP_SAMPLES and pps > threshold:
    self._block_ip(ip, pps, stats['baseline'], flow_pps, now)            # baseline left untouched
else:
    stats['baseline'] = EMA_ALPHA * pps + (1 - EMA_ALPHA) * stats['baseline']   # alpha = 0.3
    stats['samples'] += 1''', 'Listing 1. Detection step for one source (from _check_anomalies).')
table(['Source', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'],
      [['Rate (pps)', '523.9', '2.0', '1.0', '1.0', '1.0', '0.0'],
       ['EMA baseline (pps)', '524.8', '1.98', '0.99', '1.00', '0.99', '0.02'],
       ['Threshold (pps)', '1574', '1000', '1000', '1000', '1000', '1000']],
      [3.4, 2.1, 2.1, 2.1, 2.1, 2.1, 2.1],
      cap='Table 3. Source baselines learned from normal traffic, just before the first attack (t = 29.3 s).',
      align_cols=[1, 2, 3, 4, 5, 6], first_col_bold=True)

h2('4.3  Blocking and release')
body('When a source is flagged, the controller installs on **all six switches** a rule matching '
     '`eth_type=IPv4, ipv4_src=<attacker>` with an empty action list (drop), priority 5000 and its own cookie. '
     'This is the same firewall rule as in the reference code. Packets from a blocked source that reach the '
     'controller are also discarded. Because the rule exists on the attacker\'s access switch, the flood is '
     'dropped at its first hop. The drop rule\'s packet counter at that switch then keeps measuring the '
     'attacker\'s rate. Once this rate stays at or below the threshold for three consecutive polls, the drop '
     'rules are deleted and the source is released. Requiring three quiet polls stops a source from being '
     'released during a brief pause in the attack.')

h2('4.4  Results and verification')
table(['Scenario', 'Attacker → victim', 'Detected after flood start', 'Rate at detection', 'Baseline / threshold',
       'IPs blocked', 'Drop-rule counter at ingress (13.8 s into block)'],
      [['a', 'h2 → h3', '1.24 s', '5,708 pps', '1.98 / 1000 pps', '10.0.0.2 only', 's2: 883,740 pkts'],
       ['b', 'h2 → h6', '1.22 s', '4,124 pps', '1.99 / 1000 pps', '10.0.0.2 only', 's2: 854,260 pkts'],
       ['c', 'h5 → h6', '1.20 s', '17,147 pps', '1.00 / 1000 pps', '10.0.0.5 only', 's5: 854,559 pkts']],
      [1.5, 2.0, 2.2, 2.0, 2.4, 2.2, 3.9], cap='Table 4. Detection and blocking in run4.',
      align_cols=[0, 2, 3, 4])
body('In every scenario only the attacker was blocked, at the first poll after the flood began (about '
     '1.2 s). The rate at detection is lower than the true flood rate because the flood started part-way '
     'through the 2-s measurement interval. The drop-rule counters show the real rate, about 62–64k pps. '
     'Three independent observations confirm that the anomalous traffic is no longer forwarded:')
bullets(['**Drop-rule counters (Listing 2).** Almost every flood packet matches the drop rule on the '
         'attacker\'s ingress switch. The other switches count zero, apart from the next-hop switch, which '
         'caught packets already in flight on the link when the rule was installed (s3: 23,076 in a; s6: '
         '1,344 in b and 1,035 in c).',
         '**Interface counters.** In scenario a, s2 receives 44,357 → 57,679 → 63,579 packets/s from h2 in the '
         'first three seconds. Its transmission towards s3 falls from 43,893 to 15,501 and then to 1 packet/s. '
         'For the rest of the attack s2 receives about 63,700 packets/s from h2 while s2→s3 carries about '
         '1 packet/s and s3→h3 about 2 packets/s (background traffic only). Scenarios b and c show the same '
         'pattern (s2→s6 and s5→s6 fall to ≈ 1 packet/s).',
         '**Victim-side links.** Once blocked, the links that carried the flood return to their normal load. '
         'The controller\'s utilisation of s2–s3, s2–s6 and s5–s6 decays to 0 (Section 5.3).'])
code('''s1: cookie=0xca20002, duration=13.774s, n_packets=0,      priority=5000,ip,nw_src=10.0.0.2 actions=drop
s2: cookie=0xca20002, duration=13.780s, n_packets=883740, priority=5000,ip,nw_src=10.0.0.2 actions=drop
s3: cookie=0xca20002, duration=13.785s, n_packets=23076,  priority=5000,ip,nw_src=10.0.0.2 actions=drop
s4: cookie=0xca20002, duration=13.791s, n_packets=0,      priority=5000,ip,nw_src=10.0.0.2 actions=drop
s5: cookie=0xca20002, duration=13.797s, n_packets=0,      priority=5000,ip,nw_src=10.0.0.2 actions=drop
s6: cookie=0xca20002, duration=13.803s, n_packets=1,      priority=5000,ip,nw_src=10.0.0.2 actions=drop''',
     'Listing 2. Drop rules in the flow tables during scenario a (excerpt of run4/flows_during_a.txt; '
     'table and byte fields omitted).', size=7.4)
placeholder('Controller log of scenario a',
            ['Ryu terminal showing [ANOMALY] 10.0.0.2 … links=s2-s3, [BLOCK] 10.0.0.2 blocked on all switches,',
             'the following [REROUTE] lines and, after the flood stops, [UNBLOCK] 10.0.0.2.',
             'No other IP (in particular 10.0.0.3) may appear in a BLOCK line.'],
            'Figure 4. Controller output for scenario a: detection, blocking, rerouting and release of h2.')
placeholder('Drop rule installed by the controller',
            ['mininet> sh ovs-ofctl -O OpenFlow13 dump-flows s2 | grep priority=5000   (and the same for s3),',
             'run twice during the flood: the nw_src=10.0.0.2 actions=drop rule with n_packets increasing',
             'on s2 and only a small, constant count on s3.'],
            'Figure 5. The priority-5000 drop rule for 10.0.0.2 and its packet counter during the flood.')

# ================================================================== 5 TASK 3
h1('5  Task 3: Dynamic Link-Cost Update')
h2('5.1  Cost model')
body('Every 2 s, each switch-to-switch link (*i*, *j*) receives the cost of Reference C:')
para('*C*_{ij}(*t*) = *C*^{0}_{ij} + α · *u*_{ij}(*t*) + β · *A*_{ij}(*t*),          '
     '*u*_{ij}(*t*) = min(1, *R*_{ij}(*t*) / *R*^{max}_{ij})', align='center')
bullets(['**Current rate** *R*_{ij}(*t*)**.** Taken from the `tx_bytes` port counters at both ends of the '
         'link. Each direction\'s rate (8·Δbytes/Δt) is smoothed with weight 0.5 on the newest sample, and '
         'the busier direction is used, since a link is as congested as its busier direction. Port counters '
         'include every packet (data, replies, control traffic), so they measure the real load, not just '
         'the flows the controller installed.',
         '**Reference rate** *R*^{max}_{ij} = 40 Mbit/s, the TCLink bandwidth of every link.',
         '**Base cost** *C*^{0}_{ij}, the static cost of the provided controller (Table 2).',
         '**Anomaly flag** *A*_{ij}(*t*)**.** When a source is blocked, every link on the installed path of each '
         'of its flows that carries at least 20 % of its rate is set to 1. The flag stays at 1 while the '
         'source is blocked and is cleared when it is released. The 20 % share selects the flood flow and '
         'ignores the attacker\'s low-rate background flows, so only links that actually carried the attack '
         'are penalised. In run4 the flagged links were exactly s2–s3, s2–s6 and s5–s6.',
         '**Normalised cost** *C*_{ij}/*C*^{0}_{ij} equals 1 on an idle, clean link and reaches at most '
         '1 + (α + β)/*C*^{0} = 4 for *C*^{0} = 10. It is the quantity plotted in Figure 6.'])
code('''for u, v in links:                                          # every switch-to-switch link, once
    fwd, rev = self.link_rate.get((u, v), 0.0), self.link_rate.get((v, u), 0.0)
    utilisation = min(1.0, max(fwd, rev) / LINK_CAPACITY_BPS)       # R / Rmax, Rmax = 40 Mbit/s
    anomaly = 1 if (u, v) in anomaly_links else 0                   # A_ij from blocked sources
    cost = self.base_cost[(u, v)] + COST_ALPHA * utilisation + COST_BETA * anomaly
    self.graph[u][v] = self.graph[v][u] = cost                      # weights used by Dijkstra''',
     'Listing 3. Cost update (simplified from _update_costs).')

h2('5.2  Choice of α and β')
bullets(['**α = 10.** A saturated link costs C^{0} + 10, i.e. about twice a default link. Load alone can move '
         'traffic, but only under substantial congestion. For h1→h6, load on s2–s6 alone would trigger a '
         'reroute when 6.3 + 10 + 10·*u* > 20 + 2, i.e. at *u* > 0.57 (≈ 23 Mbit/s). The 2.0 margin is the '
         'rerouting hysteresis of Section 6.1, so ordinary fluctuations do not move flows.',
         '**β = 20.** β is larger than the cost difference between the primary and alternative paths in this '
         'topology (for h1→h6: 20 − 15 = 5). A link with an active anomaly is therefore always avoided when '
         'an alternative exists. Unlike removing the link, the penalty is finite: if the flagged link is the '
         'only way to a destination, it is still used, so connectivity is preserved as the assignment '
         'requires.'])

h2('5.3  Results')
table(['Scenario', 'Link', 'C^{0}', 'Cost before (norm.)', 'Peak util.', 'Peak cost (norm.)',
       'While blocked (norm.)', 'After release'],
      [['a', 's2–s3', '10', '10.00 (1.00)', '0.089', '30.89 (3.09)', '30.00 (3.00)', '10.00 at +7.2 s'],
       ['b', 's2–s6', '10', '11.30 (1.13)', '0.200', '32.00 (3.20)', '30.00 (3.00)', '10.00 at +7.2 s, then 11.09'],
       ['c', 's5–s6', '10', '10.00 (1.00)', '0.076', '30.76 (3.08)', '30.00 (3.00)', '10.00 at +7.2 s']],
      [1.5, 1.4, 1.0, 2.3, 1.5, 2.4, 2.4, 3.6],
      cap='Table 5. Dynamic cost of the flooded links (release time measured from the end of the flood).',
      align_cols=[0, 2, 4])
body('Figure 6 (Section 7) plots these costs against time. Four observations follow:')
bullets(['**The load term and the anomaly term act on different time scales.** At the first poll after the '
         'attack begins, both terms rise and the cost jumps to 30.8–32.0. The drop rule removes the flood '
         'from the link in the same poll, so the measured load then decays geometrically because of the '
         'smoothing (s2–s6: *u* = 0.200, 0.174, 0.087, 0.044, …). The β term, however, holds the cost at '
         '30.0 (normalised 3.0) until the source is released. This plateau is the controller\'s memory of the '
         'attack.',
         '**The peak load is modest because the flood is blocked quickly.** In the first second the flood '
         'pushed about 44k packets/s (≈ 15 Mbit/s with 42-byte frames, *u* ≈ 0.37) onto s2–s3. It lasted only '
         'about 1.2 s of a 2-s window, however, so the smoothed sample peaks at 0.09. A flood is handled by '
         'detection and the β term. The α term is meant for sustained congestion caused by legitimate traffic.',
         '**The load term follows the legitimate traffic.** Before scenario b, s2–s6 is at 1.13 and s1–s2 at '
         '1.26 because they carry the 5 Mbit/s h1→h6 flow (*u* = 0.13). When the flow moves away, s1–s5 rises '
         'from 1.00 to 1.13, and after the flow returns, s2–s6 climbs back towards 1.13 (11.09 six seconds after the release).',
         '**Costs recover automatically.** The drop rule keeps counting the attacker. Once three polls in a '
         'row see no anomalous traffic, the source is released 7.2 s after the flood stops (one poll that '
         'still contains the end of the flood plus 3 × 2 s). A_{ij} is then cleared and the link returns to '
         'C^{0} in the same poll, in all three scenarios.'])

# ================================================================== 6 TASK 4
h1('6  Task 4: Rerouting of Legitimate Traffic')
h2('6.1  Routing and rerouting mechanism')
bullets(['**Path computation.** Dijkstra\'s algorithm (from `resilient_controller.py`) runs on the graph '
         'weighted by the current *C*_{ij}(*t*). A new flow is routed when its first packet arrives.',
         '**Periodic re-optimisation.** After every cost update the controller recomputes the best path of '
         'every installed flow and moves the flow only if the new path is cheaper by more than a margin of '
         '2.0. This hysteresis prevents flapping between near-equal paths. In particular, a flow does not '
         'bounce back just because its own load has made its new path slightly more expensive. Flows of '
         'blocked sources are not rerouted.',
         '**Make-before-break installation.** Rules are written from the destination switch back towards the '
         'source, so a packet never reaches a switch that has no rule yet. A rule whose output port changes is '
         'modified in place (`OFPFC_MODIFY_STRICT`, which keeps its counters for rate measurement). Rules on '
         'switches that are no longer on the path are deleted last.'])
code('''best = self.dijkstra(src_host.dpid, dst_host.dpid)              # under the current dynamic costs
current_cost, best_cost = self._path_cost(flow['path']), self._path_cost(best)
if best_cost + REROUTE_MARGIN < current_cost:                     # hysteresis, margin = 2.0
    self._install_path(src_ip, dst_ip, best)                      # dst-to-src, MODIFY where possible
    self._event('REROUTE', ...)''', 'Listing 4. Reroute decision for one installed flow (from _reroute_flows).')

h2('6.2  Initial state of the h1→h6 flow')
body('Before any anomaly, h1→h6 follows **s1 → s2 → s6 → h6**, both according to the controller and as traced '
     'from the switches\' flow tables. Its path cost is 15 from C^{0} alone, or 17.59 including its own load '
     '(s1–s2 = 6.30, s2–s6 = 11.30). During the baseline it delivers 5.00 Mbit/s with 0 % UDP loss and 0 % '
     'ping loss, and its RTT is 98.5 ms, matching 2 × (15 + 5 + 14 + 15) ms of link delays. Table 6 lists the '
     'candidate paths and their costs in each phase. The chosen path is always the cheapest one in its column.')
table(['h1→h6 path', 'C^{0} sum', 'Baseline', 'Scenario a', 'Scenario b', 'Scenario c'],
      [['s1–s2–s6', '15', '**17.59**', '**17.60**', '38.30', '**17.59**'],
       ['s1–s5–s6', '20', '20.00', '20.00', '**20.00**', '40.57'],
       ['s1–s2–s3–s6', '25', '26.30', '47.03', '26.30', '26.30'],
       ['s1–s2–s5–s6', '25', '26.30', '26.30', '26.30', '46.87'],
       ['s1–s5–s3–s6', '30', '30.00', '30.00', '30.00', '30.00']],
      [3.6, 1.8, 2.3, 2.3, 2.3, 2.3],
      cap='Table 6. Cost of the h1→h6 candidate paths at the first poll after each attack is detected '
          '(baseline: t = 25 s). Bold: the selected path.', align_cols=[1, 2, 3, 4, 5])

h2('6.3  Behaviour in each scenario')
table(['Requirement', 'Scenario a: h2→h3, s2–s3', 'Scenario b: h2→h6, s2–s6', 'Scenario c: h5→h6, s5–s6'],
      [['a. Load and cost of the link', 'u 0 → 0.089; C 10 → 30.89, then 30.00',
        'u 0.13 → 0.200; C 11.30 → 32.00, then 30.00', 'u 0 → 0.076; C 10 → 30.76, then 30.00'],
       ['b. Detected and blocked', 'h2 at +1.24 s; only h2 blocked', 'h2 at +1.22 s; only h2 blocked',
        'h5 at +1.20 s; only h5 blocked'],
       ['c. h1→h6 rerouted?', 'No: s2–s3 is not on its path; 17.60 < 20.00',
        'Yes, at +1.22 s: s1–s2–s6 (38.30) → s1–s5–s6 (20.00); data plane at +1.8 s',
        'No: the penalty falls on the alternative path (40.57); 17.59 is still cheapest'],
       ['d. Path before / during', 's1–s2–s6 / s1–s2–s6', 's1–s2–s6 / s1–s5–s6', 's1–s2–s6 / s1–s2–s6'],
       ['d. Throughput during (mean / min)', '5.00 / 4.99 Mbit/s', '4.99 / 4.67 Mbit/s', '5.00 / 4.99 Mbit/s'],
       ['d. Packet loss during', 'UDP 0 %; ping 0 / 311', 'UDP 34 datagrams, all before the block (0.21 %); ping 0 / 309',
        'UDP 0 %; ping 0 / 311'],
       ['e. Connectivity kept?', 'Yes, no ping lost', 'Yes, no ping lost', 'Yes, no ping lost'],
       ['f. Recovery', 'h2 released 7.2 s after the flood; s2–s3 back to 10; h1→h6 never moved',
        'h2 released 7.2 s after the flood; s2–s6 back to 10; h1→h6 back on s1–s2–s6 in the same poll '
        '(data plane +7.8 s)', 'h5 released 7.2 s after the flood; s5–s6 back to 10; h1→h6 never moved']],
      [3.2, 4.3, 4.6, 4.3], cap='Table 7. Requirements a–f of Task 4 for each scenario (times relative to the '
                                'start of the flood unless stated).', first_col_bold=True)
body('**Scenario a (link s2–s3).** The flagged link is not on the h1→h6 path. That path stays the cheapest '
     '(17.60 against 20.00), so the controller correctly leaves the flow untouched: its throughput, loss and RTT '
     'do not change at all. The controller does reroute every flow that did cross s2–s3: h1→h3 and h3→h1 move '
     'from s1–s2–s3 (37.03) to s1–s5–s3 (20.00), and h3→h2, h3→h4 and h4→h3 move onto paths via s5. Rerouting '
     'is therefore selective. A flow moves only when its own path cost changes.')
body('**Scenario b (link s2–s6, shared with h1→h6).** This is the case the assignment targets. At the first '
     'poll after the flood starts (+1.22 s), h2 is blocked, s2–s6 is flagged, and the h1→h6 path cost rises to '
     '6.30 + 32.00 = 38.30. Dijkstra picks s1–s5–s6 (20.00) over s1–s2–s3–s6 (26.30), and the flow is moved in '
     'the same poll. h6→h1, h6→h2, h4→h6 and h6→h4 are moved as well. During the attack, the h1→h6 flow\'s own '
     'load raises the new path to 22.57, while the next-best path s1–s2–s3–s6 costs 25.01. The 2.44 gap '
     'exceeds the margin, so the path stays stable for the whole 36 s. When h2 is released, s2–s6 drops to '
     '10, s1–s2–s6 becomes 15.00 against 22.59 for the current path, and the flow returns in the same poll. '
     'The only loss of the entire run occurred in this scenario: 34 UDP datagrams, all in the ≈ 1.2 s before '
     'the block took effect (analysed in Section 7.3).')
body('**Scenario c (link s5–s6).** This flood hits the alternative path rather than the active one. '
     's1–s5–s6 rises to 40.57 while the active path s1–s2–s6 stays at 17.59, so h1→h6 is not moved. The only '
     'flow rerouted is h6→h5 (s6–s5 → s6–s3–s5). The scenario also shows that the costs keep the controller '
     'ready for a combined failure: if s2–s6 were degraded at the same time, the next choice would be '
     's1–s2–s3–s6 (26.30), not the flagged s1–s5–s6.')

# ================================================================== 7 TASK 5
h1('7  Task 5: Performance Evaluation')
body('Figures 6–8 are the three required plots. Figure 9 adds the RTT, which makes path changes visible. '
     'Grey bands mark the three floods, and dotted lines mark the two reroutes of h1→h6 in scenario b. Table 8 '
     'summarises each phase.')
figure('fig1_normalized_link_cost.png', 16.0, 'Figure 6. Dynamic link cost (normalised, C(t)/C0) against time for the flooded links '
       'and for s1–s5, which carries h1→h6 during scenario b.')
figure('fig2_packet_loss.png', 16.0, 'Figure 7. Packet loss of h1→h6 against time: UDP loss per iperf3 interval and ping loss per second.')
figure('fig3_throughput.png', 16.0, 'Figure 8. Throughput of the h1→h6 UDP flow against time.')
figure('fig4_rtt.png', 16.0, 'Figure 9. Round-trip time of h1→h6 (ping every 0.1 s). The step to 137 ms is the move to '
       's1–s5–s6.')
table(['Scenario', 'Phase', 'h1→h6 path', 'Throughput mean / min (Mbit/s)', 'UDP loss', 'Ping loss', 'RTT mean'],
      [['a', 'before', 's1–s2–s6', '5.00 / 4.99', '0 %', '0 / 90', '98.6 ms'],
       ['a', 'during', 's1–s2–s6', '5.00 / 4.99', '0 %', '0 / 311', '98.5 ms'],
       ['a', 'after', 's1–s2–s6', '5.00 / 4.99', '0 %', '0 / 100', '98.5 ms'],
       ['b', 'before', 's1–s2–s6', '5.00 / 4.99', '0 %', '0 / 90', '98.5 ms'],
       ['b', 'during', 's1–s5–s6 from +1.2 s', '4.99 / 4.67', '0.21 % (34 datagrams)', '0 / 309', '133.9 ms*'],
       ['b', 'after', 's1–s2–s6', '5.00 / 4.99', '0 %', '0 / 100', '98.5 ms'],
       ['c', 'before', 's1–s2–s6', '5.00 / 4.99', '0 %', '0 / 90', '98.5 ms'],
       ['c', 'during', 's1–s2–s6', '5.00 / 4.99', '0 %', '0 / 311', '98.5 ms'],
       ['c', 'after', 's1–s2–s6', '5.00 / 4.99', '0 %', '0 / 100', '98.6 ms']],
      [1.5, 1.4, 3.3, 3.1, 2.8, 1.7, 1.9],
      cap='Table 8. h1→h6 before (10 s to 1 s before the flood), during the flood, and after it (10–20 s after the '
          'flood). *136.6 ms once on s1–s5–s6.', align_cols=[0, 1, 3, 4, 5, 6])

h2('7.1  Routing cost')
body('Before any anomaly, only links that carry the legitimate flow sit above 1: s1–s2 at 1.26 and s2–s6 at '
     '1.13. During each flood, the cost of the flooded link jumps to 3.08–3.20 at the first poll, then relaxes '
     'to a 3.00 plateau as the load term decays to zero and the anomaly term remains (Section 5.3). After the '
     'flood the link returns to 1.00 within 7.2 s. The other links react only to the traffic that is moved '
     'onto them: s1–s5 rises to 1.13 while it carries h1→h6 in scenario b. The cost thus captures both '
     'components the assignment asks for: current load and anomaly state.')
h2('7.2  Path selection')
body('The h1→h6 path changes exactly when a penalised link lies on it (scenario b) and stays put when the '
     'penalised link is elsewhere (a, c). Figure 9 shows the change: the RTT steps from 98.5 ms to 136.6 ms '
     'at +1.2 s and returns at release. The single intermediate samples (108 ms and 120 ms) belong to probes in '
     'flight during the switch. The 38 ms increase is the price of the detour. s1–s5 (18 ms) and s5–s6 (20 ms) '
     'have the controller\'s default C^{0} = 10 even though they are the slowest links in the mesh, so the cost '
     'metric does not reflect delay. Section 8 discusses this trade-off.')
h2('7.3  Packet loss')
body('Of 2,102 ping probes, none was lost during the whole run, and of 109,255 UDP datagrams, 34 (0.031 %) '
     'were lost. All 34 were lost in the first ≈ 1.2 s of scenario b, between the start of the flood and the '
     'installation of the drop rule. During that window the flood shares two links with the legitimate flow: '
     's2–s6, which rerouting can avoid, and the victim\'s access link s6→h6, which it cannot, because h6 is '
     'the destination of both flows. Diagnostic counters sampled every second during the run show that the egress '
     'queue of s6-eth1 (towards h6) dropped 760 packets between 89.5 s and 91.5 s (and otherwise only 18, at the '
     'onset of scenario c, without any UDP or ping loss), while h6\'s UDP receive-buffer errors stayed at 0. The loss therefore happened in the network queue in front of the victim, not '
     'in the receiving host. This explains why rerouting and blocking are both needed. Rerouting protects '
     'legitimate traffic on shared transit links, but only blocking at the attacker\'s ingress relieves the '
     'victim\'s own access link. Figure 7 shows this loss in the 89–91 s bins because iperf3\'s 1-s reporting '
     'grid lags the experiment clock by about 0.5 s, as the server starts its interval timer only after the '
     'test set-up. The interface counters show no flood traffic before 90.2 s. The return to s1–s2–s6 at 127.4 s lost no '
     'packets, and the queue drops on s6-eth1 fully account for the loss around the first switch at 91.4 s. This is '
     'consistent with the make-before-break rule installation.')
h2('7.4  Throughput')
body('The legitimate flow keeps its full 5.00 Mbit/s in every phase. The only dip is the 4.67 Mbit/s interval '
     'that contains the loss described above. One interval at the return to s1–s2–s6 reads 5.10 Mbit/s '
     '(531 datagrams instead of 521). When the flow moves from the 68 ms path back to the 49 ms path, '
     'datagrams sent on the new, shorter path overtake those still in flight on the old one, so two streams '
     'arrive in the same interval. iperf3 accordingly reports 15 out-of-order datagrams for the whole run: '
     'reordering at the path switch, not loss.')

# ================================================================== 8 DISCUSSION
h1('8  Discussion and Limitations')
bullets(['**Detection latency is bounded by polling.** With a 2-s poll the worst-case detection delay is about '
         '2.5 s; here it was 1.2 s. Until then the flood reaches the victim, which caused the only loss of the '
         'run. Shorter polling, or OpenFlow meters that rate-limit each access port in the data plane, would '
         'shrink this window at the cost of more control traffic.',
         '**Fixed absolute floor.** The 1000-pps floor removes false positives from low-rate baselines but '
         'must be tuned to the network. A low-and-slow attack, or a distributed attack in which every source '
         'stays below the floor, would not be detected. Detection is also per source IP, so a spoofing '
         'attacker could evade an IP block. Blocking by access port would be more robust.',
         '**Scope of the Echo-Reply exclusion.** Excluding replies prevents the victim from being blocked, '
         'but a flood consisting only of Echo Replies (e.g. a reflection attack) would not count against its '
         'sender. Its load would still raise the link costs through the α term.',
         '**Coarse blocking.** The whole source IP is blocked, including its legitimate traffic (h2\'s background '
         'pings are also dropped during scenarios a and b). Blocking only the offending protocol or destination '
         'would reduce this collateral damage.',
         '**The base cost does not encode delay.** Following the assignment, C^{0} comes from the provided controller, '
         'where most links share the default cost of 10. The detour in scenario b therefore adds 38 ms of RTT. '
         'With the delay-based option (`CA2_COST_MODE=delay`), h1→h6 would start on s1–s2–s6 (cost 19) and '
         'during scenario b would move to s1–s2–s3–s6 (5 + 10 + 7 = 22, RTT ≈ 104 ms) instead of s1–s5–s6 '
         '(38). This is a calculation from the cost model; run4 used the controller costs.',
         '**Conservative anomaly memory.** A_{ij} stays at 1 for as long as the source is blocked, although '
         'the flood is already dropped at the ingress. This keeps legitimate traffic away from links that an '
         'attacker is targeting (useful if the attacker changes address), but it also keeps h1→h6 on the '
         'longer path for about 37 s. A decaying anomaly term would trade some of that safety for a faster '
         'return.',
         '**Emulation environment.** All switches, hosts and the controller share one virtual machine. In '
         'run4 the controller kept a regular 2.00 s polling period throughout (2.001–2.008 s between samples), '
         'but on a weaker host a flood can compete with the controller for CPU and delay its reaction.'])

# ================================================================== 9 CONCLUSION
h1('9  Conclusion')
body('The integrated controller meets the objectives of CA2 on the CEG mesh topology. It learns per-source '
     'EMA baselines from normal ping traffic and detects each ICMP flood at the first poll after it starts '
     '(1.2 s). It blocks only the attacker, never the victim, thanks to the separate Echo-Reply counters, and '
     'drops the flood at the attacker\'s first hop. The dynamic cost C = C^{0} + α·R/R^{max} + β·A reflects both '
     'the measured load and the anomaly state. The resulting rerouting is selective: in the scenario where the '
     'attack shares a link with the legitimate h1→h6 flow, the flow moves to s1–s5–s6 in the same poll in which '
     'the attacker is blocked, and in the other two scenarios it correctly stays on its path. Throughout all '
     'three attacks the legitimate flow kept 5.00 Mbit/s and lost no ping probe. Its only loss, 0.031 % of UDP '
     'datagrams, occurred on the victim\'s access link before the block took effect. Once each attack stopped, '
     'the source was released, the link cost returned to C^{0}, and the original path was restored automatically '
     'within 7.2 s.')

# ================================================================== APPENDIX
h1('Appendix A  Controller parameters')
table(['Parameter', 'Value', 'Purpose'],
      [['POLL_INTERVAL / STATS_WAIT', '2.0 s / 0.5 s', 'monitoring period / wait for statistics replies'],
       ['EMA_ALPHA', '0.3', 'weight of the newest sample in the baseline (as in anomaly_detection.py)'],
       ['THRESHOLD_MULT / MIN_ANOMALY_PPS', '3.0 / 1000 pps', 'anomaly threshold max(3·B, 1000 pps)'],
       ['WARMUP_SAMPLES', '3', 'samples before a source can be flagged'],
       ['RECOVERY_POLLS', '3', 'quiet polls before a blocked source is released'],
       ['HEAVY_FLOW_SHARE', '0.2', 'flows with ≥ 20 % of the attacker\'s rate mark their links (A = 1)'],
       ['COST_ALPHA / COST_BETA', '10 / 20', 'weights of the load and anomaly terms'],
       ['LINK_CAPACITY_BPS (R^{max})', '40 Mbit/s', 'TCLink bandwidth'],
       ['LOAD_SMOOTHING', '0.5', 'weight of the newest link-rate sample'],
       ['REROUTE_MARGIN', '2.0', 'hysteresis for moving an installed flow'],
       ['DROP / ICMP counter / FWD priority', '5000 / 11 / 10', 'OpenFlow rule priorities']],
      [5.4, 3.0, 7.8], cap='Table 9. Parameters at the top of anomaly_aware_controller.py.')

h1('Appendix B  Files and reproduction')
table(['File', 'Content'],
      [['solution/anomaly_aware_controller.py', 'integrated controller (Tasks 2–4)'],
       ['solution/miniedit.mn', 'MiniEdit topology (Task 1)'],
       ['solution/run_experiment.py', 'automated experiment: topology, traffic, attacks, measurements'],
       ['solution/summarize_run.py, plot_results.py, run_data.py', 'per-scenario summary and the plots of Section 7'],
       ['solution/results/run4/', 'raw data of the evaluated run (controller CSVs, iperf3, ping, flow tables)']],
      [7.0, 9.2], cap='Table 10. Submitted files.')
code('''# automated run (about 4 minutes), results in results/run4
cd ~/CA2/solution && sudo python3 run_experiment.py --out results/run4
python3 summarize_run.py results/run4 > results/run4/summary.md
python3 plot_results.py results/run4

# manual run - terminal 1 (in solution/), then terminal 2 (in ceg_code/)
ryu-manager --observe-links anomaly_aware_controller.py
sudo mn --switch ovsk --controller remote --custom ceg_mesh_topo.py --topo meshTopo --link tc''',
     'Listing 5. Commands used to reproduce the results.')

# open in Word 2013+ mode instead of compatibility mode
settings = doc.settings.element
compat = settings.find(qn('w:compat'))
if compat is None:
    compat = OxmlElement('w:compat'); settings.append(compat)
for old in compat.findall(qn('w:compatSetting')):
    if old.get(qn('w:name')) == 'compatibilityMode':
        compat.remove(old)
cs = OxmlElement('w:compatSetting')
cs.set(qn('w:name'), 'compatibilityMode'); cs.set(qn('w:uri'), 'http://schemas.microsoft.com/office/word'); cs.set(qn('w:val'), '15')
compat.append(cs)

doc.save(OUT)
print('saved', OUT)
