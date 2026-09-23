#define _GNU_SOURCE
#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <string.h>
#include <stdint.h>
#include <sys/ioctl.h>
#include <linux/perf_event.h>
#include <asm/unistd.h>
#include <errno.h>
#include <time.h>
#include <fcntl.h>
#include <math.h>
#include "counter.h"
#include "../utils/json_utils.h"

#define MSR_IA32_PERF_STATUS   0x198
#define MSR_IA32_THERM_STATUS  0x19C
#define MSR_TEMPERATURE_TARGET 0x1A2
#define MSR_UNCORE_RATIO_LIMIT 0x620
#define MSR_UNCORE_PERF_STATUS 0x621

/* ── MSR ─────────────────────────────────────────────────────────────────── */

int read_msr(int cpu, off_t msr, uint64_t *value)
{
    char path[64];
    snprintf(path, sizeof(path), "/dev/cpu/%d/msr", cpu);
    int fd = open(path, O_RDONLY);
    if (fd < 0) {
        fprintf(stderr, "[WARN] open MSR failed (cpu=%d): %s\n", cpu, strerror(errno));
        return -1;
    }
    if (pread(fd, value, sizeof(*value), msr) != (ssize_t)sizeof(*value)) {
        fprintf(stderr, "[WARN] pread MSR failed (cpu=%d msr=0x%lx): %s\n",
                cpu, (long)msr, strerror(errno));
        close(fd);
        return -1;
    }
    close(fd);
    return 0;
}

int write_msr(int cpu, off_t msr, uint64_t value)
{
    char path[64];
    snprintf(path, sizeof(path), "/dev/cpu/%d/msr", cpu);
    int fd = open(path, O_WRONLY);
    if (fd < 0) { perror("open MSR write"); return -1; }
    if (pwrite(fd, &value, sizeof(value), msr) != (ssize_t)sizeof(value)) {
        fprintf(stderr, "[WARN] pwrite MSR failed (cpu=%d msr=0x%lx): %s\n",
                cpu, (long)msr, strerror(errno));
        close(fd);
        return -1;
    }
    close(fd);
    return 0;
}

/* ── Uncore frequency ────────────────────────────────────────────────────── */

static void set_uncore_freq(double freq_ghz)
{
    int ratio = (int)(freq_ghz * 10);
    uint64_t val = ((uint64_t)ratio << 8) | ratio;
    if (write_msr(0, MSR_UNCORE_RATIO_LIMIT, val) == 0)
        printf("  Uncore frequency fixed to %d00 MHz\n", ratio);
    else
        fprintf(stderr, "[WARN] Uncore MSR not supported on this CPU (ignored)\n");
}

static double read_uncore_freq_ghz(void)
{
    uint64_t val;
    if (read_msr(0, MSR_UNCORE_PERF_STATUS, &val) != 0) return -1.0;
    return (val & 0xff) * 0.1;
}

/* ── Core frequency ──────────────────────────────────────────────────────── */

static int detect_intel_pstate(void)
{
    FILE *f = fopen("/sys/devices/system/cpu/cpu0/cpufreq/scaling_driver", "r");
    if (!f) return 0;
    char driver[64] = {0};
    if (fgets(driver, sizeof(driver), f)) { /* consumed */ }
    fclose(f);
    driver[strcspn(driver, "\n")] = 0;
    return strcmp(driver, "intel_pstate") == 0;
}

static void set_frequency_intel(double freq_ghz)
{
    long target_khz = (long)(freq_ghz * 1e6);

    if (detect_intel_pstate()) {
        FILE *nt = fopen("/sys/devices/system/cpu/intel_pstate/no_turbo", "w");
        if (nt) { fprintf(nt, "1"); fclose(nt); }
        for (int cpu = 0; ; cpu++) {
            char path[128];
            snprintf(path, sizeof(path),
                     "/sys/devices/system/cpu/cpu%d/cpufreq/scaling_max_freq", cpu);
            FILE *f = fopen(path, "w");
            if (!f) break;
            fprintf(f, "%ld", target_khz);
            fclose(f);
            snprintf(path, sizeof(path),
                     "/sys/devices/system/cpu/cpu%d/cpufreq/scaling_min_freq", cpu);
            f = fopen(path, "w");
            if (f) { fprintf(f, "%ld", target_khz); fclose(f); }
        }
    } else {
        FILE *boost = fopen("/sys/devices/system/cpu/cpufreq/boost", "w");
        if (boost) { fprintf(boost, "0"); fclose(boost); }
        char cmd[256];
        snprintf(cmd, sizeof(cmd),
                 "cpupower frequency-set -g userspace 2>&1 >/dev/null");
        system(cmd);
        snprintf(cmd, sizeof(cmd),
                 "cpupower frequency-set -f %.2fGHz 2>&1 >/dev/null", freq_ghz);
        system(cmd);
    }
}

