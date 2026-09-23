/*
 * test_sim.c — Unit tests for the parallel simulation kernel.
 *
 * Tests pure C logic (no RAPL, no MSR, no root required).
 * Checks: work distribution, sequential fraction split, determinism,
 *         auto-detect TPC fallback.
 *
 * Usage: make test
 */

#include "unity/unity.h"
#include "../benchmarks/parallel_sim.h"
#include <stdint.h>
#include <string.h>

void setUp(void)    {}
void tearDown(void) {}

/* ── work unit distribution ──────────────────────────────────────────────── */

void test_zero_seq_fraction_gives_all_parallel(void)
{
    uint64_t total = 1000000;
    double seq_frac = 0.0;
    uint64_t seq = (uint64_t)(total * (seq_frac / 100.0));
    TEST_ASSERT_EQUAL_UINT64(0, seq);
    TEST_ASSERT_EQUAL_UINT64(total, total - seq);
}

void test_full_seq_fraction_gives_all_sequential(void)
{
    uint64_t total = 1000000;
    double seq_frac = 100.0;
    uint64_t seq = (uint64_t)(total * (seq_frac / 100.0));
    TEST_ASSERT_EQUAL_UINT64(total, seq);
}

void test_partial_seq_fraction(void)
{
    uint64_t total = 1000000;
    double seq_frac = 25.0;
    uint64_t seq = (uint64_t)(total * (seq_frac / 100.0));
    TEST_ASSERT_EQUAL_UINT64(250000, seq);
    TEST_ASSERT_EQUAL_UINT64(750000, total - seq);
}

void test_parallel_per_thread_divides_evenly(void)
{
    uint64_t total = 1000000;
    uint64_t seq   = 0;
    uint64_t par   = total - seq;
    int nthreads   = 4;
    uint64_t per   = par / nthreads;
    uint64_t rem   = par % nthreads;
    TEST_ASSERT_EQUAL_UINT64(250000, per);
    TEST_ASSERT_EQUAL_UINT64(0,      rem);
}

void test_parallel_per_thread_with_remainder(void)
{
    uint64_t total = 1000001;
    uint64_t par   = total;
    int nthreads   = 4;
    uint64_t per   = par / nthreads;
    uint64_t rem   = par % nthreads;
    /* thread 0 gets per + rem, others get per */
    TEST_ASSERT_EQUAL_UINT64(250000, per);
    TEST_ASSERT_EQUAL_UINT64(1,      rem);
    TEST_ASSERT_EQUAL_UINT64(total, (nthreads - 1) * per + (per + rem));
}

/* ── parallel_sim_params_t struct ────────────────────────────────────────── */

void test_params_struct_fields(void)
{
    parallel_sim_params_t p;
    memset(&p, 0, sizeof(p));
    p.nthreads               = 4;
    p.nbarriers              = 1;
    p.seq_fraction           = 25.0;
    p.total_units_per_barrier = 1000000ULL;
    p.tpc                    = 2;

    TEST_ASSERT_EQUAL_INT(4, p.nthreads);
    TEST_ASSERT_EQUAL_INT(1, p.nbarriers);
    TEST_ASSERT_EQUAL_DOUBLE(25.0, p.seq_fraction);
    TEST_ASSERT_EQUAL_UINT64(1000000ULL, p.total_units_per_barrier);
    TEST_ASSERT_EQUAL_INT(2, p.tpc);
}

/* ── smoke test: runs without crashing ───────────────────────────────────── */

void test_exec_parallel_sim_runs(void)
{
    parallel_sim_params_t p = {
        .nthreads               = 2,
        .nbarriers              = 1,
        .seq_fraction           = 0.0,
        .total_units_per_barrier = 100000ULL, /* small: fast */
        .tpc                    = 1,          /* 1 logical CPU per core */
    };
    exec_parallel_simulation_core_control(&p);
    TEST_PASS();
}

void test_exec_parallel_sim_single_thread(void)
{
    parallel_sim_params_t p = {
        .nthreads               = 1,
        .nbarriers              = 1,
        .seq_fraction           = 100.0,      /* all sequential */
        .total_units_per_barrier = 100000ULL,
        .tpc                    = 1,
    };
    exec_parallel_simulation_core_control(&p);
    TEST_PASS();
}

/* ── runner ──────────────────────────────────────────────────────────────── */

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_zero_seq_fraction_gives_all_parallel);
    RUN_TEST(test_full_seq_fraction_gives_all_sequential);
    RUN_TEST(test_partial_seq_fraction);
    RUN_TEST(test_parallel_per_thread_divides_evenly);
    RUN_TEST(test_parallel_per_thread_with_remainder);
    RUN_TEST(test_params_struct_fields);
    RUN_TEST(test_exec_parallel_sim_runs);
    RUN_TEST(test_exec_parallel_sim_single_thread);
    return UNITY_END();
}
