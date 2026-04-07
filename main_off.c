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
#define VERBOSE 0

/////// hardware utils /////////

#define MSR_IA32_PERF_STATUS 0x198
#define MSR_IA32_THERM_STATUS 0x19C
#define MSR_UNCORE_RATIO_LIMIT 0x620
#define MSR_UNCORE_PERF_STATUS 0x621

int write_msr(int cpu, off_t msr, uint64_t value)
{
    char path[64];
    int fd;

    sprintf(path, "/dev/cpu/%d/msr", cpu);
    fd = open(path, O_WRONLY);
    if (fd < 0)
    {
        perror("open");
        return -1;
    }

    if (pwrite(fd, &value, sizeof(value), msr) != sizeof(value))
    {
        perror("pwrite");
        close(fd);
        return -1;
    }

    close(fd);
    return 0;
}

uint64_t read_msr(int cpu, off_t msr)
{
    char path[64];
    int fd;
    uint64_t value;

    sprintf(path, "/dev/cpu/%d/msr", cpu);
    fd = open(path, O_RDONLY);
    if (fd < 0)
    {
        perror("open");
        return 0;
    }

    if (pread(fd, &value, sizeof(value), msr) != sizeof(value))
    {
        perror("pread");
        close(fd);
        return 0;
    }

    close(fd);
    return value;
}

uint64_t build_uncore_value(int min_ratio, int max_ratio)
{
    return ((uint64_t)min_ratio << 8) | max_ratio;
}

void set_uncore_freq_ghz(int cpu, int ratio)
{
    uint64_t val = build_uncore_value(ratio, ratio);
    if (write_msr(cpu, MSR_UNCORE_RATIO_LIMIT, val) == 0)
        printf("Uncore frequency fixed to %d00 MHz\n", ratio);
}

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
    //set_uncore_freq_ghz(0, (int)(freq_ghz * 10));
}

double read_core_voltage(int core)
{
    uint64_t val = read_msr(0, MSR_IA32_PERF_STATUS);
    // Bits [47:32] contain the current VID value *in Intel VID units (1mV steps)*
    unsigned int vid = (val >> 32) & 0xFFFF;
    double voltage = vid * 0.001; // ≈ convert to volts
    return voltage;
}
double read_core_temperature(int core)
{
    uint64_t val = read_msr(0, MSR_IA32_THERM_STATUS);
    // For Haswell, temperature is in bits 22:16 (Reading Valid) and 6:0 (Temperature)
    // Temperature Target is in bits 23:16, Digital Readout in bits 6:0
    unsigned int temp_reading = (val >> 16) & 0x7F; // Bits 22:16 for Reading Valid + Digital readout
    double temperature = (double)temp_reading;      // Temperature in degrees Celsius
    return temperature;
}

double read_core_freq_ghz(int cpu)
{
    uint64_t val = read_msr(cpu, MSR_IA32_PERF_STATUS);
    int ratio = (val >> 8) & 0xff; // Bits 15:8 contain current multiplier
    return ratio * 0.1;            // ratio * 100 MHz -> GHz
}
double read_uncore_freq_ghz(int cpu)
{
    uint64_t val = read_msr(cpu, MSR_UNCORE_PERF_STATUS);

    int ratio = val & 0xff; // lower 8 bits
    return ratio * 0.1;     // ratio * 100 MHz -> GHz
}

long perf_event_open(struct perf_event_attr *hw_event, pid_t pid,
                     int cpu, int group_fd, unsigned long flags)
{
    int ret;

    ret = syscall(__NR_perf_event_open, hw_event, pid, cpu,
                  group_fd, flags);
    return ret;
}
/**
 * Initialize a RAPL energy measurement event based on arch and sensor.
 * Returns file descriptor on success, -1 on error.
 */
