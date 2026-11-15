/* The same interrupt latency with the MMU and caches off (the usual bare-metal "unoptimised" start-up) for contrast. */
#include "bench.h"
static volatile uint32_t g_n;
static void hook(int id) { if (id == 61) wr32(LAT_BASE + LAT_IRQ_STATUS, 1); g_n++; }
void app_main(void) {
    rt_init(0); g_uart_on = 0;
    uint32_t sctlr; __asm__ volatile("mrc p15,0,%0,c1,c0,0" : "=r"(sctlr)); sctlr &= ~1u;     /* MMU off too */
    __asm__ volatile("mcr p15,0,%0,c1,c0,0" :: "r"(sctlr)); isb();
    ops_banner("irq_latency_caches_off");
    g_irq_hook = hook; gic_enable_spi(61, 1); wr32(LAT_BASE + LAT_IRQ_ENABLE, 1); irq_enable();
    const int N = 2000;
    for (int i = 0; i < N; i++) {
        uint32_t before = g_n;
        wr32(LAT_BASE + LAT_DELAY, 200); dsb(); wr32(LAT_BASE + LAT_CMD, 1);
        while (g_n == before) { }
        uint32_t tf = rd32(LAT_BASE + LAT_T_FIRE), ta = rd32(LAT_BASE + LAT_T_ACK);
        g_s[i] = ta - tf - 200 - 1; if ((int32_t)g_s[i] < 0 || g_s[i] > 100000) g_s[i] = 100000;
        for (volatile int k = 0; k < 50; k++) { }
    }
    stat_report("irq_busy_loop_caches_off", 0, N, 10.0, "ns");
    xadc_report("end");
    uart_puts("DONE\n");
}
