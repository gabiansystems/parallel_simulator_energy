import os
import json
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from scipy.stats import norm, shapiro, chi2_contingency
import statistics
import numpy as np
from pathlib import Path
import argparse  # Add this at the top with other imports
import warnings
import logging

# Suppress warnings and logs
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
logging.getLogger('matplotlib').setLevel(logging.ERROR)
logging.getLogger('seaborn').setLevel(logging.ERROR)
logging.getLogger('PIL').setLevel(logging.ERROR)


def med(ma_liste):
    """Calculate median of a list."""
    return statistics.median(ma_liste)


def mad_filter(values, k=3.0):
    """
    Robust MAD filtering.
    Removes points farther than k robust sigmas from median.
    """
    values = np.array(values)
    median = np.median(values)
    mad = np.median(np.abs(values - median))

    if mad == 0:
        return values.tolist()

    robust_sigma = 1.4826 * mad
    threshold = k * robust_sigma

    mask = np.abs(values - median) <= threshold
    return values[mask].tolist()


def iqr_filter(values, k=1.5):
    """
    IQR filtering.
    Keeps values inside [Q1 - k*IQR, Q3 + k*IQR]
    """
    values = np.array(values)

    q1 = np.percentile(values, 25)
    q3 = np.percentile(values, 75)
    iqr = q3 - q1

    lower = q1 - k * iqr
    upper = q3 + k * iqr

    mask = (values >= lower) & (values <= upper)
    return values[mask].tolist()


def load_clean(file, k=1.0):
    """
    Load energy data and clean each core series using MAD filtering.
    Returns core_ener dictionary mapping core numbers to cleaned energy arrays.
    """
    conc = {"energy":{},"temperature":{}}
    import os
    files = [file+f for f in os.listdir(file) if os.path.splitext(f)[1]=='.json']
    for filee in files:
        with open(filee, "r") as f:
            data = json.load(f)
        for i,v in data['energy'].items():
            if i in conc["energy"]:
                conc["energy"][i].extend(v)
            else:
                conc["energy"][i]=v

        for i,v in data['temperature'].items():
            if i in conc['temperature']:
                conc["temperature"][i].extend(v)
            else:
                conc["temperature"][i]=v
    data = conc
    print("nombre de points: ",len(data['energy']["8_0.00_1_1000000000"]))
    core_ener = {}
    cores = []

    for it, val in data["energy"].items():
        cleaned = mad_filter(val, k=k)
        core = int(it.split("_")[0])
        cores.append(core)
        core_ener[core] = cleaned

    return core_ener, cores, data


def evaluate_greenup(r, n):
    """Calculate theoretical greenup value."""
    return (1 + r) / (1 + r / n)


def prepare_energy_data(core_ener):
    """Prepare energy data for visualization."""
    energy_box = []

    for i, v in core_ener.items():
        core = int(i)
        for ee in v:
            energy_box.append({
                "energy": ee,
                "core": core
            })
        # f, m, s, q, qq, b, m = analyze_distribution(v)
        # plot_distribution(f, m, s, "distrib_"+str(core), True)
    return pd.DataFrame(energy_box)

    # for i, (core, energy_values) in enumerate(core_ener.items(), 1):
    #     for ee in energy_values:
    #         energy_box.append({
    #             "energy": ee,
    #             "core": i
    #         })
    # return pd.DataFrame(energy_box)


def calculate_greenup_values(core_ener, ref_energy, cores):
    """Calculate greenup values from energy measurements."""
    greenup_by_core = []
    greenup_proc = []
    median_greenup = []

    for core in sorted(cores):
        v = core_ener[core]
        tmp_g = []
        for ee in v:
            g_val = ref_energy / ee
            tmp_g.append(g_val)
            greenup_proc.append({
                "greenup": g_val,
                "core": core
            })
        median_greenup.append(med(tmp_g))
        greenup_by_core.append(tmp_g)

    return greenup_by_core, greenup_proc, median_greenup

    # for i, (core, energy_values) in enumerate(core_ener.items(), 1):
    #     tmp_g = []
    #     for ee in energy_values:
    #         g_val = ref_energy / ee
    #         tmp_g.append(g_val)
    #         greenup_proc.append({
    #             "greenup": g_val,
    #             "core": i
    #         })
    #     median_greenup.append(med(tmp_g))
    #     greenup_by_core.append(tmp_g)

    # return greenup_by_core, greenup_proc, median_greenup


