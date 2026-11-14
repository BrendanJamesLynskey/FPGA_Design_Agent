/* Offload benchmark shared by t_crc.c and t_fir.c: software on the A9 against the PL accelerator reached through an AXI DMA on
 * the HP0 port (cache maintenance by software) or on the ACP (coherent, none), over a range of sizes. Per size and per path:
 * reps timed calls with the global timer (3.0 ns tick); the fabric's own JOB_CYCLES for the offloaded runs.
 * Before every timed call the CPU copies the pristine input into the input buffer, so the input is dirty in the caches, as it
 * would be when the CPU has just produced it. The timed region of an offload call is: cache maintenance, the DMA job, and the
 * CPU reading the result (the whole output for the FIR). Results are checked against the software result on every rep. */
#ifndef ACC_BENCH_H
#define ACC_BENCH_H
#include "bench.h"

static uint32_t g_s2[MAXS];
static uint32_t reps_for(uint32_t bytes) {
    if (bytes <= 1024) return 1024;
    if (bytes <= 4096) return 512;
    if (bytes <= 16384) return 256;
    if (bytes <= 65536) return 96;
    if (bytes <= 262144) return 32;
    return 12;
}
static void stat_second(const char *name, uint32_t size, uint32_t n, double tick, const char *unit) {
    for (uint32_t i = 0; i < n; i++) g_s[i] = g_s2[i];
    stat_report(name, size, n, tick, unit);
}
static void fill_src(uint32_t bytes) {
    uint32_t *p = (uint32_t *)SRC_BUF;
    for (uint32_t i = 0; i < bytes / 4; i++) p[i] = xorshift();
    cache_clean_range(SRC_BUF, bytes);
}
static void stage_input(uint32_t bytes) { memcpy((void *)IN_BUF, (const void *)SRC_BUF, bytes); }   /* leaves IN_BUF dirty in the caches */

/* mode 0 = CRC-32 (bytes = packet length; output 4 bytes), mode 1 = FIR (bytes = 4 * samples; output = bytes) */
static void run_sizes(int mode, const uint32_t *sizes, int nsizes) {
    const double tick = 1e9 / GT_HZ;
    crc_init_tables();
    chain_init(0); chain_init(1);
    for (int i = 0; i < 16; i++) { g_coef[i] = (int16_t)(((int)(xorshift() & 0x3FF)) - 512); }       /* 11-bit signed, fits the 12-bit registers */
    for (int c = 0; c < 2; c++) { wr32(ACC_B[c] + ACC_CTRL, mode); for (int i = 0; i < 16; i++) wr32(ACC_B[c] + ACC_COEF(i), (uint32_t)g_coef[i] & 0xFFF); }
    uint32_t bad_total = 0;
    for (int si = 0; si < nsizes; si++) {
        uint32_t bytes = sizes[si], words = bytes / 4, reps = reps_for(bytes);
        uint32_t out_bytes = mode ? bytes : 4;
        fill_src(bytes);
        stage_input(bytes);
        uint32_t ref_crc = 0;
        if (mode) fir16_sw((const uint32_t *)SRC_BUF, (int32_t *)REF_BUF, words, g_coef); else ref_crc = crc32_slice8((const uint8_t *)SRC_BUF, bytes);
        uint32_t t0, t1, sink = 0, bad = 0;
        /* software */
        if (!mode) {
            for (uint32_t r = 0; r < reps; r++) { stage_input(bytes); dsb(); t0 = gt_lo(); uint32_t c = crc32_bytewise((const uint8_t *)IN_BUF, bytes); t1 = gt_lo(); g_s[r] = t1 - t0; if (c != ref_crc) bad++; sink += c; }
            stat_report("sw_crc_bytewise", bytes, reps, tick, "ns");
            for (uint32_t r = 0; r < reps; r++) { stage_input(bytes); dsb(); t0 = gt_lo(); uint32_t c = crc32_slice8((const uint8_t *)IN_BUF, bytes); t1 = gt_lo(); g_s[r] = t1 - t0; if (c != ref_crc) bad++; sink += c; }
            stat_report("sw_crc_slice8", bytes, reps, tick, "ns");
        } else {
            for (uint32_t r = 0; r < reps; r++) {
                stage_input(bytes); dsb(); t0 = gt_lo(); fir16_sw((const uint32_t *)IN_BUF, (int32_t *)OUT_BUF, words, g_coef); t1 = gt_lo(); g_s[r] = t1 - t0;
                if (r == 0) { const int32_t *o = (const int32_t *)OUT_BUF, *q = (const int32_t *)REF_BUF; for (uint32_t i = 0; i < words; i++) if (o[i] != q[i]) bad++; }
            }
            stat_report("sw_fir16", bytes, reps, tick, "ns");
        }
        /* HP0 with software cache maintenance, then ACP */
        for (int path = 0; path < 2; path++) {
            for (uint32_t r = 0; r < reps; r++) {
                stage_input(bytes);
                memset((void *)OUT_BUF, 0, out_bytes < 64 ? 64 : 0);   /* the CRC result slot holds a known value before the job */
                if (path == 0) cache_clean_inv_range(OUT_BUF, out_bytes < 64 ? 64 : 32);   /* no dirty line of the result slot can be written back over the DMA's data */
                dsb(); t0 = gt_lo();
                if (path == 0) cache_clean_range(IN_BUF, bytes);
                uint32_t e = chain_job(path, IN_BUF, bytes, OUT_BUF, out_bytes);
                if (path == 0) cache_inv_range(OUT_BUF, out_bytes);
                uint32_t acc = 0;
                if (mode) { const uint32_t *o = (const uint32_t *)OUT_BUF; for (uint32_t i = 0; i < words; i++) acc += o[i]; } else acc = *(volatile uint32_t *)OUT_BUF;
                t1 = gt_lo();
                g_s[r] = t1 - t0; g_s2[r] = acc_job_cycles(path);
                sink += acc;
                if (e) bad += 1000;
                if (!mode) { if (acc != ref_crc) bad++; }
                else if (r < 2 || r == reps - 1) {                       /* compare the whole output on the first two and the last rep */
                    cache_inv_range(OUT_BUF, out_bytes);
                    const int32_t *o = (const int32_t *)OUT_BUF, *q = (const int32_t *)REF_BUF; for (uint32_t i = 0; i < words; i++) if (o[i] != q[i]) bad++;
                    cache_inv_range(OUT_BUF, out_bytes);
                }
            }
            stat_report(path == 0 ? (mode ? "hp_fir16" : "hp_crc") : (mode ? "acp_fir16" : "acp_crc"), bytes, reps, tick, "ns");
            stat_second(path == 0 ? "hp_fabric_job_clk" : "acp_fabric_job_clk", bytes, reps, 10.0, "ns");
        }
        uart_puts("CHK size="); uart_dec(bytes); uart_puts(" bad="); uart_dec(bad); uart_puts(" sink="); uart_hex(sink); uart_puts("\n");
        bad_total += bad;
        xadc_report("size");
    }
    uart_puts("TOTAL_BAD "); uart_dec(bad_total); uart_puts("\n");
}
#endif
