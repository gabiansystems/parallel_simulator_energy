"""
work_sweep.py
=============
Figure P1 — Sensibilité de Se à la taille de charge (nœud CLX gros-1).
Modèle : E(n_c) = ecore_c + euncore_c/n_c  →  Se = euncore_c/ecore_c
OLS sur n_c ≥ 2. Bootstrap IC 95 % (B=1000, seed=42).

Sortie :
  CRIME/docs/figures/work_sweep.pdf   — pour inclusion manuscrit
  CRIME/docs/figures/work_sweep.png   — aperçu
Valeurs imprimées sur stdout → \result{} de patchs_redaction_ch1.md §4.
"""

import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────
BASE = Path(__file__).parent.parent.parent / 'lecture_energie' / 'resultats' / 'work_sweep'
OUT  = Path(__file__).parent.parent / 'docs' / 'figures'
OUT.mkdir(parents=True, exist_ok=True)

FILES = {
    '500K': BASE / 'work_sweep_nw500K_clx_gros-1.csv',
    '1M':   BASE / 'work_sweep_nw1M_clx_gros-1.csv',
    '10M':  BASE / 'work_sweep_nw10M_clx_gros-1.csv',
    '100M': BASE / 'work_sweep_nw100M_clx_gros-1.csv',
    '1G':   BASE / 'work_sweep_nw1G_clx_gros-1.csv',
}
N_WORK = {'500K': 5e5, '1M': 1e6, '10M': 1e7, '100M': 1e8, '1G': 1e9}
LABELS = ['500K', '1M', '10M', '100M', '1G']
CLX_COLOR = '#eda100'
ESU_UJ = 15.3
BOOT_B  = 1000
BOOT_SEED = 42

# ── OLS Se ──────────────────────────────────────────────────────────────────
def load_E_by_nc(filepath):
    rows = {}
    with open(filepath) as f:
        for r in csv.DictReader(f):
            if float(r['Seq_frac']) != 0.0:
                continue
            n = int(float(r['N_core']))
            rows.setdefault(n, []).append(float(r['Energy']))
    return rows


def ols_Se(rows_by_nc):
    ns    = sorted(n for n in rows_by_nc if n >= 2)
    E     = np.array([np.mean(rows_by_nc[n]) for n in ns])
    X     = np.column_stack([np.ones(len(ns)), 1.0 / np.array(ns)])
    ec, eu = np.linalg.lstsq(X, E, rcond=None)[0]
    return eu / ec, ec, eu


def bootstrap_Se(rows_by_nc, B=BOOT_B, seed=BOOT_SEED):
    rng   = np.random.default_rng(seed)
    ns    = sorted(n for n in rows_by_nc if n >= 2)
    ses   = []
    for _ in range(B):
        E_boot = np.array([np.mean(rng.choice(rows_by_nc[n], size=len(rows_by_nc[n]), replace=True))
                           for n in ns])
        X = np.column_stack([np.ones(len(ns)), 1.0 / np.array(ns)])
        ec, eu = np.linalg.lstsq(X, E_boot, rcond=None)[0]
        ses.append(eu / ec)
    ses = np.array(ses)
    lo, hi = np.percentile(ses, [2.5, 97.5])
    return float(lo), float(hi)

# ── Calcul ────────────────────────────────────────────────────────────────────
results = {}
for label, fpath in FILES.items():
    rows = load_E_by_nc(fpath)
    Se, ec, eu = ols_Se(rows)
    lo, hi     = bootstrap_Se(rows)
    # E/ESU à n_c=18 (cas le plus défavorable)
    E18 = np.mean(rows.get(18, [np.mean([v for vv in rows.values() for v in vv])]))
    results[label] = {
        'Se': Se, 'lo': lo, 'hi': hi,
        'E18': E18, 'esu_ratio': E18 * 1e6 / ESU_UJ,
        'ecore_c': ec, 'euncore_c': eu,
    }

# ── Impression stdout pour \result{} ─────────────────────────────────────────
print("=" * 60)
print("work_sweep.py — valeurs pour \\result{} (patchs §4)")
print("=" * 60)
for k in LABELS:
    if k in results:
        print(f"  Se({k:5s}) = {results[k]['Se']:.2f}  IC95%=[{results[k]['lo']:.2f}, {results[k]['hi']:.2f}]  E/ESU={results[k]['esu_ratio']:.0f}")