def calculate_ratios(greenup_by_core):
    """Calculate ratio values between consecutive core counts."""
    ratio_data = []
    for i in range(len(greenup_by_core) - 1):
        g_n = med(greenup_by_core[i])
        n = i + 1
        for g_n_1 in greenup_by_core[i + 1]:
            rat_up = g_n_1 - g_n
            rat_lo = g_n / n - g_n_1 / (n + 1)
            rat_complete = rat_up / rat_lo
            ratio_data.append({
                "ratio": rat_complete,
                "core_number": n
            })
    return ratio_data


def analyze_distribution(data):
    """Perform statistical analysis on data distribution."""
    flat_data = [x for sub in data for x in sub] if isinstance(
        data[0], list) else data
    flat_data = mad_filter(flat_data, 5)

    q1 = np.percentile(flat_data, 25)
    q3 = np.percentile(flat_data, 75)
    mu, sigma = norm.fit(flat_data)

    print(f"mu: {mu}")
    print(f"med: {med(flat_data)}")

    # Shapiro-Wilk test
    shapiro_stat, shapiro_p = shapiro(flat_data)
    print(
        f"Shapiro-Wilk test statistic: {shapiro_stat:.4f}, p-value: {shapiro_p:.4e}")
    print("Données suivent une normale" if shapiro_p >
          0.05 else "Données ne suivent PAS une normale")

    # Chi-square test
    counts, bins = np.histogram(flat_data, bins=20)
    max_bin_idx = np.argmax(counts)
    most_values_range = (bins[max_bin_idx], bins[max_bin_idx + 1])
    print(
        f"Range avec le plus de valeurs : {most_values_range[0]:.2f} <-> {most_values_range[1]:.2f} (count: {counts[max_bin_idx]})")

    expected_counts = norm.pdf((bins[1:] + bins[:-1])/2, mu, sigma)
    expected_counts = expected_counts / expected_counts.sum() * counts.sum()
    chi2_stat, chi2_p = chi2_contingency([counts, expected_counts])[:2]
    print(f"Chi2 test statistic: {chi2_stat:.4f}, p-value: {chi2_p:.4e}")
    if chi2_p > 0.05:
        print("Selon le test du chi2, la distribution observée ne diffère pas significativement de la normale.")
    else:
        print("Selon le test du chi2, la distribution observée DIFFÈRE de la normale.")

    return flat_data, mu, sigma, q1, q3, bins, max_bin_idx


def calculate_error_metrics(df, mu):
    """Calculate error metrics between measured and predicted greenup."""
    df["greenup_pred"] = df["core"].apply(
        lambda n: evaluate_greenup(mu, int(n)))
    df["greenup_error"] = df["greenup"] - df["greenup_pred"]
    df["greenup_error_abs_pct"] = (
        df["greenup_error"].abs() / df["greenup_pred"].abs()) * 100

    # Remove outliers for percentage range calculation
    q1_pct = df["greenup_error_abs_pct"].quantile(0.25)
    q3_pct = df["greenup_error_abs_pct"].quantile(0.75)
    iqr_pct = q3_pct - q1_pct
    lower_bound_pct = q1_pct - 1.5 * iqr_pct
    upper_bound_pct = q3_pct + 1.5 * iqr_pct

    df_no_outliers_pct = df[(df["greenup_error_abs_pct"] >= lower_bound_pct) &
                            (df["greenup_error_abs_pct"] <= upper_bound_pct)]

    error_abs_pct_min = df_no_outliers_pct["greenup_error_abs_pct"].min()
    error_abs_pct_max = df_no_outliers_pct["greenup_error_abs_pct"].max()
    print(
        f"Greenup absolute error percentage range (without outliers): {error_abs_pct_min:.2f}% to {error_abs_pct_max:.2f}%")

    return df


def plot_distribution(flat_data, mu, sigma, name, show, output_dir="./images"):
    """Plot distribution of ratio values."""
    aspect_ratio = 0.3
    fig_width = 10
    fig_height = fig_width * aspect_ratio

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    ax.hist(flat_data, bins=20, color='tab:blue', alpha=0.6)
    ax.set_xlabel("valeurs de r_n")
    ax.set_ylabel("Count", color='tab:blue')
    ax.set_xlim([0, 9])

    if show:
        plt.show()
    else:
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(
            output_dir, f'{name}/'+"distribution_rn_HLratio.png")
        plt.tight_layout()
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        print(f"Figure saved to {filepath}")
        plt.close()


def plot_ratio_boxplot(ratio_df, name, output_dir="./images"):
    """Plot boxplot of ratios by core number."""
    plt.figure(figsize=(8, 5))
    sns.boxplot(data=ratio_df, x="core_number", y="ratio", palette="Blues")
    plt.tight_layout()
    plt.savefig(os.path.join(
        output_dir, f'{name}/'+"distribution_rn_violinplot.png"), dpi=300, bbox_inches='tight')
    plt.close()


