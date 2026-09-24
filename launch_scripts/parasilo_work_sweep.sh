#!/bin/bash
#OAR -n parasilo_work_sweep
#OAR -l nodes=1,walltime=3:00:00
#OAR -O /home/asolcour/public/parallel_simulator_energy/logs/oar_%jobid%.out
#OAR -E /home/asolcour/public/parallel_simulator_energy/logs/oar_%jobid%.err

# Test work_sweep — sensibilité de Se à la taille de charge n_work — parasilo (HSW)
#
# Principe : relance le test ep pour 5 tailles de charge (500K à 1G unités de travail).
# Les résultats permettent de valider que Se est indépendant de n_work
# au-delà d'un seuil (voir docs/postprocess/work_sweep.py).
#
# Soumission depuis le frontend G5K :
#   oarsub -p "cluster='parasilo'" launch_scripts/parasilo_work_sweep.sh

set -e
cd /home/asolcour/public/parallel_simulator_energy

NODE=$(hostname -s)
mkdir -p logs resultats
echo "[$(date)] Node: $NODE"

sudo-g5k modprobe msr 2>/dev/null || echo "[warn] modprobe msr failed"

echo "[build] compiling..."
make -B 2>&1

# Sweep sur n_work : modifie temporairement le param via sed
for NW in 500000 1000000 10000000 100000000 1000000000; do
    LABEL=$(echo $NW | sed 's/000000000/1G/;s/00000000/100M/;s/0000000/10M/;s/000000/1M/;s/00000/500K/')
    PARAM_TMP="/tmp/work_sweep_${LABEL}.json"
    sed "s/\"n_work\": [0-9]*/\"n_work\": $NW/" params/parasilo_work_sweep.json > "$PARAM_TMP"
    echo "[run] n_work=$LABEL — $(date)"
    sudo-g5k ./counter -i "$PARAM_TMP" -o "resultats/${NODE}_work_sweep_nw${LABEL}"
done

echo "[done] $(date)"
echo "Results: resultats/${NODE}_work_sweep_nw*.{json,csv}"