static void set_frequency_amd(double freq_ghz)
{
    long freq_hz = (long)(freq_ghz * 1e6);
    for (int cpu = 0; ; cpu++) {
        char path[128];
        snprintf(path, sizeof(path),
                 "/sys/devices/system/cpu/cpu%d/cpufreq/scaling_governor", cpu);
        FILE *f = fopen(path, "w");
        if (!f) break;
        fprintf(f, "userspace"); fclose(f);
        snprintf(path, sizeof(path),
                 "/sys/devices/system/cpu/cpu%d/cpufreq/scaling_setspeed", cpu);
        f = fopen(path, "w");
        if (f) { fprintf(f, "%ld", freq_hz); fclose(f); }
    }
}

/* Always locks both core and uncore — this repo measures uncore-lock effects. */
void set_fixed_frequency(double freq_ghz, const char *vendor)
{
    printf("=== Setting core + uncore frequency to %.2f GHz ===\n", freq_ghz);

    if (vendor && strcmp(vendor, "AMD") == 0)
        set_frequency_amd(freq_ghz);
    else
        set_frequency_intel(freq_ghz);

    set_uncore_freq(freq_ghz);
    usleep(500000);

    /* Verify core bounds */
    double tol = 0.1;
    int mismatch = 0;
    for (int cpu = 0; ; cpu++) {
        char path[128];
        snprintf(path, sizeof(path),
                 "/sys/devices/system/cpu/cpu%d/cpufreq/scaling_max_freq", cpu);
        FILE *f = fopen(path, "r");
        if (!f) break;
        long max_khz = 0;
        if (fscanf(f, "%ld", &max_khz) != 1) { fclose(f); break; }
        fclose(f);
        if (fabs(max_khz / 1e6 - freq_ghz) > tol) mismatch++;
    }
    if (mismatch == 0)
        printf("  All CPUs pinned to %.2f GHz\n", freq_ghz);
    else
        fprintf(stderr, "[WARN] %d CPUs did not pin to %.2f GHz\n", mismatch, freq_ghz);

    /* Verify uncore */
    double unc = read_uncore_freq_ghz();
    if (unc > 0 && fabs(unc - freq_ghz) > tol)
        fprintf(stderr, "[WARN] Uncore at %.3f GHz (expected %.2f)\n", unc, freq_ghz);
    else if (unc > 0)
        printf("  Uncore at %.2f GHz ✓\n", unc);
}

/* ── Temperature ─────────────────────────────────────────────────────────── */

static double read_temperature_intel_hwmon(void)
{
    char path[128];
    for (int i = 0; i < 16; i++) {
        snprintf(path, sizeof(path), "/sys/class/hwmon/hwmon%d/name", i);
        FILE *f = fopen(path, "r");
        if (!f) continue;
        char name[32] = {0};
        fgets(name, sizeof(name), f); fclose(f);
        if (!strstr(name, "coretemp")) continue;
        snprintf(path, sizeof(path), "/sys/class/hwmon/hwmon%d/temp1_input", i);
        f = fopen(path, "r");
        if (!f) return -1.0;
        int milli; int ok = fscanf(f, "%d", &milli); fclose(f);
        return (ok == 1) ? milli / 1000.0 : -1.0;
    }
    return -1.0;
}

static double read_temperature_intel(int core)
{
    uint64_t val;
    if (read_msr(core, MSR_IA32_THERM_STATUS, &val) != 0)
        return read_temperature_intel_hwmon();

    unsigned int dts = (val >> 16) & 0x7F;

    uint64_t target;
    int tjmax = 100;
    if (read_msr(core, MSR_TEMPERATURE_TARGET, &target) == 0)
        tjmax = (int)((target >> 16) & 0xFF);

    return (double)(tjmax - (int)dts);
}

static double read_temperature_amd(void)
{
    char path[128];
    for (int i = 0; i < 10; i++) {
        snprintf(path, sizeof(path), "/sys/class/hwmon/hwmon%d/name", i);
        FILE *f = fopen(path, "r");
        if (!f) continue;
        char name[32] = {0};
        fgets(name, sizeof(name), f); fclose(f);
        if (!strstr(name, "k10temp")) continue;
        snprintf(path, sizeof(path), "/sys/class/hwmon/hwmon%d/temp1_input", i);
        f = fopen(path, "r");
        if (!f) return -1.0;
        int milli; int ok = fscanf(f, "%d", &milli); fclose(f);
        return (ok == 1) ? milli / 1000.0 : -1.0;
    }
    return -1.0;
}

