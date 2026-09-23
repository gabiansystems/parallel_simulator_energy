#define _GNU_SOURCE
#include "parallel_sim.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <sched.h>
#include <unistd.h>
#include <stdint.h>

static pthread_barrier_t barrier;
static volatile double sink = 0.0;

typedef struct {
    int tid;
    const parallel_sim_params_t *params;
    uint64_t seq_units;
    uint64_t parallel_units;
} thread_arg_t;

static inline void do_work(uint64_t units)
{
    double x = 1.23456789;
    for (uint64_t i = 0; i < units; ++i)
        x = x * 1.0000001 + 0.0000001;
    sink += x;
}

/* Detect threads-per-core from sysfs topology of cpu0.
 * Falls back to 2 (standard HT) on any error. */
static int detect_tpc(void)
{
    FILE *f = fopen("/sys/devices/system/cpu/cpu0/topology/thread_siblings_list", "r");
    if (!f) return 2;
    char buf[64] = {0};
    if (!fgets(buf, sizeof(buf), f)) { fclose(f); return 2; }
    fclose(f);
    int tpc = 1;
    for (int i = 0; buf[i] && buf[i] != '\n'; i++)
        if (buf[i] == ',') tpc++;
    return tpc > 0 ? tpc : 2;
}

static void *thread_main(void *arg)
{
    thread_arg_t *a = (thread_arg_t *)arg;
    const parallel_sim_params_t *p = a->params;

    for (int b = 0; b < p->nbarriers; ++b) {
        if (a->tid == 0 && a->seq_units > 0)
            do_work(a->seq_units);
        if (a->parallel_units > 0)
            do_work(a->parallel_units);
        if (p->nbarriers > 1)
            pthread_barrier_wait(&barrier);
    }
    return NULL;
}

void exec_parallel_simulation_core_control(const parallel_sim_params_t *params)
{
    int nthreads = params->nthreads;
    double seq_frac = params->seq_fraction;
    uint64_t total_units = params->total_units_per_barrier;
    int tpc = (params->tpc > 0) ? params->tpc : detect_tpc();

    uint64_t seq_units = (uint64_t)(total_units * (seq_frac / 100.0));
    uint64_t parallel_total = (total_units > seq_units) ? (total_units - seq_units) : 0;
    uint64_t parallel_per_thread = parallel_total / nthreads;
    uint64_t remainder = parallel_total % nthreads;

    pthread_t *threads = malloc(sizeof(pthread_t) * nthreads);
    thread_arg_t *args = malloc(sizeof(thread_arg_t) * nthreads);
    if (!threads || !args) { free(threads); free(args); return; }

    pthread_barrier_init(&barrier, NULL, nthreads);

    for (int t = 0; t < nthreads; ++t) {
        args[t].tid = t;
        args[t].params = params;
        args[t].seq_units = seq_units;
        args[t].parallel_units = parallel_per_thread + (t == 0 ? remainder : 0);

        pthread_attr_t attr;
        pthread_attr_init(&attr);

        cpu_set_t cpuset;
        CPU_ZERO(&cpuset);
        int cpu_id = t * tpc;
        CPU_SET(cpu_id, &cpuset);
        pthread_attr_setaffinity_np(&attr, sizeof(cpu_set_t), &cpuset);

        if (pthread_create(&threads[t], &attr, thread_main, &args[t]) != 0)
            perror("pthread_create");

        pthread_attr_destroy(&attr);
    }

    for (int t = 0; t < nthreads; ++t)
        pthread_join(threads[t], NULL);

    pthread_barrier_destroy(&barrier);
    free(threads);
    free(args);
}
