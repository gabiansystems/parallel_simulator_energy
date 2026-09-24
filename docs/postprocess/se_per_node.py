"""
se_per_node.py
==============
Figure chapitre 1 — Paramètre Se par nœud (17 nœuds du périmètre).
Modèle Greenup : E(n) = ecore_c + euncore_c/n  →  Se = euncore_c/ecore_c
                 (régression OLS, n_c ≥ 2)

Sortie :
  CRIME/docs/figures/se_per_node.pdf   — pour inclusion manuscrit
  CRIME/docs/figures/se_per_node.png   — aperçu
  CRIME/resultats/se_summary.csv       — source de vérité (Se, ecore_c, euncore_c)
"""

import csv, numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path

# ── Données ──────────────────────────────────────────────────────────────────
BASE    = Path(__file__).parent.parent / 'resultats' / 'parallel_sim'
OUT     = Path(__file__).parent.parent / 'docs' / 'figures'
OUT_CSV = Path(__file__).parent.parent / 'resultats' / 'se_summary.csv'
OUT.mkdir(parents=True, exist_ok=True)

NODES = [   # (arch, label_court, fichier_csv)
    ('SNB', 'econome-6',  'parallel_sim_snb_econome-6.csv'),
    ('SNB', 'orion-4',    'parallel_sim_snb_orion-4.csv'),
    ('SNB', 'taurus-3',   'parallel_sim_snb_taurus-3.csv'),
    ('SNB', 'taurus-4',   'parallel_sim_snb_taurus-4.csv'),
    ('SNB', 'hercule-1',  'parallel_sim_snb_hercule-1.csv'),
    ('IVB', 'gof17',      'parallel_sim_ivb_gof17.csv'),
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

# Métadonnées fixes par nœud (site, CPU, fréquence nominale en GHz)
METADATA = {
    'econome-6':  {'site': 'Nantes',      'cpu': 'Xeon E5-2650',    'freq_nom': 2.00},
    'orion-4':    {'site': 'Lyon',         'cpu': 'Xeon E5-2670',    'freq_nom': 2.60},
    'taurus-3':   {'site': 'Lyon',         'cpu': 'Xeon E5-2630',    'freq_nom': 2.30},
    'taurus-4':   {'site': 'Lyon',         'cpu': 'Xeon E5-2630',    'freq_nom': 2.30},
    'hercule-1':  {'site': 'Lyon',         'cpu': 'Xeon E5-2650',    'freq_nom': 2.00},
    'gof17':      {'site': 'Lyon',         'cpu': 'Xeon E5-2630',    'freq_nom': 2.30},
    'parasilo-2': {'site': 'Rennes',       'cpu': 'Xeon E5-2660 v3', 'freq_nom': 2.60},
    'nova-1':     {'site': 'Lyon',         'cpu': 'Xeon E5-2630 v4', 'freq_nom': 2.20},
    'ecotype-2':  {'site': 'Nantes',       'cpu': 'Xeon E5-2660 v4', 'freq_nom': 2.00},
    'clervaux-8': {'site': 'Luxembourg',   'cpu': 'Xeon E5-2680 v4', 'freq_nom': 2.40},
    'gros-1':     {'site': 'Nancy',        'cpu': 'Xeon Gold 5220',  'freq_nom': 2.20},
    'dahu-1':     {'site': 'Grenoble',     'cpu': 'Xeon Gold 6130',  'freq_nom': 2.10},
    'chifflot-1': {'site': 'Lille',        'cpu': 'Xeon Gold 6130',  'freq_nom': 2.10},
    'paradoxe-2': {'site': 'Rennes',       'cpu': 'Xeon Gold 6346',  'freq_nom': 3.10},
    'chirop-1':   {'site': 'Lille',        'cpu': 'Xeon Gold 6338',  'freq_nom': 2.00},
    'chirop-4':   {'site': 'Lille',        'cpu': 'Xeon Gold 6338',  'freq_nom': 2.00},
    'chirop-5':   {'site': 'Lille',        'cpu': 'Xeon Gold 6338',  'freq_nom': 2.00},
    'spirou-3':   {'site': 'Louvain',      'cpu': 'Xeon Gold 6342',  'freq_nom': 2.80},
    'montcalm-1': {'site': 'Toulouse',     'cpu': 'Xeon Gold 6342',  'freq_nom': 2.80},
    'taurus-6':   {'site': 'Lyon',         'cpu': 'Xeon E5-2630',    'freq_nom': 2.30},
    'taurus-7':   {'site': 'Lyon',         'cpu': 'Xeon E5-2630',    'freq_nom': 2.30},
}

# Palette catégorielle (reference palette slots 1–7, adjacente validée)
ARCH_COLOR = {
    'SNB': '#2a78d6',
    'IVB': '#4a3aa7',
    'HSW': '#eb6834',
    'BDW': '#1baf7a',
    'CLX': '#eda100',
    'SKL': '#e87ba4',
    'ICX': '#e34948',
}

def fit_Se(filepath):
    """OLS sur E(n_c) = ecore_c + euncore_c/n_c, n_c ≥ 2.
    Retourne (Se, n_max, ecore_c, euncore_c, RMSE, n_points)."""
    rows = {}
    with open(filepath) as f:
        for r in csv.DictReader(f):
            if float(r['Seq_frac']) != 0.0:
                continue
            n = int(float(r['N_core']))
            if n < 2:
                continue
            rows.setdefault(n, []).append(float(r['Energy']))
    ns       = sorted(rows)
    E_mean   = np.array([np.mean(rows[n]) for n in ns])
    X        = np.column_stack([np.ones(len(ns)), 1.0 / np.array(ns)])
    ecore_c, euncore_c = np.linalg.lstsq(X, E_mean, rcond=None)[0]
    E_pred   = ecore_c + euncore_c / np.array(ns)
    rmse     = float(np.sqrt(np.mean((E_pred - E_mean) ** 2)))
    return euncore_c / ecore_c, max(ns), ecore_c, euncore_c, rmse, len(ns)

results = []
for arch, label, fname in NODES:
    p = BASE / fname
    if not p.exists():
        print(f'[warn] manquant : {fname}')
        continue
    Se, n_max, ecore_c, euncore_c, rmse, n_pts = fit_Se(p)
    results.append({
        'arch': arch, 'label': label,
        'Se': Se, 'n_max': n_max,
        'ecore_c': ecore_c, 'euncore_c': euncore_c,
        'RMSE': rmse, 'n_points': n_pts,
    })

# ── Style ─────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    'font.family':       'sans-serif',
    'font.size':         8.5,
    'axes.linewidth':    0.6,
    'axes.spines.top':   False,
    'axes.spines.right': False,
    'axes.spines.left':  False,
    'xtick.direction':   'out',
    'ytick.direction':   'out',
    'xtick.major.size':  3,
    'ytick.major.size':  0,
    'xtick.major.width': 0.6,
    'grid.linewidth':    0.35,
    'grid.color':        '#e1e0d9',
    'legend.frameon':    False,
    'legend.fontsize':   7.5,
})

