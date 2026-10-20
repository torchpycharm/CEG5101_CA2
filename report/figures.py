import sys, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
OUT = sys.argv[1]
INK, MUTED, GRID = '#222222', '#6b6b6b', '#c9c9c9'
BLUE, ORANGE, RED = '#2a6fd6', '#e8902a', '#d23c3c'
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10})

# ---------------- Figure: topology with C0 and delays ----------------
pos = {'s1': (0, 1), 's2': (1.6, 1), 's3': (3.2, 1), 's4': (0, 0), 's5': (1.6, 0), 's6': (3.2, 0)}
hostpos = {'h1': (0, 1.55), 'h2': (1.6, 1.55), 'h3': (3.2, 1.55), 'h4': (0, -0.55), 'h5': (1.6, -0.55), 'h6': (3.2, -0.55)}
links = {('s1','s2'): (5, 5), ('s2','s3'): (10, 10), ('s4','s5'): (10, 15), ('s5','s6'): (10, 20),
         ('s1','s4'): (20, 8), ('s2','s5'): (10, 12), ('s3','s6'): (10, 7), ('s1','s5'): (10, 18),
         ('s2','s4'): (8, 6), ('s2','s6'): (10, 14), ('s3','s5'): (10, 9)}
label_frac = {('s1','s5'): 0.27, ('s2','s4'): 0.27, ('s2','s6'): 0.27, ('s3','s5'): 0.27}
primary = {('s1','s2'), ('s2','s6')}
backup = {('s1','s5'), ('s5','s6')}
attacked = {('s2','s3'): 'a', ('s2','s6'): 'b', ('s5','s6'): 'c'}

fig, ax = plt.subplots(figsize=(7.6, 4.6))
for (u, v), (c0, d) in links.items():
    (x1, y1), (x2, y2) = pos[u], pos[v]
    if (u, v) in primary:
        ax.plot([x1, x2], [y1, y2], color=BLUE, lw=4.2, zorder=2, solid_capstyle='round')
    elif (u, v) in backup:
        ax.plot([x1, x2], [y1, y2], color=ORANGE, lw=3.2, zorder=2, ls=(0, (4, 2)))
    else:
        ax.plot([x1, x2], [y1, y2], color='#9a9a9a', lw=1.5, zorder=1)
    f = label_frac.get((u, v), 0.5)
    lx, ly = x1 + (x2 - x1) * f, y1 + (y2 - y1) * f
    txt = 'C0=%d | %dms' % (c0, d)
    ax.text(lx, ly, txt, fontsize=7.6, ha='center', va='center', color=INK, zorder=4,
            bbox=dict(boxstyle='round,pad=0.18', fc='white', ec='none', alpha=0.95))
    if (u, v) in attacked:
        g, dy = {('s2','s3'): (0.72, 0.13), ('s2','s6'): (0.66, 0.15), ('s5','s6'): (0.72, -0.15)}[(u, v)]
        ax.text(x1 + (x2 - x1) * g, y1 + (y2 - y1) * g + dy, '(%s)' % attacked[(u, v)],
                fontsize=9.5, color=RED, fontweight='bold', ha='center', va='center', zorder=5)
for h, (x, y) in hostpos.items():
    s = 's' + h[1]
    ax.plot([x, pos[s][0]], [y, pos[s][1]], color=GRID, lw=1.2, zorder=1)
    ax.text(x, y, '%s\n10.0.0.%s' % (h, h[1]), ha='center', va='center', fontsize=8, color=INK, zorder=3,
            bbox=dict(boxstyle='round,pad=0.3', fc='#f3f3f3', ec='#9a9a9a', lw=0.8))
for s, (x, y) in pos.items():
    ax.text(x, y, s, ha='center', va='center', fontsize=10, fontweight='bold', color='white', zorder=6,
            bbox=dict(boxstyle='circle,pad=0.35', fc='#3b3b3b', ec='none'))
ax.plot([], [], color=BLUE, lw=4, label='h1→h6 initial path s1–s2–s6 (C0 sum 15)')
ax.plot([], [], color=ORANGE, lw=3, ls=(0, (4, 2)), label='alternative s1–s5–s6 (C0 sum 20)')
ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.0), ncol=2, frameon=False, fontsize=8.2)
ax.text(1.6, -0.98, '(a) (b) (c): link loaded by the flood in scenario a, b, c.   Every link is a TCLink with bw = 40 Mbit/s; host links have 15 ms delay.',
        fontsize=7.6, color=MUTED, ha='center', va='center')
ax.set_xlim(-0.45, 3.65); ax.set_ylim(-1.05, 1.85); ax.axis('off')
fig.tight_layout()
fig.savefig(OUT + '/topology_costs.png', dpi=220, bbox_inches='tight', facecolor='white')
plt.close(fig)