def plot_energy_boxplot(energy_df, name, output_dir="./images"):
    """Plot boxplot of energy by core."""
    plt.figure(figsize=(8, 5))
    sns.boxplot(data=energy_df, x="core", y="energy", palette="Blues")
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'{name}/'+"energy_boxplot.png"),
                dpi=300, bbox_inches='tight')
    plt.close()


def plot_greenup_comparison(greenup_proc, median_greenup, cores, mu, q1, q3, name, output_dir="./images"):
    """Plot greenup comparison between measured and theoretical values."""
    fig, ax = plt.subplots(figsize=(8, 5))
    df = pd.DataFrame(greenup_proc)

    greenup_th_mu = [evaluate_greenup(mu, int(n)) for n in cores]
    greenup_th_q1 = [evaluate_greenup(q1, int(n)) for n in cores]
    greenup_th_q3 = [evaluate_greenup(q3, int(n)) for n in cores]

    ax.plot(cores, greenup_th_mu, label="Greenup modèle",
            color="C1", linewidth=2)
    ax.plot(cores, median_greenup, "o",
            label="Médiane du greenup mesuré", color="C0", linewidth=2)

    ax.set_ylim([0, 8])
    ax.set_ylabel("Greenup, Speedup")
    ax.plot(cores, [int(c) for c in cores], "k-.",
            linewidth=2, label="Speedup théorique")
    ax.set_xlabel("Degré de parallélisation (nombre de coeurs impliqués)")
    ax.legend()

    yticks = list(ax.get_yticks()) + [mu+1]
    ax.set_yticks([y for y in yticks])
    plt.axhline(y=mu+1, linestyle=':')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'{name}/'+"greenup_boxplot.png"),
                dpi=300, bbox_inches='tight')
    plt.close()


def plot_error_boxplot(df, name, output_dir="./images"):
    """Plot boxplot of greenup errors."""
    fig_err, ax_err = plt.subplots(figsize=(8, 5))
    sns.boxplot(data=df, x="core", y="greenup_error",
                palette="Reds", ax=ax_err)
    ax_err.set_ylabel("Erreur Greenup (mesuré - prédit)")
    ax_err.set_xlabel("Degré de parallélisation (nombre de coeurs impliqués)")
    ax_err.set_title("Distribution de l'erreur entre greenup mesuré et prédit")
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'{name}/'+"greenup_error_boxplot.png"),
                dpi=300, bbox_inches='tight')
    plt.close()


def proc_temperature(data):
    temperature = []
    for i, v in data['temperature'].items():
        core = int(i.split("_")[0])
        for ee in v:
            temperature.append({
                "temperature": ee,
                "core": core
            })
    return pd.DataFrame(temperature)

def plot_temperature(temperature,name,output_dir):
    df = pd.DataFrame(temperature)
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.boxplot(data=df, x="core", y="temperature",
            palette="Reds", ax=ax)
    ax.set_ylabel("Temperature")
    ax.set_xlabel("Degré de parallélisation (nombre de coeurs impliqués)")
    ax.set_title("La temperature")
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'{name}/'+"temperature"),
                dpi=300, bbox_inches='tight')
    plt.close()

