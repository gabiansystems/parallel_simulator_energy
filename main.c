#include "parallel_sim.h"
#include "json_utils.h"
#define _GNU_SOURCE
#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <string.h>
#include <stdint.h>
#include <sys/ioctl.h>
#include <linux/perf_event.h>
#include <asm/unistd.h>
#include <sched.h>
#include <sys/wait.h>
#include <errno.h>
#include <time.h>
#include <fcntl.h>

// Function pointer type for benchmark functions
typedef void (*bench_func_t)(const void *params);

#define VERBOSE 1
#define MSR_IA32_PERF_STATUS 0x198
#define MSR_IA32_THERM_STATUS 0x19C

/**
 * Set the CPU frequency to a fixed value using cpupower.
 * @param freq_ghz The target frequency in GHz
 */
void set_fixed_frequency(double freq_ghz)
{
    char cmd[128];
    printf("=== Setting frequency to %.2f GHz ===\n", freq_ghz);
    snprintf(cmd, sizeof(cmd),
             "sudo-g5k cpupower frequency-set -f %.2fGHz 2>&1 >> /dev/null", freq_ghz);
    system(cmd);
}

long perf_event_open(struct perf_event_attr *hw_event, pid_t pid,
                     int cpu, int group_fd, unsigned long flags)
{
    int ret;

    ret = syscall(__NR_perf_event_open, hw_event, pid, cpu,
                  group_fd, flags);
    return ret;
}
double read_core_voltage(int core)
{
    char msr_path[64];
    snprintf(msr_path, sizeof(msr_path), "/dev/cpu/%d/msr", core);
    int fd = open(msr_path, O_RDONLY);
    if (fd < 0)
    {
        perror("open msr voltage");
        return -1.0;
    }

    uint64_t val;
    if (pread(fd, &val, sizeof(val), MSR_IA32_PERF_STATUS) != sizeof(val))
    {
        perror("pread msr");
        close(fd);
        return -1.0;
    }
    close(fd);

    // Bits [47:32] contain the current VID value *in Intel VID units (1mV steps)*
    unsigned int vid = (val >> 32) & 0xFFFF;
    double voltage = vid * 0.001; // ≈ convert to volts
    return voltage;
}
double read_core_temperature(int core)
{
    char msr_path[64];
    snprintf(msr_path, sizeof(msr_path), "/dev/cpu/%d/msr", core);

    int fd = open(msr_path, O_RDONLY);
    if (fd < 0)
    {
        perror("open msr temperature");
        return -1.0;
    }

    uint64_t val;
    if (pread(fd, &val, sizeof(val), MSR_IA32_THERM_STATUS) != sizeof(val))
    {
        perror("pread msr");
        close(fd);
        return -1.0;
    }
    close(fd);

    // For Haswell, temperature is in bits 22:16 (Reading Valid) and 6:0 (Temperature)
    // Temperature Target is in bits 23:16, Digital Readout in bits 6:0
    unsigned int temp_reading = (val >> 16) & 0x7F; // Bits 22:16 for Reading Valid + Digital readout
    double temperature = (double)temp_reading;      // Temperature in degrees Celsius
    return temperature;
}

/**
 * Get RAPL type based on architecture
 */
int get_rapl_type(const char *arch)
{
    if (strcmp(arch, "SNB") == 0)
        return 27; // Sandy Bridge
    if (strcmp(arch, "IVB") == 0)
        return 29; // Ivy Bridge
    if (strcmp(arch, "HSW") == 0)
        return 34; // Haswell
    if (strcmp(arch, "BDW") == 0)
        return 33; // Broadwell
    if (strcmp(arch, "SKL") == 0)
        return 53; // Skylake
    if (strcmp(arch, "CLX") == 0)
        return 65; // Cascade Lake
    if (strcmp(arch, "ICX") == 0)
        return 89; // Ice Lake
    if (strcmp(arch, "EMR") == 0)
        return 175; // Emerald Rapids
    // Default to Haswell
    return 34;
}

/**
 * Get RAPL config based on sensor type
 */
