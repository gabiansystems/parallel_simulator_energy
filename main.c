#define _GNU_SOURCE
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include "energy_tool/counter.h"
#include "utils/json_utils.h"
#include "benchmarks/parallel_sim.h"

static void usage(const char *prog)
{
    fprintf(stderr,
            "Usage: %s -i params/parallel_sim_uncore.json -o resultats/run1\n"
            "  -i  JSON config file (see params/)\n"
            "  -o  output base path (produces <path>.json and <path>.csv)\n",
            prog);
}

int main(int argc, char **argv)
{
    const char *input_cfg   = "params/parallel_sim_uncore.json";
    const char *output_base = "resultats/sim1";
    int opt;

    while ((opt = getopt(argc, argv, "i:o:h")) != -1) {
        switch (opt) {
        case 'i': input_cfg   = optarg; break;
        case 'o': output_base = optarg; break;
        case 'h': usage(argv[0]); return 0;
        default:  usage(argv[0]); return 1;
        }
    }

    params_t p;
    memset(&p, 0, sizeof(p));
    if (read_params_from_json(input_cfg, &p) != 0) {
        fprintf(stderr, "Error: cannot read config from %s\n", input_cfg);
        return EXIT_FAILURE;
    }

    printf("=== parallel_simulator_energy ===\n");
    printf("arch=%d  sensor=%d  freq=%.2f GHz  n_work=%d  n_stat=%d  "
           "n_cores=%d  seq_frac=%.1f%%  vendor=%s\n",
           p.arch, p.sensor, p.freq, p.total_operations, p.n_stat,
           p.n_cores, p.seq_fraction, p.vendor);

    int n_cores_count = p.n_cores;
    int *n_cores_array = malloc(sizeof(int) * n_cores_count);
    if (!n_cores_array) { perror("malloc"); return EXIT_FAILURE; }
    for (int i = 0; i < n_cores_count; ++i)
        n_cores_array[i] = i + 1;

    float seq_fraction_array[1] = { p.seq_fraction };

    if (create_output_files(output_base, &p,
                            n_cores_array, n_cores_count,
                            seq_fraction_array, 1) != 0) {
        fprintf(stderr, "Error: cannot create output files at %s\n", output_base);
        free(n_cores_array);
        return EXIT_FAILURE;
    }

    /* Always lock both core and uncore frequencies — the purpose of this repo
     * is to measure energy under fixed uncore frequency to isolate its effect. */
    set_fixed_frequency(p.freq, p.vendor);

    /* Sweep from n_cores down to 1: hottest run first for a stable thermal baseline. */
    for (int nthreads = n_cores_count; nthreads > 0; nthreads--) {
        parallel_sim_params_t sim = {
            .nthreads               = nthreads,
            .nbarriers              = 1,
            .seq_fraction           = p.seq_fraction,
            .total_units_per_barrier = (uint64_t)p.total_operations,
            .tpc                    = 0, /* auto-detect from sysfs */
        };
        char *exp_name = build_name(&sim);
        if (!exp_name) continue;

        printf("[%2d cores] measuring %d samples...\n", nthreads, p.n_stat);

        measure_config_t cfg = {
            .output_file = output_base,
            .exp_name    = exp_name,
            .vendor      = p.vendor,
            .arch        = p.arch,
            .sensor      = p.sensor,
            .n_samples   = p.n_stat,
            .n_cores     = nthreads,
            .seq_frac    = p.seq_fraction,
            .nbarriers   = 1,
        };

        if (measure_energy_temperature(exec_parallel_simulation_core_control,
                                       &sim, &cfg) != 0)
            fprintf(stderr, "[WARN] measurement failed for nthreads=%d\n", nthreads);

        free(exp_name);
    }

    printf("=== Done. Results in %s.{json,csv} ===\n", output_base);
    free(n_cores_array);
    return 0;
}
