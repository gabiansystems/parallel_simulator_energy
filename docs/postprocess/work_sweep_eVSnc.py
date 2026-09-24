"""
work_sweep_eVSnc.py
===================
Investigation : Se(10M) ≈ 16 vs Se(100M) ≈ 23 — artefact RAPL ou différence physique ?

Méthode : pour chaque taille_charge, tracer E(nombre_coeurs)/E_ref(1) normalisé
sur le même panneau. Si les pentes OLS diffèrent → physique (régimes différents).
Si seul le bruit diffère → artefact de durée de mesure trop courte à 10M.

Sortie : CRIME/docs/figures/work_sweep_eVSnc.pdf / .png
"""

import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent / 'lecture_energie' / 'resultats' / 'work_sweep'
OUT  = Path(__file__).parent.parent / 'docs' / 'figures'
OUT.mkdir(parents=True, exist_ok=True)

ARCH_COLOR = {
    'SNB': '#2a78d6', 'IVB': '#4a3aa7', 'HSW': '#eb6834',
    'BDW': '#1baf7a', 'CLX': '#eda100', 'SKL': '#e87ba4', 'ICX': '#e34948',
}
CLX_COLOR = ARCH_COLOR['CLX']

# ── Fichiers disponibles ──────────────────────────────────────────────────────
TAILLES = [
    ('500K',  5e5,   'work_sweep_nw500K_clx_gros-1.csv',  ':'),
    ('1M',    1e6,   'work_sweep_nw1M_clx_gros-1.csv',    '--'),
    ('10M',   1e7,   'work_sweep_nw10M_clx_gros-1.csv',   '-'),
    ('100M',  1e8,   'work_sweep_nw100M_clx_gros-1.csv',  '-'),
    ('1G',    1e9,   'work_sweep_nw1G_clx_gros-1.csv',    '-'),
]
# Palettes différentes pour distinguer les tailles sur le même panneau
COLORS = ['#aaa', '#888', '#e34948', '#eda100', '#1baf7a']


def ols_greenup(nombre_coeurs_arr, energie_arr):
    """OLS sur E(n) = ecore_c + euncore_c/n, n >= 2.
    Retourne (ecore_c, euncore_c, Se, E_ref_1, rmse).
    E_ref(1) = ecore_c + euncore_c (valeur OLS prédite, pas mesurée)."""
    mask = np.array(nombre_coeurs_arr) >= 2
    nc = np.array(nombre_coeurs_arr)[mask].astype(float)
    en = np.array(energie_arr)[mask]
    if len(nc) < 2:
        return None
    # Régression linéaire : E = a + b*(1/n)  →  a=ecore_c, b=euncore_c
    X = np.column_stack([np.ones(len(nc)), 1.0 / nc])
    coeffs, res, _, _ = np.linalg.lstsq(X, en, rcond=None)
    ecore_c, euncore_c = coeffs
    E_ref_1 = ecore_c + euncore_c
    Se = euncore_c / ecore_c if ecore_c > 0 else float('nan')
    rmse = np.sqrt(np.mean((en - X @ coeffs) ** 2)) if len(res) == 0 else np.sqrt(res[0] / len(nc))
    return ecore_c, euncore_c, Se, E_ref_1, rmse


def charger_csv(chemin):
    """Charge un CSV work_sweep, retourne dict nombre_coeurs → liste(energie)."""
    donnees = {}
    with open(chemin) as f:
        for row in csv.DictReader(f):
            nombre_coeurs = int(row['N_core'])
            energie = float(row['Energy'])
            donnees.setdefault(nombre_coeurs, []).append(energie)
    return donnees


def mediane_par_nc(donnees):
    """Retourne (liste_nc_triée, liste_mediane_energie)."""
    nc_sorted = sorted(donnees)
    medians = [np.median(donnees[nc]) for nc in nc_sorted]
    return nc_sorted, medians