def create_comprehensive_plot(flat_data, mu, sigma, cores, median_greenup, 
                              greenup_proc, greenup_error_df, temperature_df, 
                              ratio_df, energy_df, name, output_dir):
    """
    Create a multi-panel figure showing:
    - Distribution of r_n (top-left)
    - Greenup prediction vs measurement (top-right)
    - Greenup error per core (bottom-left)
    - Temperature per core (bottom-right)
    """
    fig, axes = plt.subplots(3, 2, figsize=(14, 10))
    fig.suptitle(f'Analyse complète – {name}', fontsize=16)

    # ---------- Top-left: Distribution of r_n ----------
    ax = axes[0, 0]
    ax.hist(flat_data, bins=20, color='tab:blue', alpha=0.6, density=True)
    x = np.linspace(min(flat_data), max(flat_data), 200)
    pdf = norm.pdf(x, mu, sigma)
    ax.plot(x, pdf, 'r-', lw=2, label=f'N({mu:.2f}, {sigma:.2f})')
    ax.set_xlabel('Valeurs de $r_n$')
    ax.set_ylabel('Densité')
    ax.legend()
    ax.set_title('Distribution de $r_n$')

    # ---------- Top-right: Greenup prediction vs measured ----------
    ax = axes[0, 1]
    greenup_th_mu = [evaluate_greenup(mu, int(n)) for n in cores]
    # Median greenup per core (from greenup_proc)
    med_greenup = [med([d['greenup'] for d in greenup_proc if d['core'] == int(c)]) for c in cores]
    ax.plot(cores, greenup_th_mu, 'C1-', lw=2, label='Greenup modèle')
    ax.plot(cores, med_greenup, 'C0o', label='Médiane mesurée')
    ax.plot(cores, [int(c) for c in cores], 'k-.', lw=2, label='Speedup théorique')
    ax.set_xlabel('Nombre de cœurs')
    ax.set_ylabel('Greenup / Speedup')
    ax.set_ylim(0, 8)
    ax.legend()
    ax.set_title('Greenup prédit vs mesuré')

    # ---------- Bottom-left: Greenup error boxplot ----------
    ax = axes[1, 1]
    sns.boxplot(data=greenup_error_df, x='core', y='greenup_error', 
                palette='Reds', ax=ax)
    ax.set_xlabel('Nombre de cœurs')
    ax.set_ylabel('Erreur (mesuré - prédit)')
    ax.set_title('Erreur de greenup')

    # ---------- Bottom-right: Temperature boxplot ----------
    ax = axes[1, 0]
    sns.boxplot(data=temperature_df, x='core', y='temperature', 
                palette='Oranges', ax=ax)
    ax.set_xlabel('Nombre de cœurs')
    ax.set_ylabel('Température')
    ax.set_title('Température par cœur')

    ax = axes[2, 0]
    sns.boxplot(data=ratio_df, x='core_number', y='ratio', 
            palette='Blues', ax=ax)
    ax.set_xlabel('degre de parallelisation')
    ax.set_ylabel('Valeurs de $r_n$')
    ax.set_title('Distribution de $r_n$')
    
    ax = axes[2, 1]
    sns.boxplot(data=energy_df, x='core', y='energy', 
            palette='Blues', ax=ax)
    ax.set_xlabel('degre de parallelisation')
    ax.set_ylabel('consommation d energie')
    ax.set_title('Consommation d energie en fonction du degre de parallelisation')

    plt.tight_layout()
    out_path = os.path.join(output_dir, f'comprehensive_{name}.png')
    plt.savefig(out_path, dpi=300, bbox_inches='tight')

    plt.show()
    plt.close()
    print(f"Figure complète sauvegardée : {out_path}")

def create_plots(file_path, name, show=False):
    """Main function to create all plots."""
    # Load data using core_ener dictionary
    core_ener, cores, data = load_clean(file_path)

    # return 0

    # Get reference energy from first core
    ref = med(core_ener[1])

    # Prepare data for analysis
    energy_df = prepare_energy_data(core_ener)
    greenup_by_core, greenup_proc, median_greenup = calculate_greenup_values(
        core_ener, ref, cores)

    # Calculate ratios and analyze distribution
    ratio_data = calculate_ratios(greenup_by_core)
    ratio_df = pd.DataFrame(ratio_data)
    flat_data, mu, sigma, q1, q3, bins, max_bin_idx = analyze_distribution(
        [d["ratio"] for d in ratio_data])

    if show:
        return 0

    # Create directory if it doesn't exist
    Path(f'./images/{name}').mkdir(parents=True, exist_ok=True)

    # Calculate error metrics
    greenup_df = pd.DataFrame(greenup_proc)
    greenup_error_df = calculate_error_metrics(greenup_df, mu)

    # Temperature
    temperature_df = proc_temperature(data)

    # Create all plots
    output_dir = "./images"
    os.makedirs(output_dir, exist_ok=True)

    create_comprehensive_plot(flat_data, mu, sigma, cores,median_greenup,greenup_proc,greenup_error_df,temperature_df,ratio_df,energy_df,name,output_dir)

    plot_temperature(temperature_df,name,output_dir)
    plot_distribution(flat_data, mu, sigma, name, show, output_dir)
    plot_ratio_boxplot(ratio_df, name, output_dir)
    plot_energy_boxplot(energy_df, name, output_dir)
    plot_greenup_comparison(greenup_proc, median_greenup,
                            sorted(cores), mu, q1, q3, name, output_dir)
    plot_error_boxplot(greenup_df, name, output_dir)

    print(f"All figures saved to {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Generate energy analysis plots')
    parser.add_argument('file', type=str, help='Path to the JSON file')
    parser.add_argument('--show', action='store_true',
                        help='Show plots instead of saving')

    args = parser.parse_args()

    name = "on"
    # name = "_".join(os.path.splitext(args.file)[0].split("_")[-2:])
    print(name)

    # Update create_plots to accept name parameter
    create_plots(args.file, name, show=args.show)