Se_all = [results[k]['Se'] for k in LABELS if k in results]
ecart_max = (max(Se_all) - min(Se_all)) / np.mean(Se_all) * 100
print(f"  Écart relatif max = {ecart_max:.1f} %  (min={min(Se_all):.2f}, max={max(Se_all):.2f})")
print("=" * 60)

# ── Style ─────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    'font.family':       'sans-serif',
    'font.size':         9,
    'axes.linewidth':    0.7,
    'axes.spines.top':   False,
    'axes.spines.right': False,
    'xtick.direction':   'out',
    'ytick.direction':   'out',
    'xtick.major.size':  3,
    'ytick.major.size':  3,
    'xtick.major.width': 0.7,
    'ytick.major.width': 0.7,
    'grid.linewidth':    0.4,
    'grid.color':        '#DDDDDD',
    'legend.frameon':    False,
})

fig, ax = plt.subplots(figsize=(10 / 2.54 * 1.5, 7 / 2.54 * 1.5))

active_labels = [k for k in LABELS if k in results]
x_vals = [N_WORK[k] for k in active_labels]
Se_pts = [results[k]['Se'] for k in active_labels]
lo_pts = [results[k]['lo'] for k in active_labels]
hi_pts = [results[k]['hi'] for k in active_labels]
n_pts  = len(active_labels)

# IC bootstrap (barres d'erreur)
yerr = np.array([[Se_pts[i] - lo_pts[i] for i in range(n_pts)],
                 [hi_pts[i] - Se_pts[i] for i in range(n_pts)]])
ax.errorbar(x_vals, Se_pts, yerr=yerr,
            fmt='o', color=CLX_COLOR, markersize=7,
            ecolor=CLX_COLOR, elinewidth=1.4, capsize=5, capthick=1.4,
            zorder=5, label='CLX gros-1 (Xeon Gold 5220, 18 cœurs)')

# Ligne reliant les points
ax.plot(x_vals, Se_pts, '-', color=CLX_COLOR, linewidth=1.2, alpha=0.6, zorder=4)

# Annotations des valeurs Se
for k, x, se in zip(active_labels, x_vals, Se_pts):
    ax.text(x, se + 0.4, f'$S_e$={se:.2f}', ha='center', va='bottom',
            fontsize=8, color=CLX_COLOR, fontweight='semibold')

ax.set_xscale('log')
ax.set_xlim(2e5, 3e9)
ax.set_ylim(0, max(hi_pts) * 1.4)
ax.set_xlabel(r'Volume de travail $n_\mathrm{work}$ (opérations)', labelpad=7)
ax.set_ylabel(r'Paramètre $S_e$ (OLS, $n_c \geq 2$)', labelpad=7)
ax.set_title(r'Stabilité de $S_e$ en fonction du volume de travail' + '\n'
             'nœud gros-1 (CLX Gold 5220, 18 cœurs, Nancy)',
             fontsize=9, fontweight='semibold', pad=8)

ax.xaxis.set_major_formatter(ticker.FuncFormatter(
    lambda x, _: {5e5: '500K', 1e6: '1M', 1e7: '10M', 1e8: '100M', 1e9: '1G'}.get(x, '')))
ax.set_xticks([5e5, 1e6, 1e7, 1e8, 1e9])
ax.grid(axis='y')
ax.legend(loc='upper left', fontsize=8)

note = f"IC 95 % bootstrap (B={BOOT_B}, seed={BOOT_SEED}) — Légende : CRIME/docs/figures/captions.tex (\\captionWorkSweep)"
ax.text(0, -0.16, note, transform=ax.transAxes, fontsize=6.5, color='#888888')

fig.tight_layout()
fig.savefig(OUT / 'work_sweep.pdf', bbox_inches='tight', pad_inches=0.08)
fig.savefig(OUT / 'work_sweep.png', bbox_inches='tight', pad_inches=0.08, dpi=200)
print(f"PDF : {OUT / 'work_sweep.pdf'}")
print(f"PNG : {OUT / 'work_sweep.png'}")
