/*
 * test_probes.c — Sanity checks for RAPL and MSR hardware probes.
 *
 * Requires root (or sudo-g5k on G5K nodes) for:
 *   - perf_event_open with RAPL PMU
 *   - /dev/cpu/0/msr
 *
 * Build: make test_probes
 * Run:   sudo-g5k ./test_probes
 *
 * Exits 0 if all probes pass/skip, non-zero on failures.
 * SKIP is printed (not FAIL) when a probe is unavailable, so the
 * test is non-destructive on systems without RAPL or MSR support.
 */

#include "unity/unity.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <stdint.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <linux/perf_event.h>

void setUp(void)    {}
void tearDown(void) {}

/* ── helpers ─────────────────────────────────────────────────────────────── */

static int rapl_pmu_type(void)
{
    const char *paths[] = {
        "/sys/bus/event_source/devices/power/type",
        "/sys/bus/event_source/devices/power_0/type",
        "/sys/bus/event_source/devices/intel-rapl/type",
        NULL
    };
    for (int i = 0; paths[i]; i++) {
        FILE *f = fopen(paths[i], "r");
        if (!f) continue;
        int t = -1; fscanf(f, "%d", &t); fclose(f);
        if (t > 0) return t;
    }
    return -1;
}

static long long rapl_pkg_config(void)
{
    const char *paths[] = {
        "/sys/bus/event_source/devices/power/events/energy-pkg",
        "/sys/bus/event_source/devices/power_0/events/energy-pkg",
        "/sys/bus/event_source/devices/intel-rapl/events/energy-pkg",
        NULL
    };
    for (int i = 0; paths[i]; i++) {
        FILE *f = fopen(paths[i], "r");
        if (!f) continue;
        long long cfg = -1; fscanf(f, "event=%lli", &cfg); fclose(f);
        if (cfg >= 0) return cfg;
    }
    return -1;
}

static int perf_open(int type, long long config)
{
    struct perf_event_attr attr;
    memset(&attr, 0, sizeof(attr));
    attr.type = type; attr.size = sizeof(attr);
    attr.config = config; attr.disabled = 1;
    return (int)syscall(__NR_perf_event_open, &attr, -1, 0, -1, 0);
}

/* ── tests ───────────────────────────────────────────────────────────────── */

void test_rapl_pmu_type_found(void)
{
    int t = rapl_pmu_type();
    if (t < 0) { TEST_IGNORE_MESSAGE("SKIP: RAPL PMU type not found in sysfs"); return; }
    TEST_ASSERT_GREATER_THAN(0, t);
}

void test_rapl_pkg_config_found(void)
{
    long long cfg = rapl_pkg_config();
    if (cfg < 0) { TEST_IGNORE_MESSAGE("SKIP: energy-pkg config not found in sysfs"); return; }
    TEST_ASSERT_GREATER_OR_EQUAL(0, (int)cfg);
}

void test_rapl_fd_opens(void)
{
    int type = rapl_pmu_type();
    long long cfg = rapl_pkg_config();
    if (type < 0 || cfg < 0) { TEST_IGNORE_MESSAGE("SKIP: RAPL sysfs entries missing"); return; }
    int fd = perf_open(type, cfg);
    if (fd < 0) {
        if (errno == EACCES || errno == EPERM)
            TEST_IGNORE_MESSAGE("SKIP: insufficient permissions (run as root or sudo-g5k)");
        else
            TEST_FAIL_MESSAGE("perf_event_open failed for RAPL PKG");
        return;
    }
    TEST_ASSERT_GREATER_OR_EQUAL(0, fd);
    close(fd);
}

void test_rapl_energy_increases(void)
{
    int type = rapl_pmu_type();
    long long cfg = rapl_pkg_config();
    if (type < 0 || cfg < 0) { TEST_IGNORE_MESSAGE("SKIP: RAPL sysfs entries missing"); return; }
    int fd = perf_open(type, cfg);
    if (fd < 0) { TEST_IGNORE_MESSAGE("SKIP: cannot open RAPL fd"); return; }

    ioctl(fd, PERF_EVENT_IOC_RESET,  0);
    ioctl(fd, PERF_EVENT_IOC_ENABLE, 0);
    volatile double x = 1.0;
    for (int i = 0; i < 2000000; i++) x = x * 1.0000001 + 0.0000001;
    (void)x;
    uint64_t v1 = 0, v2 = 0;
    read(fd, &v1, sizeof(v1));
    for (int i = 0; i < 2000000; i++) x = x * 1.0000001 + 0.0000001;
    (void)x;
    read(fd, &v2, sizeof(v2));
    ioctl(fd, PERF_EVENT_IOC_DISABLE, 0);
    close(fd);
    TEST_ASSERT_GREATER_THAN(v1, v2);
}

void test_msr_readable(void)
{
    int fd = open("/dev/cpu/0/msr", O_RDONLY);
    if (fd < 0) {
        if (errno == ENOENT)
            TEST_IGNORE_MESSAGE("SKIP: MSR module not loaded (modprobe msr)");
        else if (errno == EACCES || errno == EPERM)
            TEST_IGNORE_MESSAGE("SKIP: /dev/cpu/0/msr not accessible (run as root)");
        else
            TEST_FAIL_MESSAGE("Cannot open /dev/cpu/0/msr");
        return;
    }
    uint64_t val = 0;
    ssize_t n = pread(fd, &val, sizeof(val), 0x19C); /* MSR_IA32_THERM_STATUS */
    close(fd);
    TEST_ASSERT_EQUAL(sizeof(uint64_t), (size_t)n);
}

void test_uncore_msr_readable(void)
{
    int fd = open("/dev/cpu/0/msr", O_RDONLY);
    if (fd < 0) { TEST_IGNORE_MESSAGE("SKIP: /dev/cpu/0/msr not accessible"); return; }
    uint64_t val = 0;
    /* MSR_UNCORE_PERF_STATUS = 0x621: read current uncore ratio */
    ssize_t n = pread(fd, &val, sizeof(val), 0x621);
    close(fd);
    if (n < 0) { TEST_IGNORE_MESSAGE("SKIP: MSR_UNCORE_PERF_STATUS not available on this CPU"); return; }
    TEST_ASSERT_EQUAL(sizeof(uint64_t), (size_t)n);
    int ratio = (int)(val & 0xff);
    TEST_ASSERT_GREATER_THAN(0, ratio); /* uncore must be running at some ratio */
}

/* ── runner ──────────────────────────────────────────────────────────────── */

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_rapl_pmu_type_found);
    RUN_TEST(test_rapl_pkg_config_found);
    RUN_TEST(test_rapl_fd_opens);
    RUN_TEST(test_rapl_energy_increases);
    RUN_TEST(test_msr_readable);
    RUN_TEST(test_uncore_msr_readable);
    return UNITY_END();
}
