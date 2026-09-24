"""
greenup_par_noeud.py
====================
Figure P3 — G(n_c) toutes courbes superposées sur un seul graphe.

G(n_c) = E_ref(1) / E(n_c),   E_ref(1) = ecore_c + euncore_c (OLS prédit)
Modèle : G(n_c) = n_c(Se+1)/(n_c+Se)
Asymptote par nœud : 1+Se  (pointillés)

Sortie :
  CRIME/docs/figures/greenup_par_noeud.pdf / .png
"""

import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path

BASE    = Path(__file__).parent.parent / 'resultats' / 'parallel_sim'
SUMMARY = Path(__file__).parent.parent / 'resultats' / 'se_summary.csv'
OUT     = Path(__file__).parent.parent / 'docs' / 'figures'
OUT.mkdir(parents=True, exist_ok=True)

ARCH_COLOR = {
    'SNB': '#2a78d6', 'IVB': '#4a3aa7', 'HSW': '#eb6834',
    'BDW': '#1baf7a', 'CLX': '#eda100', 'SKL': '#e87ba4', 'ICX': '#e34948',
}
ARCH_ORDER = ['IVB', 'SNB', 'HSW', 'BDW', 'CLX', 'SKL', 'ICX']

NODES = [
    ('IVB', 'gof17',      'parallel_sim_ivb_gof17.csv'),
    ('SNB', 'econome-6',  'parallel_sim_snb_econome-6.csv'),
    ('SNB', 'orion-4',    'parallel_sim_snb_orion-4.csv'),
    ('SNB', 'taurus-3',   'parallel_sim_snb_taurus-3.csv'),
    ('SNB', 'taurus-4',   'parallel_sim_snb_taurus-4.csv'),
    ('SNB', 'hercule-1',  'parallel_sim_snb_hercule-1.csv'),
    ('HSW', 'parasilo-2', 'parallel_sim_hsw_parasilo-2.csv'),
    ('BDW', 'nova-1',     'parallel_sim_bdw_nova-1.csv'),
    ('BDW', 'ecotype-2',  'parallel_sim_bdw_ecotype-2.csv'),
    ('BDW', 'clervaux-8', 'parallel_sim_bdw_clervaux-8.csv'),
    ('CLX', 'gros-1',     'parallel_sim_clx_gros-1_fixed.csv'),
    ('SKL', 'dahu-1',     'parallel_sim_skl_dahu-1.csv'),
    ('SKL', 'chifflot-1', 'parallel_sim_skl_chifflot-1.csv'),
    ('ICX', 'paradoxe-2', 'parallel_sim_icx_paradoxe-2.csv'),
    ('ICX', 'chirop-1',   'parallel_sim_icx_chirop-1.csv'),
    ('ICX', 'chirop-4',   'parallel_sim_icx_chirop-4.csv'),
    ('ICX', 'chirop-5',   'parallel_sim_icx_chirop-5.csv'),
    ('ICX', 'spirou-3',   'parallel_sim_icx_spirou-3.csv'),
    ('ICX', 'montcalm-1', 'parallel_sim_icx_montcalm-1.csv'),
    ('SNB', 'taurus-6',   'parallel_sim_snb_taurus-6.csv'),
    ('SNB', 'taurus-7',   'parallel_sim_snb_taurus-7.csv'),
]

FIT = {}
with open(SUMMARY) as f:
    for r in csv.DictReader(f):
        FIT[r['node']] = {
            'ecore_c':   float(r['ecore_c']),
            'euncore_c': float(r['euncore_c']),
            'Se':        float(r['Se']),
            'n_max':     int(r['n_max']),
        }

def load_median(filepath):
    rows = {}
    with open(filepath) as f:
        for r in csv.DictReader(f):
            if float(r['Seq_frac']) != 0.0:
                continue
            n = int(float(r['N_core']))
            rows.setdefault(n, []).append(float(r['Energy']))
    return {n: float(np.median(v)) for n, v in rows.items()}

DATA = {label: load_median(BASE / fname)
        for _, label, fname in NODES if (BASE / fname).exists()}

plt.rcParams.update({
    'font.family': 'sans-serif', 'font.size': 9,
    'axes.linewidth': 0.7,
    'axes.spines.top': False, 'axes.spines.right': False,
    'xtick.direction': 'out', 'ytick.direction': 'out',
    'xtick.major.size': 3.5, 'ytick.major.size': 3.5,
    'grid.linewidth': 0.4, 'grid.color': '#e0e0e0',
    'legend.frameon': False,
})

