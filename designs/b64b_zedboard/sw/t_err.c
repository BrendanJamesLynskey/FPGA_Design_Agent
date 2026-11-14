/* Bus-error behaviour of the Cortex-A9 on AXI error responses from the PL (brief 64B item 5), bare metal.
 * For each target (a hole inside a generated block set to okay, slverr or split; an address outside every block, answered
 * DECERR by axil_xbar) and each access (read, write) and each mapping of the PL window (strongly ordered, device, normal
 * non-cacheable), N attempts. Per attempt: was a data abort taken (right after the access and its barrier, or only later),
 * DFSR and DFAR as the handler read them, whether the aborted instruction was the access itself (precise) or a later one
 * (imprecise), and for reads the value the load returned. Async aborts are unmasked (CPSR.A = 0) throughout. Then the error-
 * capture registers of the block are read (ERR_ADDR 0xFF8, ERR_STATUS 0xFFC). */
#include "bench.h"

#define MAXD 6
typedef struct { uint32_t dfsr; uint32_t n; } dfsr_cnt_t;

static const uint32_t SEC_SO = 0x00c02u, SEC_DEV = 0x00c06u, SEC_NC = 0x14de2u;
void __ttb_set(uint32_t idx, uint32_t attr);
static void map_pl(uint32_t attr) {
    __ttb_set(0x400, attr);
}
extern uint32_t __ttb[4096];
void __ttb_set(uint32_t idx, uint32_t attr) {
    __ttb[idx] = (idx << 20) | attr;
    dsb();
    __asm__ volatile("mcr p15,0,%0,c8,c7,0" :: "r"(0) : "memory");     /* invalidate TLB */
    dsb(); isb();
}

static volatile uint32_t g_ld_val;
static uint32_t do_read(uint32_t addr, uint32_t *insn_addr) {
    uint32_t v = 0xDEADBEEFu, ia;
    __asm__ volatile("adr %1, 1f\n 1: ldr %0, [%2]\n dsb\n isb" : "+r"(v), "=&r"(ia) : "r"(addr) : "memory");
    *insn_addr = ia;
    return v;
}
static void do_write(uint32_t addr, uint32_t val, uint32_t *insn_addr) {
    uint32_t ia;
    __asm__ volatile("adr %0, 1f\n 1: str %1, [%2]\n dsb\n isb" : "=&r"(ia) : "r"(val), "r"(addr) : "memory");
    *insn_addr = ia;
}

static void clear_capture(uint32_t base) { wr32(base + 0xFFC, 1); dsb(); }

static void experiment(const char *name, uint32_t addr, uint32_t cap_base, int is_write, uint32_t attr, const char *attrname, int N) {
    map_pl(attr);
    dfsr_cnt_t tab[MAXD]; int nt = 0;
    uint32_t aborts_immediate = 0, aborts_late = 0, precise = 0, dfar_ok = 0, wnr = 0, ext = 0, none = 0;
    uint32_t lastval = 0, first_dfar = 0, first_lr_delta = 0; int have_first = 0;
    if (cap_base) clear_capture(cap_base);
    for (int i = 0; i < N; i++) {
        uint32_t c0 = g_dabt.count, ia = 0, v = 0;
        if (is_write) do_write(addr, 0xA5A50000u + i, &ia); else v = do_read(addr, &ia);
        uint32_t c1 = g_dabt.count;
        for (volatile int k = 0; k < 400; k++) { }              /* about 1-2 us: lets a late abort arrive */
        dsb(); isb();
        uint32_t c2 = g_dabt.count;
        if (!is_write) lastval = v;
        if (c1 != c0) aborts_immediate++;
        else if (c2 != c0) aborts_late++;
        else none++;
        if (c2 != c0) {
            uint32_t f = g_dabt.dfsr; int j;
            for (j = 0; j < nt; j++) if (tab[j].dfsr == f) break;
            if (j == nt && nt < MAXD) { tab[nt].dfsr = f; tab[nt].n = 0; nt++; }
            if (j < MAXD) tab[j].n++;
            if (g_dabt.lr == ia) precise++;                      /* the aborted instruction is the access */
            if (g_dabt.dfar == addr) dfar_ok++;
            if (f & (1u << 11)) wnr++;
            if (f & (1u << 12)) ext++;
            if (!have_first) { have_first = 1; first_dfar = g_dabt.dfar; first_lr_delta = g_dabt.lr - ia; }
        }
    }
    uart_puts("E "); uart_puts(name); uart_putc(' '); uart_puts(is_write ? "W" : "R"); uart_putc(' '); uart_puts(attrname);
    uart_puts(" addr="); uart_hex(addr); uart_puts(" N="); uart_dec(N);
    uart_puts(" abort_at_barrier="); uart_dec(aborts_immediate); uart_puts(" abort_late="); uart_dec(aborts_late); uart_puts(" no_abort="); uart_dec(none);
    uart_puts(" precise="); uart_dec(precise); uart_puts(" dfar_eq_addr="); uart_dec(dfar_ok);
    uart_puts(" WnR="); uart_dec(wnr); uart_puts(" ExT="); uart_dec(ext);
    for (int j = 0; j < nt; j++) { uart_puts(" DFSR="); uart_hex(tab[j].dfsr); uart_putc('x'); uart_dec(tab[j].n); }
    if (have_first) { uart_puts(" first_dfar="); uart_hex(first_dfar); uart_puts(" lr_minus_insn="); uart_dec((int32_t)first_lr_delta); }
    if (!is_write) { uart_puts(" last_value="); uart_hex(lastval); }
    if (cap_base) {
        /* the capture reads may themselves abort (they are mapped registers: they must not) */
        uint32_t ea = rd32(cap_base + 0xFF8), es = rd32(cap_base + 0xFFC);
        uart_puts(" ERR_ADDR="); uart_hex(ea); uart_puts(" ERR_STATUS="); uart_hex(es);
    }
    uart_puts("\n");
}

void app_main(void) {
    rt_init(1); g_uart_on = 0;
    ops_banner("bus_errors");
    xadc_alarms_setup();
    async_abort_enable();
    const int N = 200;
    static const struct { const char *n; uint32_t base; } blk[3] = {{"okay", PL_BASE + 0x10000u}, {"slverr", PL_BASE + 0x20000u}, {"split", PL_BASE + 0x30000u}};
    static const struct { const char *n; uint32_t a; } att[3] = {{"SO", SEC_SO}, {"DEV", SEC_DEV}, {"NC", SEC_NC}};
    uart_puts("NOTE ID reads first, to show the blocks answer\n");
    for (int b = 0; b < 3; b++) {
        map_pl(SEC_SO);
        uart_puts("ID "); uart_puts(blk[b].n); uart_putc(' '); uart_hex(rd32(blk[b].base + 0x000)); uart_puts("\n");
    }
    for (int a = 0; a < 3; a++) {
        for (int w = 0; w < 2; w++) {
            for (int b = 0; b < 3; b++) {
                char nm[24]; const char *p = "hole_"; int k = 0;
                while (*p) nm[k++] = *p++; p = blk[b].n; while (*p) nm[k++] = *p++; nm[k] = 0;
                experiment(nm, blk[b].base + 0x100, blk[b].base, w, att[a].a, att[a].n, N);
            }
            experiment("outside_decerr", PL_BASE + 0x1000u, 0, w, att[a].a, att[a].n, N);          /* between windows 0 and 1 */
            experiment("outside_decerr2", PL_BASE + 0x80000u, 0, w, att[a].a, att[a].n, N);        /* above the last window */
        }
    }
    map_pl(SEC_SO);
    xadc_report("end");
    uart_puts("DONE\n");
}