int get_rapl_config(const char *sensor)
{
    if (strcmp(sensor, "PKG") == 0)
        return 2; // Package energy
    if (strcmp(sensor, "PP0") == 0)
        return 1; // PP0 energy (cores)
    if (strcmp(sensor, "PP1") == 0)
        return 4; // PP1 energy (uncore)
    if (strcmp(sensor, "DRAM") == 0)
        return 8; // DRAM energy
    // Default to package
    return 2;
}

/**
 * Initialize a RAPL energy measurement event based on arch and sensor.
 * Returns file descriptor on success, -1 on error.
 */
int init_rapl_event(const char *arch, const char *sensor)
{
    struct perf_event_attr pe;
    memset(&pe, 0, sizeof(struct perf_event_attr));

    pe.type = get_rapl_type(arch); // RAPL type based on architecture
    pe.size = sizeof(struct perf_event_attr);
    pe.config = get_rapl_config(sensor); // RAPL config based on sensor
    pe.disabled = 1;
    pe.exclude_kernel = 0;
    pe.exclude_hv = 0;

    int fd = perf_event_open(&pe, -1, 0, -1, 0);
    if (fd == -1)
    {
        perror("Error opening RAPL perf event");
        return -1;
    }

    return fd;
}

/**
 * Execute a benchmark function while measuring energy consumption and execution time.
 *
 * @param bench_func   Function pointer to the benchmark to execute
 * @param params       Parameters for the benchmark function
 * @param fd           File descriptor for RAPL energy counter
 * @param energy_joules Output: total energy consumed in Joules
 * @param time_seconds  Output: total execution time in seconds
 */
void measure_energy_and_time(bench_func_t bench_func,
                             const void *params,
                             int fd,
                             double *energy_joules,
                             double *time_seconds)
{
    long long count = 0;

    ioctl(fd, PERF_EVENT_IOC_RESET, 0);
    ioctl(fd, PERF_EVENT_IOC_ENABLE, 0);

    // Call the benchmark function
    struct timespec start, end;
    clock_gettime(CLOCK_MONOTONIC, &start);
    // printf("mesure\n");
    // usleep(10000);
    bench_func(params);
    clock_gettime(CLOCK_MONOTONIC, &end);
    *time_seconds = (end.tv_sec - start.tv_sec) + (end.tv_nsec - start.tv_nsec) / 1e9;

    ioctl(fd, PERF_EVENT_IOC_DISABLE, 0);
    read(fd, &count, sizeof(long long));

    // Scale to Joules
    *energy_joules = 2.3283064365386962890625e-10f * (float)count;

    if (VERBOSE)
    {
        printf("Énergie %.6f J\n", *energy_joules);
    }
    // printf("Énergie %.6f J\n", *energy_joules);
}

/**
 * Main measurement function that can be called from main.c
 * Currently uses built-in parallel simulation for measurements.
 *
 * `exp_name` identifies the experiment/series under which results
 * are stored in the JSON (e.g. "1_0.00_1_100000000").
 */
