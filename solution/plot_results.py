#!/usr/bin/env python3
"""
CEG5101 CA2 - Task 5 plots for one experiment run.

Writes into <run_dir>/plots/:
  fig1_normalized_link_cost.png   Dynamic link cost (normalised, C/C0) vs time
  fig2_packet_loss.png            Packet loss (%) of h1 -> h6 vs time
  fig3_throughput.png             Throughput (Mbps) of h1 -> h6 vs time
  fig4_rtt.png                    (extra) h1 -> h6 ping RTT vs time - shows the path change
  overview.png                    figures 1-3 stacked on one time axis

Usage:
    python3 plot_results.py results/run1
"""

import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt          # noqa: E402

from run_data import Run, ping_loss_per_second   # noqa: E402

# palette: validated categorical slots 1-4 (light surface) + neutral chrome
SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100']
SURFACE = '#fcfcfb'
TEXT = '#0b0b0b'
TEXT_2 = '#52514e'
GRID = '#e1e0d9'
AXIS = '#c3c2b7'
WINDOW = '#efeee9'

COST_LINKS = ['s2-s3', 's2-s6', 's5-s6', 's1-s5']   # the three loaded links + backup path link
LEGIT = '10.0.0.1->10.0.0.6'

plt.rcParams.update({
    'figure.facecolor': SURFACE, 'axes.facecolor': SURFACE, 'savefig.facecolor': SURFACE,
    'axes.edgecolor': AXIS, 'axes.labelcolor': TEXT_2, 'xtick.color': TEXT_2,
    'ytick.color': TEXT_2, 'text.color': TEXT, 'font.size': 10,
    'axes.titlesize': 11, 'axes.titleweight': 'bold',
    'legend.frameon': False, 'lines.linewidth': 1.6,
})


def style(ax, ylabel):
    ax.grid(axis='y', color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    ax.set_ylabel(ylabel)


def shade_scenarios(ax, run, label=True):
    """Grey band for every high-rate traffic window, labelled at the top"""
    for sc in run.scenarios:
        ax.axvspan(sc['start'], sc['end'], color=WINDOW, zorder=0, linewidth=0)
        if label:
            ax.text((sc['start'] + sc['end']) / 2.0, 1.01, '%s) %s→%s  [%s]' % (
                sc['name'], sc['attacker'], sc['victim'], sc['link']),
                transform=ax.get_xaxis_transform(), ha='center', va='bottom',
                fontsize=8, color=TEXT_2)


def mark_reroutes(ax, run, label=True):
    """Dotted line at every reroute of the legitimate h1 -> h6 flow"""
    for t, event, detail in run.events():
        if event != 'REROUTE' or not detail.startswith(LEGIT + ' '):
            continue
        new_path = detail.split('=> ')[1].split(' ')[0].replace('>', '-')
        ax.axvline(t, color=TEXT_2, linestyle=':', linewidth=1.0, zorder=1)
        if label:
            ax.text(t + 1, 0.92, '→ %s' % new_path, transform=ax.get_xaxis_transform(),
                    fontsize=7.5, color=TEXT_2, va='top')


def direct_label(ax, x, y, text, color):
    ax.annotate(text, (x, y), xytext=(4, 0), textcoords='offset points',
                va='center', fontsize=8, color=TEXT)
    ax.plot([x], [y], marker='o', markersize=4, color=color)


def plot_cost(ax, run, costs):
    for i, link in enumerate(COST_LINKS):
        rows = costs.get(link, [])
        if not rows:
            continue
        t = [r[0] for r in rows]
        y = [r[5] for r in rows]
        ax.plot(t, y, color=SERIES[i], label=link, zorder=3)
        k = y.index(max(y))              # label each link at its own peak
        direct_label(ax, t[k], y[k], link, SERIES[i])
    style(ax, 'Normalised cost  C(t) / C0')
    ax.set_ylim(bottom=0.8)
    ax.legend(loc='center left', fontsize=8, bbox_to_anchor=(1.01, 0.5))


def plot_loss(ax, run, iperf, ping_loss):
    ax.plot([r[0] for r in iperf], [100.0 * r[3] / r[4] if r[4] else 0.0 for r in iperf],
            color=SERIES[0], label='UDP loss (iperf3)', zorder=3)
    ax.plot([r[0] + 0.5 for r in ping_loss], [r[1] for r in ping_loss],
            color=SERIES[1], label='ping loss', zorder=3)
    style(ax, 'Packet loss (%)')
    ax.set_ylim(-3, 105)
    ax.legend(loc='center left', fontsize=8, bbox_to_anchor=(1.01, 0.5))


def plot_throughput(ax, run, iperf):
    ax.plot([(r[0] + r[1]) / 2.0 for r in iperf], [r[2] for r in iperf],
            color=SERIES[0], zorder=3)
    style(ax, 'Throughput (Mbps)')
    peak = max([r[2] for r in iperf] or [1.0])
    ax.set_ylim(0, peak * 1.35)


def plot_rtt(ax, run, replies):
    rtts = sorted(r[1] for r in replies)
    top = max(150.0, 1.6 * rtts[int(0.99 * (len(rtts) - 1))]) if rtts else 150.0
    ax.plot([r[0] for r in replies], [r[1] for r in replies], linestyle='none',
            marker='o', markersize=2.5, color=SERIES[0], zorder=3)
    style(ax, 'RTT (ms)')
    ax.set_ylim(0, top)
    off_scale = sum(1 for r in rtts if r > top)
    if off_scale:
        ax.text(0.99, 0.97, '%d replies above %.0f ms not shown' % (off_scale, top),
                transform=ax.transAxes, ha='right', va='top', fontsize=8, color=TEXT_2)


def finish(fig, ax, title, path):
    ax.set_title(title, pad=16, loc='left')
    ax.set_xlabel('Time since start of baseline (s)')
    ax.set_xlim(0, None)
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches='tight')
    plt.close(fig)
    print('wrote', path)


