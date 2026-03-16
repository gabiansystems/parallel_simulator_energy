#define _GNU_SOURCE
#include "parallel_sim.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <sched.h>
#include <unistd.h>
#include <stdint.h>
#include <sys/ioctl.h>

#include <sys/wait.h>
#include <errno.h>
#define TPC 2 // Threads per core
#define CPS 8 // Core per socket
#define CPM 2 // Core per machine
#define NCORES 8
#define WORK_UNITS 100000000ULL

static pthread_barrier_t barrier;
// pas d'optims
static volatile double sink = 0.0;

typedef struct
{
    int tid;
    const parallel_sim_params_t *params;
    uint64_t seq_units;
    uint64_t parallel_units;
} thread_arg_t;

// synthetic workload, on garde le résultat pour éviter les optimisations
static inline void do_work(uint64_t units)
{
    double x = 1.23456789;
    for (uint64_t i = 0; i < units; ++i){
        x = x * 1.0000001 + 0.0000001;
    }
    sink += x;
}


static void *worker(void *arg)
{
    int tid = (intptr_t)arg;

    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(tid, &cpuset);
    sched_setaffinity(0, sizeof(cpu_set_t), &cpuset);

    do_work(WORK_UNITS);
    return NULL;
}

void run_synthetic_load()
{
    pthread_t threads[NCORES];

    for (int t = 0; t < NCORES; ++t)
        pthread_create(&threads[t], NULL, worker, (void *)(intptr_t)t);

    for (int t = 0; t < NCORES; ++t)
        pthread_join(threads[t], NULL);
}


/**
 * @brief Dans cette version, le travail séquentiel est réalisé après la création des threads
 * Cela semble fonctionner tout de même. Une autre version est à envisager
 *
 * @param arg
 * @return void*
 */
static void *thread_main(void *arg)
{
    thread_arg_t *a = (thread_arg_t *)arg;
    const parallel_sim_params_t *p = a->params;
    // printf("%d\n",a->parallel_units);
    for (int b = 0; b < p->nbarriers; ++b)
    {
        if (a->tid == 0 && a->seq_units > 0)
            do_work(a->seq_units);
        if (a->parallel_units > 0)
            do_work(a->parallel_units);
        if(p->nbarriers>1)
            pthread_barrier_wait(&barrier);
    }
    return NULL;
}

void exec_parallel_simulation_core_control(const parallel_sim_params_t *params)
{
    int nthreads = params->nthreads;
    double seq_frac = params->seq_fraction;
    uint64_t total_units = params->total_units_per_barrier;

    uint64_t seq_units = (uint64_t)(total_units * (seq_frac / 100.0f));
    uint64_t parallel_total = (total_units > seq_units) ? (total_units - seq_units) : 0;
    uint64_t parallel_per_thread = parallel_total / nthreads;
    uint64_t remainder = parallel_total % nthreads;

    pthread_t *threads = malloc(sizeof(pthread_t) * nthreads);
    thread_arg_t *args = malloc(sizeof(thread_arg_t) * nthreads);
    pthread_barrier_init(&barrier, NULL, nthreads);

    // --- Socket / topology config ---
    int base_cpu = 0;         // start on socket 0
    int threads_per_core = TPC; // 2 logical CPUs per core
    int cores_per_socket = CPS; // 6 physical cores per socket

    for (int t = 0; t < nthreads; ++t)
    {
        args[t].tid = t;
        args[t].params = params;
        args[t].seq_units = seq_units;
        args[t].parallel_units = parallel_per_thread + (t == 0 ? remainder : 0);
        // printf("cores: %d\n",parallel_per_thread);

        // surcouche pour choisir le coeur précisément
        pthread_attr_t attr;
        pthread_attr_init(&attr);

        // assign CPU affinity: only one socket, one thread per core
        cpu_set_t cpuset;
        CPU_ZERO(&cpuset);
        int cpu_id = base_cpu + t * threads_per_core; // 0,2,4,6,8,10,...
        if (cpu_id >= base_cpu + cores_per_socket * threads_per_core)
            break;

        CPU_SET(cpu_id, &cpuset);
        pthread_attr_setaffinity_np(&attr, sizeof(cpu_set_t), &cpuset);

        if (pthread_create(&threads[t], &attr, thread_main, &args[t]) != 0)
            perror("pthread_create");

        pthread_attr_destroy(&attr);
        // ça fait beaucoup :=(
    }

    for (int t = 0; t < nthreads; ++t)
        pthread_join(threads[t], NULL);

    pthread_barrier_destroy(&barrier);
    free(threads);
    free(args);
}