fig, ax = plt.subplots(figsize=(13 / 2.54 * 1.6, 11 / 2.54 * 1.6))

# ── Bandes de fond par architecture ──────────────────────────────────────────
arch_order = ['SNB', 'IVB', 'HSW', 'BDW', 'CLX', 'SKL', 'ICX']
arch_groups = {a: [] for a in arch_order}
for r in results:
    arch_groups[r['arch']].append(r)

y_pos = {}
y = 0
group_spans = {}

for arch in arch_order:
    nodes = arch_groups[arch]
    if not nodes:
        continue
    y_start = y - 0.5
    for r in nodes:
        y_pos[r['label']] = y
        y += 1
    y_end = y - 0.5
    group_spans[arch] = (y_start, y_end, (y_start + y_end) / 2)
    # bande de fond alternée
    idx = arch_order.index(arch)
    if idx % 2 == 0:
        ax.axhspan(y_start, y_end, color='#f0efed', zorder=0, lw=0)
    y += 0.4  # espace entre groupes

n_rows = y

# ── Lignes de grille verticales ───────────────────────────────────────────────
ax.grid(axis='x', zorder=1)
ax.axvline(0, color='#c3c2b7', lw=0.6, zorder=2)

# ── Ligne de moyenne par architecture ────────────────────────────────────────
for arch in arch_order:
    nodes = arch_groups[arch]
    if not nodes:
        continue
    Se_vals = [r['Se'] for r in nodes]
    y_s, y_e, y_mid = group_spans[arch]
    ax.hlines(y_mid, min(Se_vals) if len(Se_vals) > 1 else 0,
              max(Se_vals) if len(Se_vals) > 1 else 0,
              color=ARCH_COLOR[arch], lw=1.5, zorder=3, alpha=0.4)
    mean_Se = np.mean(Se_vals)
    ax.vlines(mean_Se, y_s + 0.1, y_e - 0.1,
              color=ARCH_COLOR[arch], lw=2.0, zorder=4, alpha=0.7)

# ── Dots individuels ──────────────────────────────────────────────────────────
for r in results:
    yi = y_pos[r['label']]
    c  = ARCH_COLOR[r['arch']]
    ax.scatter(r['Se'], yi, s=55, color=c, zorder=5,
               edgecolors='white', linewidths=0.8)
    # annotation n_max
    ax.text(r['Se'] + 0.5, yi, f"({r['n_max']}c)",
            va='center', fontsize=6.5, color='#898781')

