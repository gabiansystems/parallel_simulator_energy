#!/bin/bash
#OAR -n parasilo_ep
#OAR -l nodes=1,walltime=2:00:00
#OAR -O /home/asolcour/public/parallel_simulator_energy/logs/oar_%jobid%.out
#OAR -E /home/asolcour/public/parallel_simulator_energy/logs/oar_%jobid%.err

# Test ep — sweep n_cores [1..8], s=0, uncore verrouillé — parasilo (HSW)
#
# Objectif : mesurer E(n_c) pour estimer Se via le modèle SEAM.
#
# Soumission depuis le frontend G5K :
#   oarsub -p "cluster='parasilo'" launch_scripts/parasilo_ep.sh

set -e
cd /home/asolcour/public/parallel_simulator_energy

NODE=$(hostname -s)
mkdir -p logs resultats
echo "[$(date)] Node: $NODE"

sudo-g5k modprobe msr 2>/dev/null || echo "[warn] modprobe msr failed"

echo "[build] compiling..."
make -B 2>&1

echo "[run] starting sweep — $(date)"
sudo-g5k ./counter -i params/parasilo_ep.json -o resultats/${NODE}_ep

echo "[done] $(date)"
echo "Results: resultats/${NODE}_ep.{json,csv}"
