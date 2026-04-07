sudo-g5k apt-get install -y libcjson-dev
make
for i in {1..10}; do
  sudo-g5k ./counter_off -i "input_demo.json" -o "./resultats/uncore_off_${i}.json"
done