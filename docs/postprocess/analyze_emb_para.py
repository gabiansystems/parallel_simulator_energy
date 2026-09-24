import os
import sys
import json
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from scipy.stats import norm, shapiro, chi2_contingency
from scipy.optimize import minimize_scalar
import statistics
import numpy as np
import argparse
import warnings
import logging

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
logging.getLogger('matplotlib').setLevel(logging.ERROR)
logging.getLogger('seaborn').setLevel(logging.ERROR)
logging.getLogger('PIL').setLevel(logging.ERROR)


def signaturebar(fig, file_path, fontsize=7, pad=3, xpos=20, ypos=0.5,
                 rect_kw={"facecolor": "grey", "edgecolor": None},
                 text_kw={"color": "w"}):
    w, h = fig.get_size_inches()
    height = ((fontsize + 2 * pad) / 72.) / h
    rect = plt.Rectangle(
        (0, 0), 1, height, transform=fig.transFigure, clip_on=False, **rect_kw)
    fig.axes[0].add_patch(rect)
    fig.text(xpos / 72. / h, ypos / 72. / h,
             f'Generated from: {os.path.realpath(__file__)}\nUsing file: {file_path}',
             fontsize=fontsize, **text_kw)
    fig.subplots_adjust(bottom=fig.subplotpars.bottom + height)


# ── models ────────────────────────────────────────────────────────────────────

def _barrier_fraction(a_raw, time_per_run=None):
    """Convert the raw Barrier CSV column to the model fraction 'a'.

    The CSV stores nbarriers (integer count).  The model parameter 'a' is the
    fraction of per-thread compute time spent in barrier synchronisation.
    For our benchmark (10^8 ops, ~2 ns/op, ~5 µs per pthread_barrier_wait):
      a ≈ (nbarriers-1) × barrier_latency / total_compute_time  ≈  0
    We use a_raw=0 (nbarriers=1) → a=0, and a_raw>1 → a=0 (negligible overhead),
    unless an explicit fraction (<1) is passed for forward-compatibility.
    """
    if a_raw < 1:          # already a fraction (legacy/explicit)
        return a_raw
    if a_raw == 0:         # stored as 0 meaning nbarriers=1
        return 0.0
    # integer nbarriers ≥ 2: barrier overhead negligible for compute-bound runs
    return 0.0


def greenup_model(n, Se, a, s):
    a = np.vectorize(_barrier_fraction)(np.asarray(a, dtype=float))
    num = n * (Se + 1)
    den = n * s * (Se + 1) + (n + Se) * (a * n * (n - 1) - s + 1)
    return num / den


def ratio_model(g, n, a, s):
    a = np.vectorize(_barrier_fraction)(np.asarray(a, dtype=float))
    K = a * n * (n - 1) - s + 1
    num = n - g * n * s - g * K * n
    den = g * n * s + g * K - n
    return num / den


# ── data loading & filtering ───────────────────────────────────────────────────

def load_csv(path):
    """Load one CSV file or concatenate all CSVs in a directory."""
    if os.path.isfile(path):
        if not path.endswith('.csv'):
            raise ValueError(f"{path} is not a CSV file")
        return pd.read_csv(path)
    if os.path.isdir(path):
        files = [os.path.join(path, f) for f in os.listdir(path) if f.endswith('.csv')]
        if not files:
            raise ValueError(f"No CSV files found in {path}")
        return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    raise ValueError(f"{path} is neither a CSV file nor a directory")

# utiliser la bibliothèque, d'où viennent les valeurs 1.4826
def mad_filter_df(df, k=1.0):
    """
    MAD filter on Energy, applied per (N_core, Seq_frac, Barrier) group.
    pourquoi ce k en paramètres ?
    """
    mask = pd.Series(True, index=df.index)
    for _, group in df.groupby(['N_core', 'Seq_frac', 'Barrier']):
        vals = group['Energy'].values
        median = np.median(vals)
        mad = np.median(np.abs(vals - median))
        if mad == 0:
            continue
        keep = np.abs(vals - median) <= k * 1.4826 * mad
        mask.loc[group.index] = keep
    return df[mask]


