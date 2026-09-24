"""
estimateurs.py
==============
Figure fig_ch1_estimateurs — Cohérence interne des deux estimateurs de Se :
  • Se_OLS  : régression OLS sur E(n_c) = ecore_c + euncore_c/n_c, n_c ≥ 2
  • Ŝe_inv  : inversion ponctuelle à chaque n_c via G(n_c) mesuré
              Ŝe(n_c) = n_c·(G−1)/(n_c−G)  où  G = E_ref/E_médiane(n_c)

Scatter : x = Se_OLS (source de vérité), y = Ŝe_inv(n_c)
Un point par (nœud, n_c). La diagonale y = x valide la cohérence du modèle.
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

# ── Paramètres OLS (se_summary.csv) ──────────────────────────────────────────
FIT = {}
with open(SUMMARY) as f:
    for r in csv.DictReader(f):
        FIT[r['node']] = {
            'ecore_c':    float(r['ecore_c']),
            'euncore_c':  float(r['euncore_c']),
            'Se':         float(r['Se']),
            'n_max':      int(r['n_max']),
        }

# ── Collecte des Ŝe_inv par nœud et par n_c ──────────────────────────────────
records = []   # (arch, node, Se_OLS, nc, Se_inv)

for arch, node, fname in NODES:
    fpath = BASE / fname
    if not fpath.exists() or node not in FIT:
        continue
    fit    = FIT[node]
    Se_OLS = fit['Se']
    E_ref  = fit['ecore_c'] + fit['euncore_c']

    # Médiane par n_c
    raw = {}
    with open(fpath) as f:
        for r in csv.DictReader(f):
            if float(r['Seq_frac']) != 0.0:
                continue
            n = int(float(r['N_core']))
            raw.setdefault(n, []).append(float(r['Energy']))

    for nc, vals in raw.items():
        if nc < 2:
            continue
        E_med = float(np.median(vals))
        G     = E_ref / E_med
        # Formule d'inversion : Ŝe = n_c*(G-1)/(n_c-G)
        denom = nc - G
        if abs(denom) < 1e-6 or G <= 1:
            continue
        Se_inv = nc * (G - 1) / denom
        if Se_inv <= 0 or Se_inv > 200:
            continue
        records.append((arch, node, Se_OLS, nc, Se_inv))

print(f"Points totaux : {len(records)}")

Se_OLS_all = np.array([r[2] for r in records])
Se_inv_all = np.array([r[4] for r in records])
# RMSE global
rmse = float(np.sqrt(np.mean((Se_inv_all - Se_OLS_all)**2)))
print(f"RMSE Ŝe_inv vs Se_OLS = {rmse:.3f}")

# ── Style ─────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    'font.family': 'sans-serif', 'font.size': 9,
    'axes.linewidth': 0.7,
    'axes.spines.top': False, 'axes.spines.right': False,
    'xtick.direction': 'out', 'ytick.direction': 'out',
    'xtick.major.size': 3.5, 'ytick.major.size': 3.5,
    'grid.linewidth': 0.4, 'grid.color': '#e0e0e0',
    'legend.frameon': False,
})

fig, ax = plt.subplots(figsize=(10 / 2.54 * 1.8, 10 / 2.54 * 1.8))

# Diagonale y = x
lim_max = max(Se_OLS_all.max(), Se_inv_all.max()) * 1.08
ax.plot([0, lim_max], [0, lim_max], '--', color='#bbbbbb', lw=1.2, zorder=1,
        label=r'$\hat{S}_e = S_{e,\mathrm{OLS}}$')

# ±10 % bandes
ax.fill_between([0, lim_max], [0, lim_max * 0.9], [0, lim_max * 1.1],
                color='#f0f0f0', alpha=0.6, zorder=0)
ax.text(lim_max * 0.6, lim_max * 0.6 * 1.12, '±10 %',
        fontsize=7, color='#aaa', va='bottom')

seen_arch = set()
for arch, node, Se_OLS, nc, Se_inv in records:
    color = ARCH_COLOR[arch]
    alpha = 0.55 if nc < FIT[node]['n_max'] else 0.85
    size  = 20 if nc < FIT[node]['n_max'] else 40
    lbl   = arch if arch not in seen_arch else '_'
    ax.scatter(Se_OLS, Se_inv, s=size, color=color, alpha=alpha,
               edgecolors='white', linewidths=0.4, zorder=3, label=lbl)
    seen_arch.add(arch)

# RMSE annotation
ax.text(0.04, 0.96,
        f'RMSE = {rmse:.2f}\n({len(records)} points · 17 nœuds)',
        transform=ax.transAxes, fontsize=8, va='top', color='#444',
        bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                  edgecolor='#ddd', alpha=0.9))

# Légende architecture
patches = [mpatches.Patch(color=ARCH_COLOR[a], label=a) for a in ARCH_ORDER]
diag    = plt.Line2D([0], [0], color='#bbbbbb', lw=1.2, ls='--', label=r'$y = x$')
ax.legend(handles=patches + [diag],
          title='Architecture', title_fontsize=8,
          fontsize=8, loc='upper left', ncol=1,
          handlelength=1.0, handletextpad=0.4, borderpad=0.6)

ax.set_xlim(0, lim_max)
ax.set_ylim(0, lim_max)
ax.set_xlabel(r'$S_{e,\mathrm{OLS}}$ (régression)',  labelpad=6)
ax.set_ylabel(r'$\hat{S}_e(n_c)$ (inversion ponctuelle)', labelpad=6)
ax.set_title(
    r'Cohérence interne des estimateurs de $S_e$' '\n'
    r'$\hat{S}_e(n_c) = n_c\,(G-1)/(n_c-G)$,  $G = \hat{E}(1)/E_\mathrm{med}(n_c)$',
    fontsize=10, fontweight='semibold', pad=10,
)
ax.grid()

note = "Source : se_summary.csv + parallel_sim CSVs — Légende : captions.tex"
ax.text(0, -0.12, note, transform=ax.transAxes, fontsize=6.5, color='#999')

fig.tight_layout()
fig.savefig(OUT / 'estimateurs.pdf', bbox_inches='tight', pad_inches=0.08)
fig.savefig(OUT / 'estimateurs.png', bbox_inches='tight', pad_inches=0.08, dpi=200)
print(f"PDF : {OUT / 'estimateurs.pdf'}")