# ── Chargement et OLS ────────────────────────────────────────────────────────
print("Taille       Se        E_ref(1)J   RMSE    n_pts")
print("-" * 55)
resultats = []
for label, n_work, fname, ls in TAILLES:
    chemin = BASE / fname
    if not chemin.exists():
        print(f"  {label:<6}  FICHIER MANQUANT : {chemin}")
        continue
    donnees = charger_csv(chemin)
    nc_list, medians = mediane_par_nc(donnees)
    fit = ols_greenup(nc_list, medians)
    if fit is None:
        print(f"  {label:<6}  OLS impossible (< 2 points)")
        continue
    ecore_c, euncore_c, Se, E_ref_1, rmse = fit
    n_pts = sum(len(v) for v in donnees.values())
    print(f"  {label:<6}  Se={Se:.2f}  E_ref={E_ref_1:.4f}J  RMSE={rmse:.5f}  pts={n_pts}")
    resultats.append((label, n_work, ls, nc_list, medians, ecore_c, euncore_c, Se, E_ref_1))

# ── Figure ───────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
ax_left, ax_right = axes

nc_model = np.linspace(1, 20, 200)

for idx, (label, n_work, ls, nc_list, medians, ecore_c, euncore_c, Se, E_ref_1) in enumerate(resultats):
    couleur = COLORS[idx]
    alpha = 0.5 if label in ('500K', '1M') else 0.9
    lw = 1.2 if label in ('500K', '1M') else 1.8

    # Panneau gauche : E(nombre_coeurs)/E_ref(1) mesuré + courbe OLS
    en_norm = [m / E_ref_1 for m in medians]
    ax_left.plot(nc_list, en_norm, 'o', color=couleur, ms=4, alpha=alpha)
    fit_norm = (ecore_c + euncore_c / nc_model) / E_ref_1
    ax_left.plot(nc_model, fit_norm, ls=ls, color=couleur, lw=lw,
                 label=f"{label}  (Sₑ={Se:.1f})")

    # Panneau droit : Se en fonction de taille_charge (valeur OLS scalaire)
    ax_right.plot(n_work, Se, 'o', color=couleur, ms=8)
    ax_right.annotate(label, (n_work, Se), textcoords="offset points",
                      xytext=(5, 2), fontsize=8, color=couleur)

# Décoration panneau gauche
ax_left.set_xlabel("Nombre de cœurs $n_c$", fontsize=10)
ax_left.set_ylabel("$E(n_c) / \\hat{E}_{\\mathrm{ref}}(1)$", fontsize=10)
ax_left.set_title("Énergie normalisée par taille de charge\n(gros-1, CLX, OLS $n_c \\geq 2$)", fontsize=10)
ax_left.set_xlim(0, 20)
ax_left.set_ylim(0, 1.05)
ax_left.axhline(1.0, color='grey', lw=0.8, ls='--')
ax_left.legend(fontsize=8, title="n_work", title_fontsize=8)
ax_left.grid(True, alpha=0.3)

# Décoration panneau droit
ax_right.set_xscale('log')
ax_right.set_xlabel("n_work (opérations)", fontsize=10)
ax_right.set_ylabel("$S_e$ (moindres carrés, $n_c \\geq 2$)", fontsize=10)
ax_right.set_title("Sₑ vs taille de charge\n(pente OLS — constante = physique)", fontsize=10)
ax_right.axhline(resultats[-1][7] if resultats else 22, color='grey',
                 lw=1, ls=':', label=f"plateau (1G)")
ax_right.set_ylim(0, 30)
ax_right.grid(True, alpha=0.3)
ax_right.legend(fontsize=8)

# Annotation RAPL floor
if any(l in ('500K', '1M') for l, *_ in resultats):
    ax_left.text(1.5, 0.98, "↑ proche plancher RAPL\n(durée < 15 ms)",
                 fontsize=7, color='#888', va='top')

plt.tight_layout()
for ext in ('pdf', 'png'):
    fig.savefig(OUT / f'work_sweep_eVSnc.{ext}', dpi=150, bbox_inches='tight')
    print(f"Sauvegardé : {OUT}/work_sweep_eVSnc.{ext}")

plt.close()
