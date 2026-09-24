"""
validate_nstat.py
=================
Validation du protocole de mesure énergétique : stabilité statistique et
précision de quantification RAPL.

Figures produites :
  CRIME/docs/figures/validation_nstat.pdf   — pour inclusion manuscrit
  CRIME/docs/figures/validation_nstat.png   — aperçu

Méthode — panneau gauche :
  Pour chaque architecture, on prend les 30 premières mesures de la campagne
  parallel_sim à n_c = N_{c,max} et seq_fraction = 0 (séquence entrelacée :
  les répétitions alternent n_c=max → n_c=max-1 → … → 2 pour neutraliser
  les dérives thermiques). On calcule ensuite :
    CV(n_stat) = std(E[1..n_stat]) / mean(E[1..n_stat])
  en faisant croître n_stat de 2 à 30. Cela montre à partir de combien de
  répétitions CV(E) se stabilise — ici n_stat=30 est justifié (CV < 3 % dès
  n_stat ≈ 15 pour 4 architectures sur 5).

Méthode — panneau droit :
  Pour chaque architecture, on calcule le rapport E / ESU_RAPL à deux niveaux
  de parallélisme : n_c = 2 (énergie maximale, travail peu divisé) et
  n_c = N_{c,max} (énergie minimale, travail le plus divisé — cas le plus
  défavorable pour la marge de quantification). L'ESU est une constante
  matérielle lue dans le MSR 0x606 (champ ESU) :
    - 15.3 µJ pour SNB, BDW, SKL, CLX  (ESU = 2^-16 J)
    -  3.82 µJ pour ICX                  (ESU = 2^-18 J)
  Même à n_c = N_{c,max}, le rapport E/ESU reste ≥ 50 000 :
  l'erreur de quantification est < 0.002 % quelle que soit l'architecture.

Ref : Intel SDM vol. 3B §14.9.1 (RAPL MSR); Marsaglia 2003 (RNG).
"""

import numpy as np
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.patches import Patch
from pathlib import Path

# ── Configuration des architectures ──────────────────────────────────────────
ARCHS = {
    'SNB': {'color': '#1D6FBF', 'file': 'parallel_sim_snb_econome-6.csv',    'ncmax': 8,  'rapl_uJ': 15.3},
    'BDW': {'color': '#0E9E8E', 'file': 'parallel_sim_bdw_ecotype-2.csv',    'ncmax': 10, 'rapl_uJ': 15.3},
    'SKL': {'color': '#2EA04A', 'file': 'parallel_sim_skl_dahu-1.csv',       'ncmax': 16, 'rapl_uJ': 15.3},
    'CLX': {'color': '#6B3FA0', 'file': 'parallel_sim_clx_gros-1_fixed.csv', 'ncmax': 18, 'rapl_uJ': 15.3},
    'ICX': {'color': '#C93030', 'file': 'parallel_sim_icx_chirop-1.csv',     'ncmax': 32, 'rapl_uJ': 3.82},
}

BASE = Path(__file__).parent.parent / 'resultats' / 'parallel_sim'
OUT  = Path(__file__).parent.parent / 'docs' / 'figures'
OUT.mkdir(parents=True, exist_ok=True)

# ── Chargement ────────────────────────────────────────────────────────────────
CV_DATA    = {}
MEANS_NMAX = {}  # E à n_c = N_max (cas défavorable : travail le plus divisé)
MEANS_N2   = {}  # E à n_c = 2     (cas favorable : travail peu divisé)

for arch, cfg in ARCHS.items():
    en2, enmax = [], []
    with open(BASE / cfg['file']) as f:
        for row in csv.DictReader(f):
            if float(row['Seq_frac']) != 0.0:
                continue
            nc = int(float(row['N_core']))
            if nc == cfg['ncmax']:
                enmax.append(float(row['Energy']))
            elif nc == 2:
                en2.append(float(row['Energy']))
    e = np.array(enmax[:30])
    CV_DATA[arch]    = [float(np.std(e[:k], ddof=1) / np.mean(e[:k]) * 100)
                        for k in range(2, len(e) + 1)]
    MEANS_NMAX[arch] = float(e.mean())
    MEANS_N2[arch]   = float(np.array(en2).mean()) if en2 else MEANS_NMAX[arch]

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
    'legend.fontsize':   8,
})

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13 / 2.54 * 2, 7 / 2.54 * 2),
                                 gridspec_kw={'wspace': 0.42})

# ── Panneau gauche : CV(n_stat) à n_c = N_{c,max} ────────────────────────────
for arch, cv in CV_DATA.items():
    xs = np.arange(2, len(cv) + 2)
    ax1.plot(xs, cv, color=ARCHS[arch]['color'], linewidth=1.5, label=arch,
             solid_capstyle='round', solid_joinstyle='round')
    ax1.scatter([xs[-1]], [cv[-1]], color=ARCHS[arch]['color'], s=18, zorder=5)

ax1.axhline(3, color='#B45309', linewidth=1.2, linestyle=(0, (5, 4)), label='seuil 3 %')
ax1.axvline(30, color='#888888', linewidth=0.8, linestyle=(0, (3, 4)))
ax1.text(30.4, 7.6, r'$n_\mathrm{stat}$=30', fontsize=7.5, color='#666666', va='top')

