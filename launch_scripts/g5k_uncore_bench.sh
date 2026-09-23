#!/bin/bash
# Run the uncore-locked parallel simulation sweep on a G5K node.
#
# Usage (from the project root on the G5K node):
#   sudo-g5k bash launch_scripts/g5k_uncore_bench.sh [N_RUNS]
#
# Each run produces resultats/uncore_<i>.{json,csv}.
# N_RUNS defaults to 10 for statistical replication at the job level.
#
# This script:
#   1. Installs build dependencies if missing.
#   2. Loads the MSR kernel module (needed for uncore MSR writes).
#   3. Builds the binary.
#   4. Runs N_RUNS sweeps, one output file per run.

set -e

N_RUNS="${1:-10}"
PARAMS="params/parallel_sim_uncore.json"

# ---- dependencies -----------------------------------------------------------
modprobe msr 2>/dev/null || echo "[warn] modprobe msr failed — temp/uncore MSR may be unavailable"

# ---- build ------------------------------------------------------------------
echo "[build] make -B..."
make -B 2>&1

# ---- detect node name and arch (for output labelling) -----------------------
NODE=$(hostname -s)
MODEL=$(grep -m1 "model name" /proc/cpuinfo | cut -d: -f2 | sed 's/^ *//')
echo "[node] $NODE  CPU: $MODEL"

mkdir -p resultats

# ---- sweep ------------------------------------------------------------------
for i in $(seq 1 "$N_RUNS"); do
    OUT="resultats/uncore_${i}"
    echo "[run $i/$N_RUNS] → $OUT"
    sudo-g5k ./counter -i "$PARAMS" -o "$OUT"
done

echo ""
echo "[done] $N_RUNS runs complete on $NODE"
echo "       Results: resultats/uncore_*.{json,csv}"
