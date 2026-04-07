
hostname="host in ('parasilo-$1.rennes.grid5000.fr')"
command="/home/asolcour/public/parallel_simulator_energy/run_off.sh"

logfile="job_$(date +%Y%m%d_%H%M%S).log"

oarsub \
  -l "{${hostname}}/host=1,walltime=3" \
  -O "$logfile" \
  -E "$logfile" \
  "$command"