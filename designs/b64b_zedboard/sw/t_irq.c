/* Interrupt-to-handler latency, bare metal: the PL stamps the counter when FIRE reaches it (T_FIRE) and when the handler's
 * first action, the write that clears the interrupt, reaches it (T_ACK). Latency = T_ACK - T_FIRE - DELAY - 1 fabric clocks
 * (DELAY = clocks the PL waits before raising the line; one more clock for the set); resolution 10 ns. The handler is the
 * C one in rt.c (assembly entry saves r0-r12, calls irq_c, which acknowledges the GIC and calls our hook). */
#include "bench.h"
static volatile uint32_t g_n;
static void hook(int id) {
    if (id == 61) wr32(LAT_BASE + LAT_IRQ_STATUS, 1);    /* first action: clear the interrupt in the PL (stamps T_ACK) */
    g_n++;
}
static void run(const char *name, int use_wfi, int caches_note) {
    const int N = 2000;
    for (int i = 0; i < N; i++) {
        uint32_t before = g_n;
        wr32(LAT_BASE + LAT_DELAY, 200);              /* 2 us: long enough for the core to be waiting */
        dsb();
        wr32(LAT_BASE + LAT_CMD, 1);
        if (use_wfi) { while (g_n == before) __asm__ volatile("wfi"); }
        else         { while (g_n == before) { } }
        uint32_t tf = rd32(LAT_BASE + LAT_T_FIRE), ta = rd32(LAT_BASE + LAT_T_ACK);
        g_s[i] = ta - tf - 200 - 1;
        if ((int32_t)g_s[i] < 0 || g_s[i] > 100000) g_s[i] = 100000;
        for (volatile int k = 0; k < 50; k++) { }
    }
    stat_report(name, caches_note, N, 10.0, "ns");
}
void app_main(void) {
    rt_init(1); g_uart_on = 0;
    ops_banner("irq_latency");
    xadc_alarms_setup();
    g_irq_hook = hook;
    gic_enable_spi(61, 1);
    wr32(LAT_BASE + LAT_IRQ_ENABLE, 1);
    irq_enable();
    run("irq_busy_loop_caches_on", 0, 1);
    run("irq_wfi_caches_on", 1, 1);
    xadc_report("end");
    uart_puts("DONE\n");
}
