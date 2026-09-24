"""
analyze_para_seq_comm.py
Analyse de la campagne 2 : sweep seq_fraction × nbarriers.
Usage:
    python3 analyze_para_seq_comm.py <csv> --name <ARCH_NODE> [--output <dir>]
"""

import os, sys, argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import seaborn as sns
import warnings
warnings.filterwarnings("ignore")

# ── import fonctions communes depuis analyze_emb_para ─────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from analyze_emb_para import (
    greenup_model, ratio_model,
    mad_filter_df, mad_filter_list, compute_greenup,
    regress_ratio, analyze_distribution, signaturebar,
)


# ── plots par combinaison (s, b) ──────────────────────────────────────────────

def plot_greenup_combo(df_group, cores, ratio_fit, seq_frac, barrier, title, out_path, file_path):
    """Greenup boxplot + modèle pour une combinaison (seq_frac, barrier)."""
    est = greenup_model(cores, ratio_fit, barrier, seq_frac)
    pos = np.arange(len(cores))
    fig, ax = plt.subplots(figsize=(7, 4))
    sns.boxplot(data=df_group, x="N_core", y="greenup", palette="Blues", ax=ax)
    ax.plot(pos, est, 'C1-', lw=2, label=f"$S_{{e,\\mathrm{{fit}}}}$={ratio_fit:.2f}")
    ax.plot(pos, cores, 'k-.', lw=1, label="speedup théorique")
    ax.set_xlabel("Nombre de cœurs"); ax.set_ylabel("Greenup")
    ax.set_title(title); ax.legend(fontsize=8)
    plt.tight_layout(); signaturebar(fig, file_path)
    plt.savefig(out_path, dpi=200, bbox_inches='tight'); plt.close()


# ── Se vs Seq_frac (Barrier fixé) ────────────────────────────────────────────

def plot_Se_vs_seqfrac(summary, name, output_dir, file_path):
    """Se en fonction de seq_frac, une courbe par valeur de Barrier."""
    barriers = sorted(summary["Barrier"].unique())
    fig, ax = plt.subplots(figsize=(7, 4))
    colors = plt.cm.viridis(np.linspace(0.2, 0.9, len(barriers)))
    for col, b in zip(colors, barriers):
        sub = summary[summary["Barrier"] == b].sort_values("Seq_frac")
        label = "sans barrière" if b == 0 else f"{int(b)} barrières"
        ax.plot(sub["Seq_frac"], sub["Se"], 'o-', color=col, label=label)
    ax.set_xlabel("Fraction séquentielle $s$")
    ax.set_ylabel("$S_e$ (scalabilité énergétique)")
    ax.set_title(f"{name} — $S_e$ vs fraction séquentielle")
    ax.xaxis.set_major_formatter(ticker.PercentFormatter(xmax=1))
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3)
    plt.tight_layout(); signaturebar(fig, file_path)
    plt.savefig(os.path.join(output_dir, "Se_vs_seqfrac.png"), dpi=200, bbox_inches='tight')
    plt.close()


# ── Se vs Barrier (Seq_frac fixé) ────────────────────────────────────────────

def plot_Se_vs_barriers(summary, name, output_dir, file_path):
    """Se en fonction du nombre de barrières, une courbe par seq_frac."""
    seqfracs = sorted(summary["Seq_frac"].unique())
    fig, ax = plt.subplots(figsize=(7, 4))
    colors = plt.cm.plasma(np.linspace(0.1, 0.85, len(seqfracs)))
    for col, s in zip(colors, seqfracs):
        sub = summary[summary["Seq_frac"] == s].sort_values("Barrier")
        label = f"s={s:.0%}"
        ax.plot(sub["Barrier"], sub["Se"], 'o-', color=col, label=label)
    ax.set_xlabel("Nombre de barrières")
    ax.set_ylabel("$S_e$ (scalabilité énergétique)")
    ax.set_title(f"{name} — $S_e$ vs nombre de barrières")
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3)
    plt.tight_layout(); signaturebar(fig, file_path)
    plt.savefig(os.path.join(output_dir, "Se_vs_barriers.png"), dpi=200, bbox_inches='tight')
    plt.close()


