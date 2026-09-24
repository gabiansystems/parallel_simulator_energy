"""
se_distribution.py
==================
Strip plot de Se par architecture — invariance architecturale.
Une marque par nœud, labelisée, colorée par génération.
"""

import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

SUMMARY = Path(__file__).parent.parent / 'resultats' / 'se_summary.csv'
OUT     = Path(__file__).parent.parent / 'docs' / 'figures'
OUT.mkdir(parents=True, exist_ok=True)

ARCH_COLOR = {
    'SNB': '#2a78d6', 'IVB': '#4a3aa7', 'HSW': '#eb6834',
    'BDW': '#1baf7a', 'CLX': '#eda100', 'SKL': '#e87ba4', 'ICX': '#e34948',
}
ARCH_ORDER = ['IVB', 'SNB', 'HSW', 'BDW', 'CLX', 'SKL', 'ICX']

# ── Chargement ────────────────────────────────────────────────────────────────
rows = []
with open(SUMMARY) as f:
    for r in csv.DictReader(f):
        rows.append({
            'arch':  r['arch'],
            'node':  r['node'],
            'Se':    float(r['Se']),
            'cpu':   r['cpu'],
            'n_max': int(r['n_max']),
        })

# Grouper par arch dans l'ordre
by_arch = {a: [r for r in rows if r['arch'] == a] for a in ARCH_ORDER}

# ── Style ─────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    'font.family': 'sans-serif', 'font.size': 9.5,
    'axes.linewidth': 0.7,
    'axes.spines.top': False, 'axes.spines.right': False,
    'xtick.direction': 'out', 'ytick.direction': 'out',
    'xtick.major.size': 3.5, 'ytick.major.size': 3.5,
    'grid.linewidth': 0.4, 'grid.color': '#e0e0e0',
    'legend.frameon': False,
})

fig, ax = plt.subplots(figsize=(13 / 2.54 * 1.8, 9 / 2.54 * 1.8))

x_pos   = {a: i for i, a in enumerate(ARCH_ORDER)}
n_arch  = len(ARCH_ORDER)

ax.axhline(0, color='#cccccc', lw=0.5, zorder=0)

for arch in ARCH_ORDER:
    nodes  = by_arch[arch]
    if not nodes:
        continue
    color  = ARCH_COLOR[arch]
    xi     = x_pos[arch]
    Se_vals = [r['Se'] for r in nodes]

    # Ligne de dispersion (min–max) si >1 nœud
    if len(nodes) > 1:
        ax.vlines(xi, min(Se_vals), max(Se_vals),
                  color=color, lw=1.2, alpha=0.45, zorder=1)

    # Marque par nœud
    for r in nodes:
        ax.scatter(xi, r['Se'], s=55, color=color, zorder=4,
                   edgecolors='white', linewidths=0.8)

    # Labels nœuds — décalés alternativement à gauche/droite
    for k, r in enumerate(sorted(nodes, key=lambda x: x['Se'])):
        offset = 0.13 if k % 2 == 0 else -0.13
        ha     = 'left'  if offset > 0 else 'right'
        ax.text(xi + offset, r['Se'], r['node'],
                fontsize=7.5, color='#444', va='center', ha=ha, zorder=5)

    # Moyenne (tiret horizontal)
    mu = np.mean(Se_vals)
    ax.hlines(mu, xi - 0.25, xi + 0.25,
              color=color, lw=2.0, alpha=0.70, zorder=3)

# ── Axes ─────────────────────────────────────────────────────────────────────
ax.set_xticks(range(n_arch))
ax.set_xticklabels(ARCH_ORDER, fontsize=10)
ax.set_xlim(-0.6, n_arch - 0.4)
ax.set_ylim(-2, 42)
ax.set_xlabel('Architecture (génération, IVB→ICX)', labelpad=7)
ax.set_ylabel(r'$S_e = \bar{e}_{\mathrm{uncore}} / \bar{e}_{\mathrm{core}}$', labelpad=7)
ax.set_title(
    r'Distribution de $S_e$ — 17 nœuds, 7 générations Intel'
    '\n'
    r'tiret = moyenne par génération · chaque point = un nœud',
    fontsize=10, fontweight='semibold', pad=10,
)
ax.grid(axis='y')

# Annotation BDW outlier
bdw_nodes = sorted(by_arch['BDW'], key=lambda r: r['Se'])
ax.annotate(
    'BDW : 3 SKU différents\n(E5-2630/2660/2680 v4)',
    xy=(x_pos['BDW'] + 0.05, bdw_nodes[-1]['Se']),
    xytext=(x_pos['BDW'] + 0.85, bdw_nodes[-1]['Se'] - 5),
    fontsize=7.5, color=ARCH_COLOR['BDW'],
    arrowprops=dict(arrowstyle='->', color=ARCH_COLOR['BDW'],
                    lw=0.9, connectionstyle='arc3,rad=0.2'),
    va='center',
)

note = "Source : CRIME/resultats/se_summary.csv — OLS sur n_c ≥ 2"
ax.text(0, -0.13, note, transform=ax.transAxes, fontsize=6.5, color='#999')

fig.tight_layout()
fig.savefig(OUT / 'se_distribution.pdf', bbox_inches='tight', pad_inches=0.08)
fig.savefig(OUT / 'se_distribution.png', bbox_inches='tight', pad_inches=0.08, dpi=200)
print(f"PDF : {OUT / 'se_distribution.pdf'}")

# ── Statistiques stdout ───────────────────────────────────────────────────────
print("\nDispersion par architecture :")
for arch in ARCH_ORDER:
    vals = [r['Se'] for r in by_arch[arch]]
    if not vals:
        continue
    if len(vals) == 1:
        print(f"  {arch}: Se={vals[0]:.2f}  (1 nœud)")
    else:
        print(f"  {arch}: Se ∈ [{min(vals):.2f}, {max(vals):.2f}]  "
              f"μ={np.mean(vals):.2f}  σ={np.std(vals):.2f}  (n={len(vals)})")