void measure_energy_temperature(bench_func_t bench_func,
                                void *params,
                                const char *output_file,
                                const char *arch,
                                const char *sensor,
                                int n_samples,
                                const char *exp_name)
{
    int temp_dev = 1; // déviation de température
    int done_targets = 0;
    int total_samples = n_samples * temp_dev;
    int *collected_per_target = malloc(temp_dev * sizeof(int));
    if (!collected_per_target)
    {
        perror("malloc");
        return -1;
    }
    for (int i = 0; i < temp_dev; i++)
    {
        collected_per_target[i] = 0;
    }
    // Allocate memory for measurements
    double *energies = malloc(total_samples * sizeof(double));
    double *times = malloc(total_samples * sizeof(double));
    double *temperatures = malloc(total_samples * sizeof(double));
    double *voltages = malloc(total_samples * sizeof(double));
    if (!energies || !times || !temperatures || !voltages)
    {
        perror("malloc");
        free(energies);
        free(times);
        free(temperatures);
        free(voltages);
        free(collected_per_target);
        return -1;
    }
    int fd = init_rapl_event(arch, sensor);
    if (fd < 0)
    {
        free(energies);
        free(times);
        free(temperatures);
        free(voltages);
        free(collected_per_target);
        exit(EXIT_FAILURE);
    }

    int target_idx; // rangement dans l'array des temperature
    int base_temp = (int)read_core_temperature(0);
    int i = 0;
    //***
    // Fin setup
    // */
    printf("stating benchmark with temperature monitoring...\n");
    while (i < total_samples && done_targets < total_samples)
    {
        double current_temp;
        current_temp = read_core_temperature(0);
        target_idx = ((int)current_temp) - base_temp;

        if (VERBOSE)
        {
            printf("current temp: %d, (target %d + %d)\n",current_temp,base_temp,temp_dev);
        }

        // Check bounds: target_idx must be in [0, n_temps)
        if (target_idx < 0 || target_idx >= temp_dev)
        {
            usleep(100000); // Sleep 100ms
            continue;
        }

        // Check if we still need samples for this temperature
        if (collected_per_target[target_idx] < n_samples)
        {
            measure_energy_and_time(bench_func, params, fd, &energies[i], &times[i]);
            // Collect temperature and voltage from core 0
            temperatures[i] = current_temp;
            voltages[i] = read_core_voltage(0);
            if (VERBOSE)
            {
                printf("n sample %d\n", collected_per_target[target_idx]);
                printf("temperature %d\n", (int)current_temp);
            }
            collected_per_target[target_idx]++;
            done_targets++;
        }
        else
        {
            // This temperature is full, skip
            usleep(100000); // Sleep 100ms
        }
    }
    close(fd);
    free(collected_per_target);

    // Write results for benchmark
    update_subjson_double_array(output_file, "energy", exp_name, energies, total_samples);
    update_subjson_double_array(output_file, "time", exp_name, times, total_samples);
    update_subjson_double_array(output_file, "temperature", exp_name, temperatures, total_samples);
    update_subjson_double_array(output_file, "voltage", exp_name, voltages, total_samples);
    printf("Results saved successfully in: %s\n", output_file);
    return 0;
}

int main(int argc, char **argv)
{
    const char *input_cfg = "input_demo.json";
    const char *output_file = "sim1.json";

    params_t json_params;
    memset(&json_params, 0, sizeof(json_params));

    if (read_params_from_json(input_cfg, &json_params) != 0)
    {
        fprintf(stderr, "Error reading params from %s\n", input_cfg);
        return EXIT_FAILURE;
    }

    printf("Loaded config: arch=%s sensor=%s freq=%.2f n_work=%d n_stat=%d n_cores=%d seq_fraction=%.2f\n",
           json_params.arch,
           json_params.sensor,
           json_params.freq,
           json_params.total_operations,
           json_params.n_stat,
           json_params.n_cores,
           json_params.seq_fraction);

    // Build core counts [1..n_cores]
    int n_cores_count = json_params.n_cores;
    int *n_cores_array = malloc(sizeof(int) * n_cores_count);
    if (!n_cores_array)
    {
        perror("malloc n_cores_array");
        return EXIT_FAILURE;
    }
    for (int i = 0; i < n_cores_count; ++i)
        n_cores_array[i] = i + 1;

    // Single sequential fraction value from config
    float seq_fraction_array[1] = {json_params.seq_fraction};
    int seq_fraction_count = 1;

    if (create_output_json(output_file, &json_params, n_cores_array, n_cores_count, seq_fraction_array, seq_fraction_count) != 0)
    {
        fprintf(stderr, "Error creating output JSON\n");
        free(n_cores_array);
        return EXIT_FAILURE;
    }
    set_fixed_frequency(json_params.freq);
    for (int nthreads = 1; nthreads < n_cores_count + 1; nthreads++)
    {
        parallel_sim_params_t sim = {
            .nthreads = nthreads,
            .nbarriers = 1, // minimum 1 sinon pas de travail
            .seq_fraction = seq_fraction_array[0],
            .total_units_per_barrier = (uint64_t)json_params.total_operations,
        };
        char *exp_name = build_name(&sim);
        measure_energy_temperature(
            exec_parallel_simulation_core_control,
            &sim,
            output_file,
            json_params.arch,
            json_params.sensor,
            json_params.n_stat,
            exp_name);
        free(exp_name);
    }
    free(n_cores_array);
    return 0;
}