# ── Heatmap Se ────────────────────────────────────────────────────────────────

def plot_heatmap(summary, name, output_dir, file_path):
    """Heatmap de Se : lignes=Barrier, colonnes=Seq_frac."""
    pivot = summary.pivot(index="Barrier", columns="Seq_frac", values="Se")
    pivot.index = [("sans bar." if b == 0 else f"{int(b)} bar.") for b in pivot.index]
    pivot.columns = [f"s={v:.0%}" for v in pivot.columns]
    fig, ax = plt.subplots(figsize=(6, 3.5))
    sns.heatmap(pivot, annot=True, fmt=".1f", cmap="YlOrRd_r",
                linewidths=0.5, ax=ax, cbar_kws={"label": "$S_e$"})
    ax.set_title(f"{name} — $S_e$ (seq × barrières)")
    ax.set_xlabel("Fraction séquentielle"); ax.set_ylabel("Barrières")
    plt.tight_layout(); signaturebar(fig, file_path)
    plt.savefig(os.path.join(output_dir, "Se_heatmap.png"), dpi=200, bbox_inches='tight')
    plt.close()


# ── Heatmap RMSE ──────────────────────────────────────────────────────────────

def plot_heatmap_rmse(summary, name, output_dir, file_path):
    """Heatmap RMSE du fit : indique où le modèle dévie."""
    pivot = summary.pivot(index="Barrier", columns="Seq_frac", values="RMSE_pct")
    pivot.index = [("sans bar." if b == 0 else f"{int(b)} bar.") for b in pivot.index]
    pivot.columns = [f"s={v:.0%}" for v in pivot.columns]
    fig, ax = plt.subplots(figsize=(6, 3.5))
    sns.heatmap(pivot, annot=True, fmt=".1f", cmap="Reds",
                linewidths=0.5, ax=ax, cbar_kws={"label": "RMSE (%)"})
    ax.set_title(f"{name} — RMSE fit Greenup (%)")
    ax.set_xlabel("Fraction séquentielle"); ax.set_ylabel("Barrières")
    plt.tight_layout(); signaturebar(fig, file_path)
    plt.savefig(os.path.join(output_dir, "RMSE_heatmap.png"), dpi=200, bbox_inches='tight')
    plt.close()


# ── Greenup superposé : toutes seq_fracs, barrier=0 ─────────────────────────