ax1.annotate(r'ICX : plancher $\approx$6 %' + '\n' + r'(non réductible par $n_\mathrm{stat}$)',
             xy=(18, CV_DATA['ICX'][16]), xytext=(5, 6.3),
             fontsize=7, color='#C93030',
             arrowprops=dict(arrowstyle='->', color='#C93030', lw=0.8),
             bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='none', alpha=0.8))

ax1.set_xlim(2, 30)
ax1.set_ylim(0, 8)
ax1.set_xlabel(r"$n_\mathrm{stat}$ (nombre de répétitions)", labelpad=6)
ax1.set_ylabel("Coefficient de variation CV (%)", labelpad=6)
ax1.set_title(r"Convergence de CV(E) selon $n_\mathrm{stat}$" + "\n"
              r"($n_c = N_{c,\max}$,  seq\_fraction = 0,  séquence entrelacée)",
              fontsize=8.5, fontweight='semibold', pad=8)
ax1.yaxis.set_major_formatter(ticker.FormatStrFormatter('%g %%'))
ax1.grid(axis='y')
ax1.legend(loc='upper right', ncol=1, handlelength=1.6)

# ── Panneau droit : E / ESU — n_c=2 et n_c=N_max ────────────────────────────
arch_names = list(ARCHS.keys())
BAR_H  = 0.62
GAP    = 0.22   # entre les deux barres d'un même groupe
STRIDE = 2.0    # espacement entre groupes

y_nmax = np.array([i * STRIDE          for i in range(len(arch_names))])
y_n2   = np.array([i * STRIDE + BAR_H + GAP for i in range(len(arch_names))])

ratios_nmax = [MEANS_NMAX[a] * 1e6 / ARCHS[a]['rapl_uJ'] for a in arch_names]
ratios_n2   = [MEANS_N2[a]   * 1e6 / ARCHS[a]['rapl_uJ'] for a in arch_names]

for i, arch in enumerate(arch_names):
    c = ARCHS[arch]['color']

    # Barre n_c = N_max (pleine — cas défavorable)
    ax2.barh(y_nmax[i], np.log10(ratios_nmax[i]), height=BAR_H,
             color=c, alpha=0.90, edgecolor='none')
    ax2.text(np.log10(ratios_nmax[i]) + 0.05, y_nmax[i],
             f'×{int(round(ratios_nmax[i]/1000))} k',
             va='center', fontsize=7.5, color=c, fontweight='semibold')

    # Barre n_c = 2 (hachurée — cas favorable, référence)
    ax2.barh(y_n2[i], np.log10(ratios_n2[i]), height=BAR_H,
             color=c, alpha=0.28, edgecolor=c, linewidth=0.7)
    ax2.text(np.log10(ratios_n2[i]) + 0.05, y_n2[i],
             f'×{int(round(ratios_n2[i]/1000))} k',
             va='center', fontsize=7, color=c, alpha=0.65)

ax2.axvline(np.log10(1000), color='#B45309', linewidth=1.2, linestyle=(0, (5, 4)))
ax2.text(np.log10(1000) + 0.05, y_n2[-1] + BAR_H * 0.5 + 0.35,
         'seuil min.\n(×1 000)', fontsize=7, color='#B45309', va='bottom')

# Légende groupes
legend_els = [
    Patch(facecolor='grey', alpha=0.90,
          label=r'$n_c = N_{c,\max}$  (travail divisé au maximum)'),
    Patch(facecolor='grey', alpha=0.28, edgecolor='grey', linewidth=0.7,
          label=r'$n_c = 2$  (travail peu divisé)'),
]
ax2.legend(handles=legend_els, loc='lower right', fontsize=7, handlelength=1.2,
           handletextpad=0.5)

# Yticks au centre de chaque groupe
y_mid = (y_nmax + y_n2) / 2
ax2.set_yticks(y_mid)
ax2.set_yticklabels(arch_names, fontsize=9)
ax2.set_xlabel(r"$E$ / ESU$_\mathrm{RAPL}$  (log$_{10}$)", labelpad=6)
ax2.set_title("Marge de quantification RAPL\n"
              r"($E$ / ESU à deux niveaux de parallélisme)",
              fontsize=8.5, fontweight='semibold', pad=8)
ax2.xaxis.set_major_formatter(ticker.FuncFormatter(
    lambda x, _: f'$10^{{{int(x)}}}$'))
ax2.set_xlim(3, 6.8)
ax2.set_ylim(-0.5, y_n2[-1] + BAR_H + 0.8)
ax2.grid(axis='x')

note = "ESU RAPL : 15,3 µJ (SNB–CLX), 3,82 µJ (ICX) — Intel SDM vol. 3B §14.9.1"
ax2.text(0, -0.17, note, transform=ax2.transAxes, fontsize=6.5, color='#666666')

# ── Titre global ──────────────────────────────────────────────────────────────
fig.suptitle("Validation du protocole de mesure — 5 architectures Intel",
             fontsize=10.5, fontweight='semibold', y=1.01)

# Légende LaTeX séparée → voir CRIME/docs/figures/captions.tex (\captionNstat)

fig.savefig(OUT / 'validation_nstat.pdf', bbox_inches='tight', pad_inches=0.08)
fig.savefig(OUT / 'validation_nstat.png', bbox_inches='tight', pad_inches=0.08, dpi=200)
print(f"Figures sauvegardées dans {OUT}")