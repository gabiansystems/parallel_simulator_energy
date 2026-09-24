"""
freq_sweep.py
=============
Figure robustesse §2.2 — Sensibilité de Se à la fréquence fixée.

Données : lecture_energie/resultats/freq_sweep/freq_sweep_<F>MHz_<arch>_<node>.csv
Format : CSV standard counter3 (Energy, Time, N_core, Seq_frac, …)

Si plusieurs fréquences et n_c ≥ 2 → trace Se_OLS(f) via OLS par fréquence.
Si n_c=1 uniquement (cas econome-6 / intel_pstate) → trace E_med(f) normalisée.

Sortie :
  CRIME/docs/figures/freq_sweep.pdf
"""

import csv
import re
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

BASE = Path(__file__).parent.parent.parent / 'lecture_energie' / 'resultats' / 'freq_sweep'
OUT  = Path(__file__).parent.parent / 'docs' / 'figures'
OUT.mkdir(parents=True, exist_ok=True)

ARCH_COLOR = {
    'SNB': '#2a78d6', 'IVB': '#4a3aa7', 'HSW': '#eb6834',
    'BDW': '#1baf7a', 'CLX': '#eda100', 'SKL': '#e87ba4', 'ICX': '#e34948',
}

def load_csv(path):
    """Retourne dict {n_c: [E, ...]} pour seq_frac=0."""
    rows = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            if float(r['Seq_frac']) != 0.0:
                continue
            n = int(float(r['N_core']))
            rows.setdefault(n, []).append(float(r['Energy']))
    return rows


def ols_Se(rows):
    ns = sorted(n for n in rows if n >= 2)
    if len(ns) < 2:
        return None, None, None
    E = np.array([np.median(rows[n]) for n in ns])
    X = np.column_stack([np.ones(len(ns)), 1.0 / np.array(ns)])
    ec, eu = np.linalg.lstsq(X, E, rcond=None)[0]
    return eu / ec, ec, eu


csvs = sorted(BASE.glob('freq_sweep_*.csv'))
if not csvs:
    print(f"Aucun CSV dans {BASE} — expérience à relancer.")
    print("Note : sur intel_pstate (SKL+), le gouverneur userspace est bloqué.")
    print("       Relancer sur un nœud BDW/HSW : ./launch_scripts/g5k_freq_bench.sh ecotype-2")
    raise SystemExit(0)

# Extraire fréquence et arch/node du nom de fichier
# Pattern : freq_sweep_<F>MHz_<arch>_<node>.csv
PAT = re.compile(r'freq_sweep_(\d+)MHz_([a-z]+)_(.+)\.csv')

points = []
for p in csvs:
    m = PAT.match(p.name)
    if not m:
        continue
    freq_mhz = int(m.group(1))
    arch = m.group(2).upper()
    node = m.group(3)
    rows = load_csv(p)
    se, ec, eu = ols_Se(rows)
    e_nc1 = np.median(rows.get(1, [])) if 1 in rows else None
    points.append({'freq': freq_mhz, 'arch': arch, 'node': node,
                   'Se': se, 'E1': e_nc1, 'rows': rows})

if not points:
    print("Aucun CSV valide trouvé.")
    raise SystemExit(1)

# Grouper par (arch, node)
from itertools import groupby
nodes_seen = {}
for pt in points:
    key = (pt['arch'], pt['node'])
    nodes_seen.setdefault(key, []).append(pt)

fig, ax = plt.subplots(figsize=(6, 4))
has_Se = any(pt['Se'] is not None for pt in points)

for (arch, node), pts in nodes_seen.items():
    pts.sort(key=lambda x: x['freq'])
    color = ARCH_COLOR.get(arch, '#888888')
    freqs = [p['freq'] for p in pts]

    if has_Se and pts[0]['Se'] is not None:
        ses = [p['Se'] for p in pts]
        se_nom = ses[len(ses) // 2]  # fréquence nominale ≈ milieu
        ses_norm = [s / se_nom for s in ses]
        ax.plot(freqs, ses_norm, 'o-', color=color, label=f'{arch} {node}', lw=1.5, ms=5)
        ax.axhline(1.0, color='#aaaaaa', lw=0.8, ls='--')
        ax.set_ylabel(r'$S_e(f)\;/\;S_e(f_\mathrm{nom})$')
        ax.set_title(r'Stabilité de $S_e$ vs fréquence fixée')
    else:
        # Seul n_c=1 disponible → tracer E normalisée
        e1s = [p['E1'] for p in pts if p['E1'] is not None]
        if not e1s:
            continue
        e_nom = e1s[len(e1s) // 2]
        e_norm = [e / e_nom for e in e1s]
        ax.plot(freqs[:len(e_norm)], e_norm, 'o-', color=color,
                label=f'{arch} {node} (n_c=1)', lw=1.5, ms=5)
        ax.axhline(1.0, color='#aaaaaa', lw=0.8, ls='--')
        ax.set_ylabel(r'$E(f)\;/\;E(f_\mathrm{nom})$  [n_c=1]')
        ax.set_title(r'Énergie vs fréquence fixée (n_c=1 — $S_e$ non calculable)')

ax.set_xlabel('Fréquence fixée (MHz)')
ax.legend(fontsize=8)
ax.grid(True, lw=0.4, alpha=0.5)

if not has_Se:
    ax.text(0.5, 0.05,
            "Note : cpupower userspace bloqué sur intel_pstate (SNB/CLX+) — "
            "1 seul point de fréquence disponible.",
            transform=ax.transAxes, ha='center', fontsize=7, color='#c00000')

for ext in ('pdf', 'png'):
    out = OUT / f'freq_sweep.{ext}'
    fig.savefig(out, bbox_inches='tight', dpi=150)
    print(f'Écrit : {out}')

plt.close(fig)
print(f"\n{len(points)} point(s) de fréquence, {len(nodes_seen)} nœud(s).")
if not has_Se:
    print("ACTION REQUISE : relancer sur BDW ecotype-2 (acpi-cpufreq, n_cores=10).")
    print("  Fixer n_cores=10 dans freq_sweep_bench.sh avant de relancer.")
