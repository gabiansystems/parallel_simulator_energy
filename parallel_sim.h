#ifndef PARALLEL_SIM_H
#define PARALLEL_SIM_H

#include <stdint.h>

/**
 * Parameters controlling the synthetic parallel simulation.
 *
 * The model is Amdahl-like: a given fraction of the work is done
 * sequentially, the rest is distributed across worker threads.
 */
typedef struct
{
    int nthreads;                  /**< Number of worker threads. */
    int nbarriers;                 /**< Number of barriers (phases) per run. */
    double seq_fraction;           /**< Sequential work fraction in percent (0–100). */
    uint64_t total_units_per_barrier; /**< Total synthetic work units per barrier. */
} parallel_sim_params_t;

/**
 * Execute the synthetic parallel workload with basic core control.
 *
 * Threads are pinned to CPUs according to a simple topology model so
 * that measurements are more reproducible.
 */
void exec_parallel_simulation_core_control(const parallel_sim_params_t *params);

#endif