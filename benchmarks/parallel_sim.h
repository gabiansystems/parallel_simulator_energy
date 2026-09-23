#ifndef PARALLEL_SIM_H
#define PARALLEL_SIM_H

#include <stdint.h>

typedef struct {
    int nthreads;
    int nbarriers;
    double seq_fraction;              /* percent 0–100 */
    uint64_t total_units_per_barrier;
    int tpc;                          /* threads per core (0 → auto-detect from sysfs) */
} parallel_sim_params_t;

void exec_parallel_simulation_core_control(const parallel_sim_params_t *params);

#endif /* PARALLEL_SIM_H */
