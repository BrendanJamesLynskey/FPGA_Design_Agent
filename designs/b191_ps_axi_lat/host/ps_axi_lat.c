/* ps_axi_lat.c: measures the Cortex-A53 to programmable-logic AXI access latency against rtl/axi_lat_probe.sv (brief 191, board row B-R8).
 *
 * Runs on the KR260's Linux (Ubuntu) as root, after the probe's PL image is loaded. It maps the probe's 4 KiB register window (from /dev/mem at a physical address, or from a UIO
 * device node) and times 32-bit accesses to it with the processor's generic timer (CNTVCT_EL0, frequency read from CNTFRQ_EL0) and with the fabric's own clock counter in the probe.
 * No flash, no configuration memory and nothing outside the 4 KiB window is touched. Output: one JSON object on stdout; messages on stderr.
 *
 *   ps_axi_lat --base 0xA0000000 [--dev /dev/mem] [--n 200000] [--runs 5] [--cpu 2] [--expect-build 0xB1910001] [--label fpd]
 *   ps_axi_lat --dev /dev/uio0 ...                (the offset is then 0)
 *   cross-build on the PC:  aarch64-linux-gnu-gcc -O2 -static -o ps_axi_lat ps_axi_lat.c        (the ARM build needs nothing installed on the board)
 *   self-test of the arithmetic on the PC (a software stand-in for the registers, no board):  gcc -O2 -DMOCK -o ps_axi_lat_mock ps_axi_lat.c && ./ps_axi_lat_mock
 *
 * What is measured (each over --n observations, --runs times; times in nanoseconds; a percentile is quoted only when the sample holds at least 100 observations beyond it):
 *   read_cpu     one 32-bit read of CNT: the timer before and after the load (isb, mrs, ldr, a dependency on the data, isb, mrs); the timer's tick (cntfrq) is the resolution
 *   read_fab     the difference of two consecutive CNT values, in fabric clocks (clk_hz from the probe): the time between two read requests as the fabric saw them,
 *                for reads that follow each other with the loop's overhead and nothing else
 *   write_cpu    one 32-bit write to TRIG followed by dsb sy (the write response has come back when dsb completes), timed by the timer
 *   write_fab    the differences of the logged write clocks of n_log back-to-back TRIG writes with a dsb sy after each: the time between write requests as the fabric saw them
 *   write_burst  the same with no barrier between the writes: how fast the processor can issue posted writes (differences of the logged clocks)
 *   rw_cpu       a write to SCRATCH then a read of SCRATCH, timed by the timer (the read waits for the write: the device is strongly ordered)
 *   integrity    --n random words written to SCRATCH and read back
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define R_ID 0x000
#define R_BUILD 0x004
#define R_CLK 0x008
#define R_SCRATCH 0x00C
#define R_CNT 0x010
#define R_WRTS 0x014
#define R_WRN 0x018
#define R_LOGN 0x01C
#define R_TRIG 0x020
#define R_CTRL 0x024
#define R_BAD 0x028
#define R_LOG 0x400
#define LOG_DEPTH 256

#ifndef MOCK
static volatile uint32_t *regs;
#endif

#ifdef MOCK
/* a stand-in for the registers: CNT counts at 100 MHz of the monotonic clock, TRIG logs it; reads cost a few hundred ns of loop overhead, which is what the numbers show */
static uint32_t m_scratch, m_logn, m_wrn, m_log[LOG_DEPTH];
static uint64_t now_ns(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return (uint64_t)t.tv_sec * 1000000000ull + (uint64_t)t.tv_nsec; }
static uint32_t rd(uint32_t off) {
    switch (off) {
    case R_ID: return 0x50534C54; case R_BUILD: return 0xB1910001; case R_CLK: return 100000000; case R_SCRATCH: return m_scratch;
    case R_CNT: return (uint32_t)(now_ns() / 10); case R_LOGN: return m_logn; case R_WRN: return m_wrn; case R_BAD: return 0;
    default: return (off >= R_LOG && off < R_LOG + 4 * LOG_DEPTH) ? m_log[(off - R_LOG) / 4] : 0;
    }
}
static void wr(uint32_t off, uint32_t v) {
    m_wrn++;
    if (off == R_SCRATCH) m_scratch = v;
    else if (off == R_TRIG && m_logn < LOG_DEPTH) m_log[m_logn++] = (uint32_t)(now_ns() / 10);
    else if (off == R_CTRL && (v & 1)) { m_logn = 0; m_wrn = 0; }
}
static inline uint64_t ticks(void) { return now_ns(); }
static uint64_t tick_hz(void) { return 1000000000ull; }
static inline void barrier(void) { __sync_synchronize(); }
#else
static inline uint32_t rd(uint32_t off) { return regs[off / 4]; }
static inline void wr(uint32_t off, uint32_t v) { regs[off / 4] = v; }
static inline uint64_t ticks(void) { uint64_t t; __asm__ volatile("isb\n\tmrs %0, cntvct_el0" : "=r"(t)::"memory"); return t; }
static uint64_t tick_hz(void) { uint64_t f; __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(f)); return f; }
static inline void barrier(void) { __asm__ volatile("dsb sy" ::: "memory"); }
#endif