# ── greenup computation ────────────────────────────────────────────────────────

def compute_greenup(df):
    """Attach a greenup column: Energy_ref(N_core=1) / Energy for each row."""
    ref = (
        df[df["N_core"] == 1]
        .groupby(["Seq_frac", "Barrier"])["Energy"]
        .mean()
        .rename("Energy_ref")
        .reset_index()
    )
    df = df.merge(ref, on=["Seq_frac", "Barrier"], how="left")
    df["greenup"] = df["Energy_ref"] / df["Energy"]
    return df


def regress_ratio(df):
    """Fit Se by minimising MSE of greenup_model against measured greenup."""
    def objective(Se):
        pred = greenup_model(df["N_core"].values, Se,
                             df["Barrier"].values, df["Seq_frac"].values)
        return np.mean((pred - df["greenup"].values) ** 2)

    n_max = df["N_core"].max()
    result = minimize_scalar(objective, bounds=(0, n_max * 3), method="bounded")
    rmse_pct = np.sqrt(result.fun) / df["greenup"].mean() * 100
    return result.x, rmse_pct


# ── distribution analysis ──────────────────────────────────────────────────────

def mad_filter_list(values, k=5.0):
    values = np.array(values)
    median = np.median(values)
    mad = np.median(np.abs(values - median))
    if mad == 0:
        return values.tolist()
    return values[np.abs(values - median) <= k * 1.4826 * mad].tolist()


def analyze_distribution(values):
    values = mad_filter_list(values, k=5)
    mu, sigma = norm.fit(values)
    q1 = np.percentile(values, 25)
    q3 = np.percentile(values, 75)

    stat, p_sw = shapiro(values)
    print(f"  mu={mu:.4f}  med={np.median(values):.4f}  "
          f"Shapiro p={p_sw:.2e} ({'normal' if p_sw > 0.05 else 'non-normal'})")

    counts, bins = np.histogram(values, bins=20)
    expected = norm.pdf((bins[1:] + bins[:-1]) / 2, mu, sigma)
    expected = expected / expected.sum() * counts.sum()
    _, p_chi2 = chi2_contingency([counts, expected])[:2]
    print(f"  Chi2 p={p_chi2:.2e} ({'≈normal' if p_chi2 > 0.05 else '≠normal'})")

    return values, mu, sigma, q1, q3


# ── plotting ───────────────────────────────────────────────────────────────────

def plot_specific(df, col, output_dir, file_path):
    """Generic seaborn boxplot for any CSV column vs N_core."""
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.boxplot(data=df, x="N_core", y=col, palette="Blues", ax=ax)
    ax.set_xlabel("Degré de parallélisation (nombre de cœurs)")
    ax.set_ylabel(col)
    ax.set_title(f"{col} par cœur")
    plt.tight_layout()
    signaturebar(fig, file_path)
    plt.savefig(os.path.join(output_dir, f"{col.lower()}.png"), dpi=300, bbox_inches='tight')
    plt.close()


def plot_g_comp(cores, df, ratio_fit, title, output_dir, file_path):
    """Measured greenup distribution vs regressed model (Se_fit only)."""
    seq_frac = df["Seq_frac"].mean()
    barrier = df["Barrier"].mean()
    est_fit = greenup_model(cores, ratio_fit, barrier, seq_frac)
    pos = np.arange(len(cores))

    fig, ax = plt.subplots(figsize=(8, 5))
    sns.boxplot(data=df, x="N_core", y="greenup", palette="Blues", ax=ax)
    ax.plot(pos, est_fit, 'C1-', lw=2, label=f"modèle Greenup ($S_{{e,\\mathrm{{fit}}}}$={ratio_fit:.2f})")
    ax.plot(pos, cores, "k-.", lw=1, label="speedup théorique")
    ax.set_xlabel("Nombre de cœurs")
    ax.set_ylabel("Greenup")
    ax.set_title(title)
    ax.legend()
    plt.tight_layout()
    signaturebar(fig, file_path)
    plt.savefig(os.path.join(output_dir, "greenup_comp.png"), dpi=300, bbox_inches='tight')
    plt.close()