# ---------------- Figure: controller control loop ----------------
fig, ax = plt.subplots(figsize=(7.6, 5.0))
ax.set_xlim(-0.1, 10); ax.set_ylim(0.4, 9.95); ax.axis('off')
def box(x, y, w, h, title, body, fc='#ffffff', ec='#555555'):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02,rounding_size=0.15', fc=fc, ec=ec, lw=1.1))
    ax.text(x + 0.15, y + h - 0.2, title, fontsize=8.8, fontweight='bold', va='top', color=INK)
    ax.text(x + 0.15, y + h - 0.62, body, fontsize=7.6, va='top', color=INK, linespacing=1.35)
def arrow(x1, y1, x2, y2, color='#555555', style='-|>', ls='-'):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=11, color=color, lw=1.1, ls=ls))
# periodic loop (left column)
steps = [
    ('1  Collect statistics', 'OFPFlowStatsRequest + OFPPortStatsRequest\nto every switch, wait 0.5 s for replies'),
    ('2  Estimate rates', 'per-source pps at its access switch (Echo Reply\nexcluded); per-link bit/s from port tx_bytes'),
    ('3  Detect & block', 'EMA baseline B; anomalous if r > max(3B, 1000 pps)\n→ drop rule (prio 5000) on all switches, A_ij = 1'),
    ('4  Release', 'drop-rule counter ≤ threshold for 3 polls\n→ delete drop rules, A_ij = 0'),
    ('5  Update link costs', 'C_ij = C0_ij + α·R_ij/Rmax + β·A_ij\n(α = 10, β = 20, Rmax = 40 Mbit/s)'),
    ('6  Reroute', 'Dijkstra for every installed flow; move it if\nnew cost + 2.0 < current cost'),
]
x, w, h = 0.45, 5.15, 1.25
ys = [8.45 - i * 1.55 for i in range(len(steps))]
for (t, b), y in zip(steps, ys):
    box(x, y, w, h, t, b, fc='#f6f8fc', ec='#5b7db8')
for y1, y2 in zip(ys, ys[1:]):
    arrow(x + w / 2, y1, x + w / 2, y2 + h)
# loop-back arrow
lx = x - 0.18
ax.plot([x, lx, lx], [ys[-1] + h / 2, ys[-1] + h / 2, ys[0] + h / 2], color='#5b7db8', lw=1.1)
arrow(lx, ys[0] + h / 2, x, ys[0] + h / 2, color='#5b7db8')
ax.text(lx - 0.17, (ys[0] + ys[-1]) / 2 + h / 2, 'repeat every 2 s', rotation=90, fontsize=7.8, color='#5b7db8', va='center', ha='center')
# event-driven column
box(6.2, 6.75, 3.5, 2.95, 'Event-driven handlers',
    'PacketIn (ARP / IPv4):\n learn host IP → (switch, port);\n ARP delivered by controller;\n new flow → Dijkstra path,\n rules installed dst → src\nPortStatus (link down):\n remove link, reroute flows', fc='#fbf7f0', ec='#c08a3e')
box(6.2, 3.55, 3.5, 2.6, 'Open vSwitch s1–s6 (OF 1.3)',
    'prio 5000  drop  ipv4_src = attacker\nprio 11    per-(src,dst) ICMP type 8 / 0\n           counters at source switch\nprio 10    per-(src,dst) forwarding\nprio 0     table-miss → controller', fc='#f4f4f4', ec='#777777')
box(6.2, 0.55, 3.5, 2.4, 'CSV logs (every poll)',
    'link_costs.csv  rate, util, A, C, C/C0\nsources.csv     pps, baseline, state\npaths.csv       path + path cost\nevents.csv      ANOMALY / BLOCK /\n                REROUTE / UNBLOCK', fc='#ffffff', ec='#999999')
arrow(5.6, ys[0] + 0.6, 6.2, 5.6, color='#777777')   # stats request
arrow(6.2, 5.0, 5.6, ys[1] + 0.6, color='#777777')   # replies
arrow(5.6, ys[2] + 0.5, 6.2, 4.6, color=RED)          # drop rules
arrow(5.6, ys[5] + 0.6, 6.2, 4.1, color=BLUE)         # flow mods
arrow(7.95, 6.75, 7.95, 6.15, color='#c08a3e')
ax.text(5.9, ys[0] + 0.85, 'stats', fontsize=7, color=MUTED, ha='center')
ax.text(5.9, ys[2] + 0.75, 'drop', fontsize=7, color=RED, ha='center')
ax.text(5.82, ys[5] + 1.05, 'FlowMod', fontsize=7, color=BLUE, ha='center')
fig.tight_layout()
fig.savefig(OUT + '/controller_loop.png', dpi=220, bbox_inches='tight', facecolor='white')
plt.close(fig)
print('ok')