static int cmp_u32(const void *a, const void *b) { uint32_t x = *(const uint32_t *)a, y = *(const uint32_t *)b; return x < y ? -1 : x > y; }

/* statistics of n unsigned samples (sorted in place); `unit` is the value of one count in ns */
static void stats(const char *name, uint32_t *s, size_t n, double unit, int last) {
    qsort(s, n, sizeof s[0], cmp_u32);
    double sum = 0;
    for (size_t i = 0; i < n; i++) sum += s[i];
    printf("    \"%s\": {\"n\": %zu, \"unit_ns\": %.3f, \"min_ns\": %.1f, \"p50_ns\": %.1f, \"mean_ns\": %.1f", name, n, unit, s[0] * unit, s[n / 2] * unit, sum / n * unit);
    if (n >= 10000) printf(", \"p99_ns\": %.1f", s[(size_t)(n * 0.99)] * unit);          /* >= 100 observations beyond it */
    if (n >= 100000) printf(", \"p999_ns\": %.1f", s[(size_t)(n * 0.999)] * unit);
    printf(", \"max_ns\": %.1f}%s\n", s[n - 1] * unit, last ? "" : ",");
}

int main(int argc, char **argv) {
    const char *dev = "/dev/mem", *label = "probe";
    uint64_t base = 0;
    size_t n = 200000;
    int runs = 5, cpu = -1;
    long expect_build = -1;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--base") && i + 1 < argc) base = strtoull(argv[++i], 0, 0);
        else if (!strcmp(argv[i], "--dev") && i + 1 < argc) dev = argv[++i];
        else if (!strcmp(argv[i], "--n") && i + 1 < argc) n = strtoull(argv[++i], 0, 0);
        else if (!strcmp(argv[i], "--runs") && i + 1 < argc) runs = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--cpu") && i + 1 < argc) cpu = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--expect-build") && i + 1 < argc) expect_build = (long)strtoull(argv[++i], 0, 0);
        else if (!strcmp(argv[i], "--label") && i + 1 < argc) label = argv[++i];
        else { fprintf(stderr, "usage: %s --base 0xADDR [--dev /dev/mem|/dev/uioN] [--n N] [--runs R] [--cpu C] [--expect-build 0xSTAMP] [--label NAME]\n", argv[0]); return 2; }
    }
    if (n < 1000) n = 1000;
#ifndef MOCK
    if (cpu >= 0) {
        cpu_set_t set; CPU_ZERO(&set); CPU_SET(cpu, &set);
        if (sched_setaffinity(0, sizeof set, &set)) fprintf(stderr, "warning: could not pin to cpu %d: %s\n", cpu, strerror(errno));
    }
    mlockall(MCL_CURRENT | MCL_FUTURE);
    int fd = open(dev, O_RDWR | O_SYNC);                   /* O_SYNC: the mapping is Device memory: every access reaches the bus, in order */
    if (fd < 0) { perror(dev); return 1; }
    void *p = mmap(0, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, strcmp(dev, "/dev/mem") ? 0 : (off_t)base);
    if (p == MAP_FAILED) { perror("mmap"); return 1; }
    regs = (volatile uint32_t *)p;