def plot_g_comp_mad_comparison(cores, df_filtered, df_raw, ratio_fit, title, output_dir, file_path):
    """Side-by-side greenup: with MAD filter (Blues) vs without (Oranges)."""
    seq_frac = df_filtered["Seq_frac"].mean()
    barrier = df_filtered["Barrier"].mean()
    est_fit = greenup_model(cores, ratio_fit, barrier, seq_frac)
    pos = np.arange(len(cores))

    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
    fig.suptitle(title, fontsize=12)

    for ax, df_plot, label, pal in [
        (axes[0], df_filtered, "Avec filtre MAD",  "Blues"),
        (axes[1], df_raw,      "Sans filtre MAD",  "Oranges"),
    ]:
        sns.boxplot(data=df_plot, x="N_core", y="greenup", palette=pal, ax=ax)
        ax.plot(pos, est_fit, 'C1-', lw=2, label=f"modèle ($S_{{e,\\mathrm{{fit}}}}$={ratio_fit:.2f})")
        ax.plot(pos, cores,   'k-.', lw=1, label="speedup théorique")
        ax.set_xlabel("Nombre de cœurs")
        ax.set_ylabel("Greenup")
        ax.set_title(label)
        ax.legend(fontsize=8)

    plt.tight_layout()
    signaturebar(fig, file_path)
    plt.savefig(os.path.join(output_dir, "greenup_mad_comparison.png"), dpi=300, bbox_inches='tight')
    plt.close()


def plot_error_boxplot(df, ratio_fit, output_dir, title, file_path):
    df = df.copy()
    df["greenup_pred"] = greenup_model(
        df["N_core"], ratio_fit, df["Barrier"], df["Seq_frac"])
    df["error_pct"] = (df["greenup"] - df["greenup_pred"]) / df["greenup_pred"] * 100

    fig, ax = plt.subplots(figsize=(8, 5))
    sns.boxplot(data=df, x="N_core", y="error_pct", palette="Reds", ax=ax)
    ax.axhline(y=0, color="k", linestyle="--", linewidth=0.8)
    ax.set_xlabel("Degré de parallélisation (nombre de cœurs)")
    ax.set_ylabel("Erreur relative (%)")
    ax.set_title(f"Erreur du greenup prédit — {title}")
    plt.tight_layout()
    signaturebar(fig, file_path)
    plt.savefig(os.path.join(output_dir, "greenup_error_boxplot.png"),
                dpi=300, bbox_inches='tight')
    plt.close()


def plot_distribution(values, mu, output_dir, file_path):
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.hist(values, bins=20, color='tab:blue', alpha=0.6, label=f'médiane: {np.median(values):.2f}')
    ax.axvline(x=mu, color='red')
    ax.set_xlim([0, max(values) + 2])
    ax.set_xlabel("Valeurs de $S_e$")
    ax.set_ylabel("Count")
    ax.legend()
    plt.tight_layout()
    signaturebar(fig, file_path)
    plt.savefig(os.path.join(output_dir, "distribution_Se.png"), dpi=300, bbox_inches='tight')
    plt.close()


def plot_edp(df, output_dir, file_path):
    df = df.copy()
    df["EDP"] = df["Energy"] * df["Time"]
    edp_ref = df[df["N_core"] == 1]["EDP"].median()
    df["EDP_norm"] = df["EDP"] / edp_ref

    fig, axes = plt.subplots(1, 2, figsize=(14, 4))

    sns.boxplot(data=df, x="N_core", y="EDP", palette="Purples", ax=axes[0])
    axes[0].set_xlabel("Nombre de cœurs")
    axes[0].set_ylabel("EDP (J·s)")
    axes[0].set_title("Energy-Delay Product par cœur")

    sns.boxplot(data=df, x="N_core", y="EDP_norm", palette="Purples", ax=axes[1])
    axes[1].axhline(y=1.0, color='k', linestyle='--', linewidth=0.8)
    axes[1].set_xlabel("Nombre de cœurs")
    axes[1].set_ylabel("EDP normalisé (ref = 1 cœur)")
    axes[1].set_title("EDP normalisé par cœur")

    plt.tight_layout()
    signaturebar(fig, file_path)
    plt.savefig(os.path.join(output_dir, "edp.png"), dpi=300, bbox_inches='tight')
    plt.close()