double read_core_temperature(int core, const char *vendor)
{
    if (vendor && strcmp(vendor, "AMD") == 0)
        return read_temperature_amd();
    return read_temperature_intel(core);
}

/* ── Voltage ─────────────────────────────────────────────────────────────── */

double read_core_voltage(int core)
{
    uint64_t val;
    if (read_msr(core, MSR_IA32_PERF_STATUS, &val) != 0) return -1.0;
    return ((val >> 32) & 0xFFFF) * 0.001;
}

/* ── RAPL perf event ─────────────────────────────────────────────────────── */

long perf_event_open(struct perf_event_attr *hw_event, pid_t pid,
                     int cpu, int group_fd, unsigned long flags)
{
    return syscall(__NR_perf_event_open, hw_event, pid, cpu, group_fd, flags);
}

int init_rapl_event(int arch, int sensor)
{
    struct perf_event_attr pe;
    memset(&pe, 0, sizeof(pe));
    pe.type = arch; pe.size = sizeof(pe); pe.config = sensor;
    pe.disabled = 1; pe.exclude_kernel = 0; pe.exclude_hv = 0;

    int cpu = 0;
    const char *pmu_dir = find_rapl_pmu_dir();
    if (pmu_dir) {
        char mask[320];
        snprintf(mask, sizeof(mask), "%s/cpumask", pmu_dir);
        FILE *f = fopen(mask, "r");
        if (f) { int c = -1; if (fscanf(f, "%d", &c) == 1 && c >= 0) cpu = c; fclose(f); }
    }

    int fd = perf_event_open(&pe, -1, cpu, -1, 0);
    if (fd == -1)
        fprintf(stderr, "[RAPL] perf_event_open failed: type=%d sensor=%d cpu=%d — %s\n",
                arch, sensor, cpu, strerror(errno));
    return fd;
}

/* ── Measurement loop ────────────────────────────────────────────────────── */

static void measure_once(bench_func_t bench_func, const void *params,
                         int fd, double scale,
                         double *energy_j, double *time_s)
{
    long long count = 0;
    ioctl(fd, PERF_EVENT_IOC_RESET, 0);
    ioctl(fd, PERF_EVENT_IOC_ENABLE, 0);
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    bench_func(params);
    clock_gettime(CLOCK_MONOTONIC, &t1);
    *time_s = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) / 1e9;
    ioctl(fd, PERF_EVENT_IOC_DISABLE, 0);
    read(fd, &count, sizeof(long long));
    *energy_j = scale * (double)count;
}

int measure_energy_temperature(bench_func_t bench_func, void *params,
                               const measure_config_t *cfg)
{
    double *energies     = malloc(cfg->n_samples * sizeof(double));
    double *times        = malloc(cfg->n_samples * sizeof(double));
    double *temperatures = malloc(cfg->n_samples * sizeof(double));
    double *voltages     = malloc(cfg->n_samples * sizeof(double));
    if (!energies || !times || !temperatures || !voltages) {
        perror("malloc"); free(energies); free(times);
        free(temperatures); free(voltages); return -1;
    }

    int fd = init_rapl_event(cfg->arch, cfg->sensor);
    if (fd < 0) {
        free(energies); free(times); free(temperatures); free(voltages);
        return -1;
    }

    double scale = read_rapl_pkg_energy_scale(2.3283064365386962890625e-10);

    bench_func(params); /* untimed warmup */

    for (int i = 0; i < cfg->n_samples; i++) {
        temperatures[i] = read_core_temperature(0, cfg->vendor);
        measure_once(bench_func, params, fd, scale, &energies[i], &times[i]);
        voltages[i] = read_core_voltage(0);
    }
    close(fd);

    char json_path[512];
    snprintf(json_path, sizeof(json_path), "%s.json", cfg->output_file);
    update_subjson_double_array(json_path, "energy",      cfg->exp_name, energies,     cfg->n_samples);
    update_subjson_double_array(json_path, "time",        cfg->exp_name, times,        cfg->n_samples);
    update_subjson_double_array(json_path, "temperature", cfg->exp_name, temperatures, cfg->n_samples);
    update_subjson_double_array(json_path, "voltage",     cfg->exp_name, voltages,     cfg->n_samples);

    for (int i = 0; i < cfg->n_samples; i++)
        append_csv_row(cfg->output_file, energies[i], times[i],
                       temperatures[i], voltages[i],
                       cfg->n_cores, cfg->seq_frac, cfg->nbarriers);

    free(energies); free(times); free(temperatures); free(voltages);
    return 0;
}