#else
    (void)dev; (void)base; (void)cpu;
#endif
    if (rd(R_ID) != 0x50534C54) { fprintf(stderr, "ID register reads 0x%08x, not 0x50534C54: wrong address or the PL image is not loaded\n", rd(R_ID)); return 1; }
    uint32_t build = rd(R_BUILD), clk_hz = rd(R_CLK);
    if (expect_build >= 0 && build != (uint32_t)expect_build) { fprintf(stderr, "build stamp 0x%08x, expected 0x%08lx\n", build, expect_build); return 1; }
    uint64_t hz = tick_hz();
    double tick_ns = 1e9 / (double)hz, fab_ns = 1e9 / (double)clk_hz;
    uint32_t *s = malloc(n * sizeof *s);
    if (!s) return 1;
    int bad_integrity = 0;
    volatile uint32_t sink = 0;
    printf("{\n  \"label\": \"%s\", \"build\": \"0x%08x\", \"clk_hz\": %u, \"timer_hz\": %" PRIu64 ", \"timer_tick_ns\": %.3f, \"n\": %zu, \"runs\": [\n", label, build, clk_hz, hz, tick_ns, n);
    for (int run = 0; run < runs; run++) {
        printf("   {\n");
        wr(R_CTRL, 1);
        barrier();
        /* integrity */
        uint32_t x = 0x12345678u + (uint32_t)run;
        for (size_t i = 0; i < 20000; i++) { x = x * 1664525u + 1013904223u; wr(R_SCRATCH, x); if (rd(R_SCRATCH) != x) bad_integrity++; }
        /* read_cpu */
        for (size_t i = 0; i < n; i++) { uint64_t t0 = ticks(); uint32_t v = rd(R_CNT); sink += v; uint64_t t1 = ticks(); s[i] = (uint32_t)(t1 - t0); }
        stats("read_cpu", s, n, tick_ns, 0);
        /* read_fab: differences of consecutive CNT values (mod 2^32) */
        uint32_t prev = rd(R_CNT);
        for (size_t i = 0; i < n; i++) { uint32_t v = rd(R_CNT); s[i] = v - prev; prev = v; }
        stats("read_fab", s, n, fab_ns, 0);
        /* write_cpu: str + dsb sy */
        for (size_t i = 0; i < n; i++) { uint64_t t0 = ticks(); wr(R_SCRATCH, (uint32_t)i); barrier(); uint64_t t1 = ticks(); s[i] = (uint32_t)(t1 - t0); }
        stats("write_cpu", s, n, tick_ns, 0);
        /* rw_cpu: write then read back */
        for (size_t i = 0; i < n; i++) { uint64_t t0 = ticks(); wr(R_SCRATCH, (uint32_t)i); uint32_t v = rd(R_SCRATCH); sink += v; uint64_t t1 = ticks(); s[i] = (uint32_t)(t1 - t0); }
        stats("rw_cpu", s, n, tick_ns, 0);
        /* write_fab and write_burst: the probe logs the clock of each TRIG write; LOG_DEPTH - 1 writes per batch, repeated until n differences are in s */
        for (int mode = 0; mode < 2; mode++) {
            size_t k = 0;
            while (k < n) {
                wr(R_CTRL, 1);
                barrier();
                for (int i = 0; i < LOG_DEPTH; i++) { wr(R_TRIG, 0); if (mode == 0) barrier(); }
                barrier();
                uint32_t cnt = rd(R_LOGN), last = rd(R_LOG);
                for (uint32_t i = 1; i < cnt && k < n; i++) { uint32_t v = rd(R_LOG + 4 * i); s[k++] = v - last; last = v; }
            }
            stats(mode == 0 ? "write_fab" : "write_burst", s, n, fab_ns, mode == 1);
        }
        printf("   }%s\n", run + 1 < runs ? "," : "");
    }
    printf("  ], \"integrity_mismatches\": %d, \"bad_accesses\": %u, \"sink\": %u\n}\n", bad_integrity, rd(R_BAD), (unsigned)sink);
    free(s);
    return bad_integrity ? 1 : 0;
}