def create_comprehensive_plot(df_gre, cores, ratio_fit, se_values, mu, sigma,
                              output_dir, file_path, seq_frac, barrier):
    df_gre = df_gre.copy()
    df_gre["EDP"] = df_gre["Energy"] * df_gre["Time"]
    edp_ref = df_gre[df_gre["N_core"] == 1]["EDP"].median()
    df_gre["EDP_norm"] = df_gre["EDP"] / edp_ref

    fig, axes = plt.subplots(3, 2, figsize=(14, 11))
    fig.suptitle(f'Analyse complète  seq={seq_frac:.2f}  barriers={barrier}', fontsize=16)

    # [0,0] Se distribution
    ax = axes[0, 0]
    ax.hist(se_values, bins=20, color='tab:blue', alpha=0.6,
            label=f'médiane: {np.median(se_values):.2f}')
    ax.axvline(x=mu, color='red')
    ax.set_xlim([0, max(se_values) + 2])
    ax.set_xlabel("Valeurs de $S_e$")
    ax.set_ylabel("Count")
    ax.legend()
    ax.set_title("Distribution de $S_e$")

    ratio_meas = np.median(se_values)

    # [0,1] Greenup distribution vs predicted
    ax = axes[0, 1]
    pos = np.arange(len(cores))
    est = greenup_model(cores, ratio_meas, barrier, seq_frac)
    sns.boxplot(data=df_gre, x='N_core', y='greenup', palette='Blues', ax=ax)
    ax.plot(pos, est, 'C1-', lw=2, label=f'modèle ($S_e$={ratio_meas:.4f})')
    ax.plot(pos, cores, 'k-.', lw=1, label='speedup théorique')
    ax.set_ylim(0, cores.max() + 1)
    ax.set_xlabel("Nombre de cœurs")
    ax.set_ylabel("Greenup / Speedup")
    ax.legend()
    ax.set_title("Greenup prédit vs mesuré")

    # [1,0] Greenup error %
    df_err = df_gre.copy()
    df_err["greenup_pred"] = greenup_model(
        df_err["N_core"], ratio_meas, df_err["Barrier"], df_err["Seq_frac"])
    df_err["error_pct"] = (df_err["greenup"] - df_err["greenup_pred"]) / df_err["greenup_pred"] * 100
    ax = axes[1, 0]
    sns.boxplot(data=df_err, x='N_core', y='error_pct', palette='Reds', ax=ax)
    ax.axhline(y=0, color='k', linestyle='--', linewidth=0.8)
    ax.set_xlabel("Nombre de cœurs")
    ax.set_ylabel("Erreur relative (%)")
    ax.set_title("Erreur de greenup (%)")

    # [1,1] Energy
    ax = axes[1, 1]
    sns.boxplot(data=df_gre, x='N_core', y='Energy', palette='Greens', ax=ax)
    ax.set_xlabel("Nombre de cœurs")
    ax.set_ylabel("Énergie (J)")
    ax.set_title("Consommation énergétique par cœur")

    # [2,0] Se ratio boxplot
    ax = axes[2, 0]
    sns.boxplot(data=df_gre, x='N_core', y='ratio', palette='Blues', ax=ax)
    ax.set_xlabel("Nombre de cœurs")
    ax.set_ylabel("Valeurs de $S_e$")
    ax.set_title("Distribution de $S_e$ par cœur")

    # [2,1] Temperature
    ax = axes[2, 1]
    sns.boxplot(data=df_gre, x='N_core', y='Temperature', palette='Oranges', ax=ax)
    ax.set_xlabel("Nombre de cœurs")
    ax.set_ylabel("Température (°C)")
    ax.set_title("Température par cœur")

    plt.tight_layout()
    signaturebar(fig, file_path)
    out_path = os.path.join(output_dir, "comprehensive.png")
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    # plt.show()
    plt.close()
    print(f"  comprehensive → {out_path}")


