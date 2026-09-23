#ifndef COUNTER_H
#define COUNTER_H

#include <stdint.h>
#include <sys/types.h>
#include <linux/perf_event.h>

typedef void (*bench_func_t)(const void *params);

typedef struct {
    const char *output_file; /* base path: <output_file>.json and <output_file>.csv */
    const char *exp_name;    /* key written into the JSON */
    const char *vendor;      /* "Intel" or "AMD" */
    int arch;                /* RAPL perf_event type */
    int sensor;              /* RAPL perf_event config (PKG=2, PP0=1, DRAM=8) */
    int n_samples;
    int n_cores;             /* annotates CSV rows */
    double seq_frac;         /* annotates CSV rows */
    int nbarriers;           /* annotates CSV rows */
} measure_config_t;

int    read_msr(int cpu, off_t msr, uint64_t *value);
int    write_msr(int cpu, off_t msr, uint64_t value);

/* Sets both core and uncore frequency — always, since this repo specifically
 * investigates uncore-frequency locking effects on energy measurements. */
void   set_fixed_frequency(double freq_ghz, const char *vendor);

double read_core_temperature(int core, const char *vendor);
double read_core_voltage(int core);
long   perf_event_open(struct perf_event_attr *hw_event, pid_t pid,
                       int cpu, int group_fd, unsigned long flags);
int    init_rapl_event(int arch, int sensor);
int    measure_energy_temperature(bench_func_t bench_func, void *params,
                                  const measure_config_t *cfg);

#endif /* COUNTER_H */