def plot_greenup_nobar_allseq(df, summary, name, output_dir, file_path):
    """Courbes greenup pour barrier=0, une courbe par seq_frac superposées."""
    sub = df[df["Barrier"] == 0].copy()
    if sub.empty:
        return
    seq_fracs = sorted(sub["Seq_frac"].unique())
    colors = plt.cm.plasma(np.linspace(0.1, 0.85, len(seq_fracs)))
    fig, ax = plt.subplots(figsize=(7, 4.5))

    for col, s in zip(colors, seq_fracs):
        grp = sub[sub["Seq_frac"] == s]
        cores = sorted(grp["N_core"].unique())
        pos = np.arange(len(cores))

        medians = [grp[grp["N_core"] == c]["greenup"].median() for c in cores]
        row = summary[(summary["Seq_frac"] == s) & (summary["Barrier"] == 0)]
        Se_fit = float(row["Se_fit"].iloc[0]) if not row.empty else None

        ax.plot(pos, medians, 'o-', color=col, label=f"s={s:.0%}", lw=1.5, ms=5)
        if Se_fit is not None:
            est = greenup_model(np.array(cores, dtype=float), Se_fit, 0, s)
            ax.plot(pos, est, '--', color=col, alpha=0.5, lw=1)

    cores_all = sorted(sub["N_core"].unique())
    ax.plot(np.arange(len(cores_all)), sorted(cores_all), 'k:', lw=1, label="speedup idéal")
    ax.set_xticks(np.arange(len(cores_all)))
    ax.set_xticklabels([str(c) for c in sorted(cores_all)], fontsize=8)
    ax.set_xlabel("Nombre de cœurs")
    ax.set_ylabel("Greenup")
    ax.set_title(f"{name} — Greenup sans barrières, toutes fractions séquentielles")
    ax.legend(fontsize=8, ncol=2); ax.grid(True, alpha=0.3)
    plt.tight_layout(); signaturebar(fig, file_path)
    plt.savefig(os.path.join(output_dir, "greenup_nobar_allseq.png"), dpi=200, bbox_inches='tight')
    plt.close()


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file_path")
    parser.add_argument("--name", default="node")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    # répertoire de sortie
    base = args.output or os.path.join(os.path.dirname(args.file_path), "images")
    output_dir = os.path.join(base, args.name)
    os.makedirs(output_dir, exist_ok=True)

    df = pd.read_csv(args.file_path)
    df = compute_greenup(df)

    seq_fracs = sorted(df["Seq_frac"].unique())
    barriers  = sorted(df["Barrier"].unique())
    cores_all = sorted(df["N_core"].unique())

    summary_rows = []

    print(f"\n{'='*60}")
    print(f"  {args.name}  —  {len(seq_fracs)} seq × {len(barriers)} barriers × {len(cores_all)} cœurs")
    print(f"{'='*60}")

    for s in seq_fracs:
        for b in barriers:
            grp = df[(df["Seq_frac"] == s) & (df["Barrier"] == b)].copy()
            if grp.empty:
                continue

            cores = sorted(grp["N_core"].unique())

            # Se : médiane MAD-filtrée des ratios par ligne
            ratios = []
            for _, row in grp.iterrows():
                try:
                    v = ratio_model(row["greenup"], row["N_core"], b, s)
                    if np.isfinite(v) and v > 0:
                        ratios.append(v)
                except Exception:
                    pass
            se_vals = mad_filter_list(ratios, k=5)
            Se = float(np.median(se_vals)) if se_vals else np.nan

            # Se_fit : régression sur la courbe globale
            ratio_fit, rmse_pct = regress_ratio(grp)

            label_s = f"s={s:.0%}"
            label_b = "sans bar." if b == 0 else f"{int(b)} bar."
            print(f"  [{label_s}, {label_b}]  Se_fit={ratio_fit:.3f}  RMSE={rmse_pct:.2f}%  Se={Se:.3f}")

            summary_rows.append({
                "Seq_frac": s, "Barrier": b,
                "Se": Se, "Se_fit": ratio_fit, "RMSE_pct": rmse_pct,
                "N_cores": len(cores),
            })

            # plot greenup pour cette combinaison
            title = f"{args.name} — {label_s}, {label_b}"
            fname = f"greenup_s{int(s*100):02d}_b{int(b)}.png"
            plot_greenup_combo(
                grp, np.array(cores, dtype=float), ratio_fit,
                s, b, title,
                os.path.join(output_dir, fname),
                args.file_path,
            )

    summary = pd.DataFrame(summary_rows)
    csv_out = os.path.join(output_dir, "summary.csv")
    summary.to_csv(csv_out, index=False)
    print(f"\n  summary → {csv_out}")

    # plots de synthèse
    plot_Se_vs_seqfrac(summary, args.name, output_dir, args.file_path)
    plot_Se_vs_barriers(summary, args.name, output_dir, args.file_path)
    plot_heatmap(summary, args.name, output_dir, args.file_path)
    plot_heatmap_rmse(summary, args.name, output_dir, args.file_path)
    plot_greenup_nobar_allseq(df, summary, args.name, output_dir, args.file_path)
    print(f"  plots → {output_dir}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