fig, ax = plt.subplots(figsize=(12 / 2.54 * 1.8, 9 / 2.54 * 1.8))

# Speedup idéal (référence commune)
nc_full = np.linspace(2, 33, 400)
ax.plot(nc_full, nc_full, '--', color='#bbbbbb', lw=1.0, zorder=1,
        label='speedup idéal $S(n_c)=n_c$')

seen_arch = set()
max_Se = 0.0
for arch, label, _ in NODES:
    if label not in DATA or label not in FIT:
        continue
    med   = DATA[label]
    fit   = FIT[label]
    color = ARCH_COLOR[arch]
    Se    = fit['Se']
    n_max = fit['n_max']
    E_ref = fit['ecore_c'] + fit['euncore_c']
    max_Se = max(max_Se, Se)

    # Points mesurés
    ns_meas = sorted(n for n in med if n >= 2)
    G_meas  = [E_ref / med[n] for n in ns_meas]
    ax.scatter(ns_meas, G_meas, s=10, color=color, alpha=0.40, zorder=3,
               edgecolors='none')

    # Courbe modèle
    nc_fit  = np.linspace(2, n_max, 300)
    G_model = nc_fit * (Se + 1) / (nc_fit + Se)
    ax.plot(nc_fit, G_model, '-', color=color, lw=1.4,
            alpha=0.80 if arch not in seen_arch else 0.55,
            zorder=4, label=arch if arch not in seen_arch else '_nolegend_')

    # Asymptote 1+Se (pointillés légers jusqu'à n_max)
    ax.hlines(1 + Se, 2, n_max, color=color, lw=0.6,
              ls=(0, (4, 6)), alpha=0.30, zorder=2)

    seen_arch.add(arch)

# ── Annotations des asymptotes extrêmes ──────────────────────────────────────
for arch, label in [('IVB', 'gof17'), ('SKL', 'dahu-1'), ('ICX', 'chirop-1')]:
    if label in FIT:
        Se    = FIT[label]['Se']
        n_max = FIT[label]['n_max']
        ax.annotate(
            f"$1+S_e$={1+Se:.0f}",
            xy=(n_max + 0.3, 1 + Se),
            fontsize=7, color=ARCH_COLOR[arch], va='center',
        )

# ── Axes ─────────────────────────────────────────────────────────────────────
ax.set_xlabel(r'$n_c$ (nombre de cœurs actifs)', labelpad=6)
ax.set_ylabel(r'$G(n_c)$ (greenup)', labelpad=6)
ax.set_title(
    r'Greenup $G(n_c)$ — 17 nœuds superposés (IVB $\to$ ICX)'
    '\n'
    r'modèle $G = n_c(S_e+1)/(n_c+S_e)$, '
    r'asymptote $1+S_e$ (pointillés), speedup idéal (gris)',
    fontsize=9.5, fontweight='semibold', pad=10,
)
ax.set_xlim(1.5, 35)
ax.set_ylim(0.8, max_Se * 1.15)
ax.grid(axis='y')

# Légende architecture
arch_patches = [mpatches.Patch(color=ARCH_COLOR[a], label=a) for a in ARCH_ORDER]
ideal_line   = plt.Line2D([0], [0], color='#bbbbbb', lw=1.0, ls='--',
                           label='speedup idéal')
ax.legend(handles=arch_patches + [ideal_line],
          title='Architecture', title_fontsize=8,
          fontsize=8, loc='upper left', ncol=1,
          handlelength=1.2, handletextpad=0.5, borderpad=0.6)

note = "Légende complète : CRIME/docs/figures/captions.tex (\\captionGreenupParNoeud)"
ax.text(0, -0.12, note, transform=ax.transAxes, fontsize=6.5, color='#999')

fig.tight_layout()
fig.savefig(OUT / 'greenup_par_noeud.pdf', bbox_inches='tight', pad_inches=0.08)
fig.savefig(OUT / 'greenup_par_noeud.png', bbox_inches='tight', pad_inches=0.08, dpi=200)
print(f"PDF : {OUT / 'greenup_par_noeud.pdf'}")