# ── main entry points ──────────────────────────────────────────────────────────

def create_plots(file_path, name, show=False, use_mad_filter=False, use_temp_filter=False, output_base=None):
    abs_path = os.path.abspath(file_path)
    if output_base is None:
        output_base = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "images")

    # always keep a raw (unfiltered) copy for MAD comparison
    df_raw = load_csv(file_path)
    if use_temp_filter:
        df_raw = df_raw[df_raw['Temperature'].between(20, 100)]
    df_raw_gre = compute_greenup(df_raw)

    df = load_csv(file_path)
    if use_mad_filter:
        df = mad_filter_df(df)
    if use_temp_filter:
        df = df[df['Temperature'].between(20, 100)]

    df_gre = compute_greenup(df)
    df_gre["ratio"] = ratio_model(
        df_gre["greenup"], df_gre["N_core"], df_gre["Barrier"], df_gre["Seq_frac"])

    groups = list(df_gre.groupby(["Seq_frac", "Barrier"]))
    print(f"Found {len(groups)} parameter combination(s):")
    for (seq_frac, barrier), _ in groups:
        print(f"  seq_fraction={seq_frac:.2f}, nbarriers={barrier}")

    if show:
        return

    for (seq_frac, barrier), group in groups:
        folder = f"seq{seq_frac:.2f}_barriers{barrier}"
        output_dir = os.path.join(output_base, name, folder)
        os.makedirs(output_dir, exist_ok=True)

        cores = np.sort(group["N_core"].unique())
        ratio_fit, rmse_pct = regress_ratio(group)
        ratio_old = group["ratio"].mean()

        se_values, mu, sigma, q1, q3 = analyze_distribution(
            group["ratio"].replace([np.inf, -np.inf], np.nan).dropna().tolist())
        se_med = float(np.median(se_values))

        print(f"\n[{folder}]  Se_fit={ratio_fit:.6f}  RMSE={rmse_pct:.2f}%  "
              f"Se={se_med:.6f}  Se_mean={ratio_old:.6f}")

        display_title = name.replace('_', ' ')

        raw_group = df_raw_gre[
            (df_raw_gre["Seq_frac"] == seq_frac) &
            (df_raw_gre["Barrier"] == barrier)
        ].copy()

        create_comprehensive_plot(group, cores, ratio_fit, se_values, mu, sigma,
                                  output_dir, abs_path, seq_frac, barrier)
        plot_g_comp(cores, group, ratio_fit, display_title, output_dir, abs_path)
        plot_g_comp_mad_comparison(cores, group, raw_group, ratio_fit,
                                   display_title, output_dir, abs_path)
        plot_error_boxplot(group, ratio_fit, output_dir, display_title, abs_path)
        plot_distribution(se_values, mu, output_dir, abs_path)

        plot_edp(group, output_dir, abs_path)

        for col in ["Energy", "Temperature", "Voltage", "Time"]:
            plot_specific(group, col, output_dir, abs_path)

        print(f"  → {output_dir}")

    print(f"\nAll figures saved under {output_base}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Energy analysis plots for embarrassingly parallel benchmarks')
    parser.add_argument('file', type=str,
                        help='CSV file or directory containing CSV files')
    parser.add_argument('--name', type=str, default="",
                        help='Output subdirectory prefix')
    parser.add_argument('--show', action='store_true',
                        help='Show plots instead of saving')
    parser.add_argument('--no-mad-filter', action='store_true',
                        help='Disable MAD filtering on energy data')
    parser.add_argument('--temp-filter', action='store_true',
                        help='Enable temperature filtering (20–100 °C)')
    parser.add_argument('--output', type=str, default=None,
                        help='Base output directory (default: embarassingly/images/)')

    args = parser.parse_args()
    create_plots(args.file, args.name, show=args.show,
                 use_mad_filter=not args.no_mad_filter,
                 use_temp_filter=args.temp_filter,
                 output_base=args.output)