int init_rapl_event(int arch, int sensor)
{
    struct perf_event_attr pe;
    memset(&pe, 0, sizeof(struct perf_event_attr));

    pe.type = arch; // RAPL type based on architecture
    pe.size = sizeof(struct perf_event_attr);
    pe.config = sensor; // RAPL config based on sensor
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

/////// temperature utils ////////

static void warmup_until_temperature(double target_temp,
                                     double max_seconds)
{
    struct timespec start, now;
    clock_gettime(CLOCK_MONOTONIC, &start);
    double current_temp;
    printf("%d\n", (int)target_temp);
    while (1)
    {
        usleep(100000); // Sleep 100ms
        // run_synthetic_load();
        current_temp = read_core_temperature(0);
        printf("temp: %d\n", (int)current_temp);
        if (current_temp >= target_temp)
            break;

        clock_gettime(CLOCK_MONOTONIC, &now);
        double elapsed = (now.tv_sec - start.tv_sec) +
                         (now.tv_nsec - start.tv_nsec) / 1e9;

        if (elapsed >= max_seconds) // safety exit
            break;
    }
}

static void stabilize_temperature(double max_variation,
                                  int required_stable_records,
                                  double max_seconds)
{
    struct timespec start, now;
    clock_gettime(CLOCK_MONOTONIC, &start);

    double prev_temp = read_core_temperature(0);
    int stable_count = 0;

    printf("stabilize start temperature: %d\n", (int)prev_temp);

    while (1)
    {
        double current_temp = read_core_temperature(0);
        printf("temperature %d\n", (int)current_temp);
        if (fabs(current_temp - prev_temp) <= max_variation)
            stable_count++;
        else
            stable_count = 0;

        if (stable_count >= required_stable_records)
            break;

        prev_temp = current_temp;

        clock_gettime(CLOCK_MONOTONIC, &now);
        double elapsed = (now.tv_sec - start.tv_sec) +
                         (now.tv_nsec - start.tv_nsec) / 1e9;

        if (elapsed >= max_seconds)
        { // safety exit
            printf("Time up\n");
            break;
        }
        usleep(100000);
    }

    printf("stabilization reached: %d consecutive records within %.2f variation\n",
           stable_count, max_variation);
}

//////// measurements ////////

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
                                int arch,
                                int sensor,
                                int n_samples,
                                const char *exp_name,
                                int base_temp)
{
    // Allocate memory for measurements
    double *energies = malloc(n_samples * sizeof(double));
    double *times = malloc(n_samples * sizeof(double));
    double *temperatures = malloc(n_samples * sizeof(double));
    double *voltages = malloc(n_samples * sizeof(double));
    if (!energies || !times || !temperatures || !voltages)
    {
        perror("malloc");
        free(energies);
        free(times);
        free(temperatures);
        free(voltages);
        return -1;
    }
    int fd = init_rapl_event(arch, sensor);
    if (fd < 0)
    {
        free(energies);
        free(times);
        free(temperatures);
        free(voltages);
        exit(EXIT_FAILURE);
    }

    double current_temp;
    //***
    // Fin setup
    // *
    for (int i = 0; i < n_samples; i++)
    {
        // Warm up cores before taking measurements so that each experiment
        // starts from a comparable temperature, regardless of nthreads or
        // total work size.
        // warmup_until_temperature(base_temp, 600.0);
        current_temp = read_core_temperature(0);
        measure_energy_and_time(bench_func, params, fd, &energies[i], &times[i]);
        // Collect temperature and voltage from core 0
        temperatures[i] = current_temp;
        voltages[i] = read_core_voltage(0);
    }
    close(fd);

    // Write results for benchmark
    update_subjson_double_array(output_file, "energy", exp_name, energies, n_samples);
    update_subjson_double_array(output_file, "time", exp_name, times, n_samples);
    update_subjson_double_array(output_file, "temperature", exp_name, temperatures, n_samples);
    update_subjson_double_array(output_file, "voltage", exp_name, voltages, n_samples);
    if (VERBOSE)
    {
        printf("Results saved successfully in: %s\n", output_file);
    }
    return 0;
}

int main(int argc, char **argv)
{
    const char *input_cfg = "input_demo.json";
    const char *output_file = "./resultats/sim1.json";
    int opt;

    // Parse command line options
    while ((opt = getopt(argc, argv, "i:o:h")) != -1)
    {
        switch (opt)
        {
        case 'i':
            input_cfg = optarg;
            break;
        case 'o':
            output_file = optarg;
            break;
        case 'h':
            printf("Usage: %s -i input_file -o output_file\n", argv[0]);
            return 0;
        default:
            fprintf(stderr, "Usage: %s -i input_file -o output_file\n", argv[0]);
            return 1;
        }
    }
    if (VERBOSE)
    {
        printf("Input config: %s\n", input_cfg);
        printf("Output file: %s\n", output_file);
    }

    params_t json_params;
    memset(&json_params, 0, sizeof(json_params));

    if (read_params_from_json(input_cfg, &json_params) != 0)
    {
        fprintf(stderr, "Error reading params from %s\n", input_cfg);
        return EXIT_FAILURE;
    }

    if (VERBOSE)
    {
        printf("Loaded config: arch=%d sensor=%d freq=%.2f n_work=%d n_stat=%d n_cores=%d seq_fraction=%.2f\n",
               json_params.arch,
               json_params.sensor,
               json_params.freq,
               json_params.total_operations,
               json_params.n_stat,
               json_params.n_cores,
               json_params.seq_fraction);
    }

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
    // stabilize_temperature(1,100,600.0);
    // usleep(100000);
    // stabilize_temperature(1,100,600.0);
    int base_temp = (int)read_core_temperature(0);

    for (int nthreads = n_cores_count; nthreads > 0; nthreads--)
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
            exp_name,
            base_temp);

        free(exp_name);
    }
    free(n_cores_array);
    return 0;
}
