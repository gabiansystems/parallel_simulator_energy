#ifndef JSON_UTILS_H
#define JSON_UTILS_H

#include "../benchmarks/parallel_sim.h"

typedef struct {
    int arch;               /* RAPL perf_event type */
    int sensor;             /* RAPL domain config */
    double freq;            /* Target CPU frequency in GHz */
    int total_operations;   /* Synthetic work units per run */
    int n_stat;             /* Number of repetitions per configuration */
    int n_cores;            /* Maximum core count */
    float seq_fraction;     /* Sequential fraction in percent */
    char vendor[16];        /* "Intel" or "AMD" */
} params_t;

/* RAPL sysfs */
const char *find_rapl_pmu_dir(void);
double      read_rapl_pkg_energy_scale(double fallback_j_per_count);
int         get_rapl_type(const char *arch);
int         get_rapl_config(const char *sensor);

/* JSON I/O */
int   read_params_from_json(const char *filename, params_t *p);
int   create_output_files(const char *base_path, const params_t *params,
                          const int *n_cores_array, int n_cores_count,
                          const float *seq_fraction_array, int seq_fraction_count);
void  update_subjson_double_array(const char *output_file, const char *key,
                                  const char *exp_name, const double *values, int count);
char *build_name(const parallel_sim_params_t *sim);

/* CSV */
void append_csv_row(const char *base_path, double energy, double time,
                    double temp, double voltage,
                    int n_cores, double seq_frac, int nbarriers);

#endif /* JSON_UTILS_H */
