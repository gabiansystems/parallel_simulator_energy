sudo-g5k apt-get install -y libcjson-dev
make on
for i in {1..10}; do
  sudo-g5k ./counter_on -i "input_demo.json" -o "./resultats/uncore_on_${i}.json"
done