def main(run_dir):
    run = Run(run_dir)
    costs = run.link_costs()
    iperf = run.iperf()
    replies, lost = run.ping()
    ping_loss = ping_loss_per_second(replies, lost, 0, run.t_end)
    out = os.path.join(run_dir, 'plots')
    os.makedirs(out, exist_ok=True)

    figs = [
        ('fig1_normalized_link_cost.png', 'Dynamic link cost (normalised) vs time',
         lambda ax: plot_cost(ax, run, costs), False),
        ('fig2_packet_loss.png', 'Packet loss of h1→h6 vs time',
         lambda ax: plot_loss(ax, run, iperf, ping_loss), True),
        ('fig3_throughput.png', 'Throughput of h1→h6 (UDP) vs time',
         lambda ax: plot_throughput(ax, run, iperf), True),
        ('fig4_rtt.png', 'Round-trip time of h1→h6 vs time (path change is visible)',
         lambda ax: plot_rtt(ax, run, replies), True),
    ]
    for name, title, draw, reroutes in figs:
        fig, ax = plt.subplots(figsize=(10, 3.8))
        shade_scenarios(ax, run)
        if reroutes:
            mark_reroutes(ax, run)
        draw(ax)
        finish(fig, ax, title, os.path.join(out, name))

    # overview: figures 1-3 on one shared time axis
    fig, axes = plt.subplots(3, 1, figsize=(10, 9.5), sharex=True)
    for i, (ax, (_, title, draw, reroutes)) in enumerate(zip(axes, figs[:3])):
        shade_scenarios(ax, run, label=(i == 0))
        mark_reroutes(ax, run, label=(i == 2))
        draw(ax)
        ax.set_title(title, pad=14 if i == 0 else 6, loc='left')
    axes[-1].set_xlabel('Time since start of baseline (s)')
    axes[-1].set_xlim(0, None)
    fig.tight_layout()
    path = os.path.join(out, 'overview.png')
    fig.savefig(path, dpi=200, bbox_inches='tight')
    plt.close(fig)
    print('wrote', path)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
