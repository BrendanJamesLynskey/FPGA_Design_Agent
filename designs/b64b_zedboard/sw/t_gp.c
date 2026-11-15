/* GP-port latency: an uncached (strongly ordered) read of a PL register and a write that is waited for, timed with the
 * A9 global timer (333.33 MHz, 3.0 ns tick), 4096 samples each, and the same read measured in fabric clocks:
 * back-to-back reads of NOW differ by the read-to-read period in 10 ns fabric clocks (an independent timebase). */
#include "bench.h"
void app_main(void) {
    rt_init(1); g_uart_on = 0;
    ops_banner("gp_latency");
    xadc_alarms_setup();
    const double tick = 1e9 / GT_HZ;
    volatile uint32_t *now = (volatile uint32_t *)(LAT_BASE + LAT_NOW);
    volatile uint32_t *scr = (volatile uint32_t *)(LAT_BASE + 0x0FC);
    volatile uint32_t *idr = (volatile uint32_t *)(LAT_BASE + 0x000);
    uint32_t t0, t1; uint32_t v;
    /* timer overhead: two reads back to back, the same instruction sequence minus the PL access */
    for (int i = 0; i < MAXS; i++) { dsb(); t0 = gt_lo(); dsb(); t1 = gt_lo(); g_s[i] = t1 - t0; }
    stat_report("gt_overhead", 0, MAXS, tick, "ns");
    for (int i = 0; i < MAXS; i++) { dsb(); t0 = gt_lo(); v = *idr; dsb(); t1 = gt_lo(); g_s[i] = t1 - t0; }
    stat_report("gp_read_id", 0, MAXS, tick, "ns");
    for (int i = 0; i < MAXS; i++) { dsb(); t0 = gt_lo(); v = *now; dsb(); t1 = gt_lo(); g_s[i] = t1 - t0; (void)v; }
    stat_report("gp_read_now", 0, MAXS, tick, "ns");
    for (int i = 0; i < MAXS; i++) { dsb(); t0 = gt_lo(); *scr = i; dsb(); t1 = gt_lo(); g_s[i] = t1 - t0; }
    stat_report("gp_write_dsb", 0, MAXS, tick, "ns");
    for (int i = 0; i < MAXS; i++) { dsb(); t0 = gt_lo(); *scr = i; v = *scr; dsb(); t1 = gt_lo(); g_s[i] = t1 - t0; if (v != (uint32_t)i) { uart_puts("MISMATCH\n"); } }
    stat_report("gp_write_then_read", 0, MAXS, tick, "ns");
    /* read-to-read period in fabric clocks, from the PL counter itself */
    uint32_t a = *now;
    for (int i = 0; i < MAXS; i++) { uint32_t b = *now; g_s[i] = b - a; a = b; }
    stat_report("gp_read_period_fabric_clk", 0, MAXS, 10.0, "ns");
    /* the same through an L1-cached read of DDR for scale */
    volatile uint32_t *ddr = (volatile uint32_t *)IN_BUF; ddr[0] = 1;
    for (int i = 0; i < MAXS; i++) { dsb(); t0 = gt_lo(); v = ddr[0]; dsb(); t1 = gt_lo(); g_s[i] = t1 - t0; }
    stat_report("ddr_read_l1_hit", 0, MAXS, tick, "ns");
    /* PL counter monotonic and 100 MHz: PL ticks against the global timer over 1 ms */
    uint32_t p0 = *now; uint64_t g0 = gt_now(); while (gt_now() - g0 < 333333) { } uint32_t p1 = *now; uint64_t g1 = gt_now();
    uart_puts("CLK PL_ticks="); uart_dec(p1 - p0); uart_puts(" gt_ticks="); uart_dec(g1 - g0); uart_puts("\n");
    xadc_report("end");
    uart_puts("DONE\n");
}