# ── Annotation outlier BDW clervaux ──────────────────────────────────────────
clervaux = next(r for r in results if r['label'] == 'clervaux-8')
ax.annotate('clervaux-8\n14c, TDP élevé',
            xy=(clervaux['Se'], y_pos['clervaux-8']),
            xytext=(clervaux['Se'] + 3, y_pos['clervaux-8'] - 1.8),
            fontsize=6.5, color='#52514e',
            arrowprops=dict(arrowstyle='->', color='#898781', lw=0.8),
            bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='none', alpha=0.85))

# ── Labels y (nœuds + arch) ───────────────────────────────────────────────────
yticks = [y_pos[r['label']] for r in results]
ylabels = [r['label'] for r in results]
ax.set_yticks(yticks)
ax.set_yticklabels(ylabels, fontsize=7.5, color='#52514e')

# Labels architecture sur la droite
ax2 = ax.twinx()
ax2.set_ylim(ax.get_ylim())
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)
ax2.spines['left'].set_visible(False)
ax2.spines['bottom'].set_visible(False)
ax2.tick_params(left=False, right=False)

for arch in arch_order:
    if arch not in group_spans:
        continue
    _, _, y_mid = group_spans[arch]
    c = ARCH_COLOR[arch]
    # Calcul de Se moyen
    Se_vals = [r['Se'] for r in arch_groups[arch]]
    Se_mean = np.mean(Se_vals)
    ax2.text(1.01, y_mid / (n_rows + 0.5),
             f'{arch}\n$\\bar{{S}}_e$={Se_mean:.0f}',
             transform=ax2.transAxes,
             va='center', ha='left',
             fontsize=7.5, fontweight='semibold', color=c,
             linespacing=1.3)
ax2.set_yticks([])

# ── Axes ─────────────────────────────────────────────────────────────────────
ax.set_xlim(-1, 44)
ax.set_ylim(-0.7, n_rows - 0.3)
ax.set_xlabel(r'Paramètre $S_e$ (régression Greenup, $n \geq 2$)', labelpad=7)
ax.set_title(r'$S_e$ par nœud — périmètre chapitre 1 (17 nœuds Intel)',
             fontsize=9.5, fontweight='semibold', pad=9)

# Légende architectures
patches = [mpatches.Patch(color=ARCH_COLOR[a], label=a) for a in arch_order]
ax.legend(handles=patches, loc='lower right', ncol=2,
          fontsize=7, handlelength=1, handleheight=0.8, borderpad=0.5)

# Légende LaTeX séparée → voir CRIME/docs/figures/captions.tex (\captionSeParNoeud)

fig.tight_layout()
fig.savefig(OUT / 'se_per_node.pdf', bbox_inches='tight', pad_inches=0.08)
fig.savefig(OUT / 'se_per_node.png', bbox_inches='tight', pad_inches=0.08, dpi=200)
print(f"PDF : {OUT / 'se_per_node.pdf'}")
print(f"PNG : {OUT / 'se_per_node.png'}")

# ── Export se_summary.csv (source de vérité) ──────────────────────────────────
FIELDS = ['arch', 'node', 'site', 'cpu', 'n_max', 'freq_nom',
          'Se', 'ecore_c', 'euncore_c', 'RMSE', 'n_points']
with open(OUT_CSV, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    for r in results:
        meta = METADATA.get(r['label'], {})
        w.writerow({
            'arch':      r['arch'],
            'node':      r['label'],
            'site':      meta.get('site', ''),
            'cpu':       meta.get('cpu', ''),
            'n_max':     r['n_max'],
            'freq_nom':  meta.get('freq_nom', ''),
            'Se':        f"{r['Se']:.4f}",
            'ecore_c':   f"{r['ecore_c']:.6f}",
            'euncore_c': f"{r['euncore_c']:.6f}",
            'RMSE':      f"{r['RMSE']:.6f}",
            'n_points':  r['n_points'],
        })
print(f"CSV : {OUT_CSV}")
print()
print("─── Se par nœud (source de vérité) ───────────────────────────────────────")
print(f"{'arch':<6} {'node':<14} {'Se':>7} {'ecore_c':>12} {'euncore_c':>12} {'RMSE':>10} {'n_pts':>6}")
for r in results:
    print(f"{r['arch']:<6} {r['label']:<14} {r['Se']:7.2f} "
          f"{r['ecore_c']:12.4f} {r['euncore_c']:12.4f} "
          f"{r['RMSE']:10.4f} {r['n_points']:6d}")
