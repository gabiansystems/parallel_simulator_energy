# parallel\_simulator\_energy

Mesure de la consommation énergétique d'un benchmark synthétique parallèle
sous **fréquence uncore fixée** via l'interface RAPL perf\_event de Linux.

Ce dépôt est un **banc d'essai pour l'effet de la fréquence uncore** sur les
mesures d'énergie par RAPL. Contrairement à un benchmark généraliste, le
binaire fixe systématiquement la fréquence uncore (MSR `0x620`) en même temps
que la fréquence cœur — l'objectif est de neutraliser la variabilité introduite
par le scaling uncore dynamique et d'isoler la contribution de l'uncore à
l'énergie mesurée par le domaine PKG.

---

## Structure

```
parallel_simulator_energy/
├── benchmarks/
│   ├── parallel_sim.c   charge synthétique Amdahl, pinning par socket
│   └── parallel_sim.h
├── energy_tool/
│   ├── counter.c        RAPL, MSR, température, fréquence, boucle de mesure
│   └── counter.h
├── launch_scripts/
│   └── g5k_uncore_bench.sh   sweep N runs sur un nœud G5K
├── params/
│   └── parallel_sim_uncore.json   config de référence
├── tests/
│   ├── test_sim.c       tests de logique pure (no root)
│   ├── test_probes.c    tests des sondes matérielles (root)
│   ├── Makefile
│   └── unity/           framework Unity (embarqué)
├── utils/
│   ├── cJSON.{c,h}      parser JSON (embarqué, pas de dépendance système)
│   ├── json_utils.c     sysfs RAPL, I/O JSON + CSV
│   └── json_utils.h
├── main.c
├── Makefile
└── README.md
```

---

## Prérequis

- Linux avec RAPL exposé via perf\_event (`/sys/bus/event_source/devices/power/`)
- Permissions root (ou `sudo-g5k` sur Grid5000) pour perf\_event RAPL et MSR
- Module noyau `msr` chargé : `modprobe msr`
- gcc, pthread, libm — aucune dépendance externe (`cJSON` est embarqué)

---

## Build

```bash
make          # produit ./counter
make test     # tests de logique (no root)
make clean
```

Pour les tests matériels (RAPL + MSR, nécessite root) :

```bash
cd tests && make test_probes
sudo-g5k ./test_probes
```

---

## Utilisation

```bash
sudo-g5k ./counter -i params/parallel_sim_uncore.json -o resultats/run1
```

Produit `resultats/run1.json` et `resultats/run1.csv`.

Le binaire **fixe toujours les deux fréquences** (cœur et uncore) avant de
lancer la mesure. Il n'existe pas de mode « sans uncore fixé » — pour comparer,
utiliser le projet `lecture_energie` (fréquence uncore libre par défaut).

### Options

| Option | Description | Défaut |
|--------|-------------|--------|
| `-i`   | Fichier de config JSON | `params/parallel_sim_uncore.json` |
| `-o`   | Base des fichiers de sortie | `resultats/sim1` |

---

## Format de config

```json
{
  "params": {
    "arch":         "ICX",   ← architecture (sert de fallback si sysfs absent)
    "sensor":       "PKG",   ← domaine RAPL : PKG, PP0, DRAM
    "vendor":       "Intel", ← "Intel" ou "AMD"
    "freq":         2.0,     ← fréquence cœur ET uncore en GHz
    "n_work":       1000000000,  ← unités de travail par barrière
    "n_stat":       30,      ← répétitions par point de mesure
    "n_cores":      8,       ← n_c max ; sweep de n_cores…1
    "seq_fraction": 0.0      ← fraction séquentielle (% de n_work)
  }
}
```

Le type RAPL est lu depuis sysfs (`/sys/bus/event_source/devices/power/type`)
en priorité ; la table de fallback par architecture (`ICX=89`, `CLX=65`, etc.)
n'est utilisée que si le sysfs est inaccessible.

---

## Format de sortie

### CSV — `<output>.csv`

```
Energy_J, Time_s, Temperature_C, Voltage_V, N_cores, Seq_frac, Nbarriers
```

Une ligne par sample. Chaque point de mesure produit `n_stat` lignes.

### JSON — `<output>.json`

```json
{
  "params": { "date": "...", "vendor": "Intel", "arch": 89, ... },
  "energy":      { "8_0.00_1_1000000000": [18.4, 18.6, ...] },
  "time":        { "8_0.00_1_1000000000": [0.84, 0.83, ...] },
  "temperature": { ... },
  "voltage":     { ... }
}
```

Les clés d'expérience suivent le format `<nthreads>_<seq_frac>_<nbarriers>_<n_work>`.

---

## Lancement sur G5K

```bash
# Depuis le frontend, réserver un nœud et se connecter :
oarsub -I -l nodes=1,walltime=1:00:00

# Sur le nœud :
cd /path/to/parallel_simulator_energy
sudo-g5k bash launch_scripts/g5k_uncore_bench.sh 10   # 10 runs
```

---

## Différences avec `lecture_energie`

| | `lecture_energie` | `parallel_simulator_energy` |
|---|---|---|
| Objectif | campagne générale, multi-nœuds | test de l'effet de l'uncore |
| Benchmarks | multi-kernels (Mandelbrot, Monte Carlo, …) | parallel\_sim uniquement |
| Fréquence uncore | libre (non fixée par défaut) | **toujours fixée** |
| Topologie CPU | auto-détectée via hwloc | auto-détectée via sysfs |
| Sorties | CSV + JSON + colonnes PP0/util | CSV + JSON (PKG uniquement) |

---

## Notes

- Le sweep s'effectue de `n_cores` à 1 (du plus chaud au plus froid) pour
  stabiliser la ligne de base thermique entre configurations.
- Un run de chauffe (non mesuré) précède chaque série de `n_stat` mesures
  pour amorcer les caches et le prédicteur de branchements.
- La constante d'échelle RAPL est lue depuis sysfs
  (`energy-pkg.scale`) et non codée en dur.
