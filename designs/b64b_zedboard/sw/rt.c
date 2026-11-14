#include "rt.h"

abort_rec_t g_dabt, g_pabt;
volatile int g_dabt_skip = 4;
void (*g_irq_hook)(int id);

/* ---------------------------------------------------------------- UART1 (PS), 115200 8N1 from the 50 MHz UART clock */
/* Console log kept in DDR as well (read over JTAG: the host's UART device may not be readable): 16-byte header
 * {magic 'LOG1', write index, size, reserved} then the characters. */
#define LOG_BASE 0x03000000u
#define LOG_SIZE 0x00100000u
static void log_putc(char c) {
    volatile uint32_t *h = (volatile uint32_t *)LOG_BASE;
    if (h[0] != 0x31474F4Cu) { h[0] = 0x31474F4Cu; h[1] = 0; h[2] = LOG_SIZE - 16; }
    uint32_t i = h[1];
    if (i < LOG_SIZE - 16) { ((volatile char *)(LOG_BASE + 16))[i] = c; h[1] = i + 1; }
}
int g_uart_on = 1;
void uart_putc(char c) {
    log_putc(c);
    if (!g_uart_on) return;
    while (REG(UART1_BASE + 0x2C) & (1u << 4)) { }      /* TXFULL */
    REG(UART1_BASE + 0x30) = (uint32_t)c;
}
void uart_puts(const char *s) { while (*s) { if (*s == '\n') uart_putc('\r'); uart_putc(*s++); } }
void uart_hex(uint32_t v) { for (int i = 28; i >= 0; i -= 4) uart_putc("0123456789abcdef"[(v >> i) & 15]); }
void uart_dec(int64_t v) {
    char b[24]; int n = 0; uint64_t u = v < 0 ? (uint64_t)(-v) : (uint64_t)v;
    if (v < 0) uart_putc('-');
    do { b[n++] = '0' + (u % 10); u /= 10; } while (u);
    while (n) uart_putc(b[--n]);
}
static void uart_init(void) {
    REG(UART1_BASE + 0x00) = 0x28;      /* disable TX, RX */
    REG(UART1_BASE + 0x18) = 62;        /* BAUDGEN */
    REG(UART1_BASE + 0x34) = 6;         /* BAUDDIV: 50 MHz / (62 * 7) = 115207 baud */
    REG(UART1_BASE + 0x00) = 0x03;      /* reset TX and RX */
    REG(UART1_BASE + 0x04) = 0x20;      /* 8N1, normal */
    REG(UART1_BASE + 0x00) = 0x14;      /* enable TX and RX */
}

/* ---------------------------------------------------------------- global timer */
uint64_t gt_now(void) {
    uint32_t hi, lo, hi2;
    do { hi = REG(GTIMER + 4); lo = REG(GTIMER); hi2 = REG(GTIMER + 4); } while (hi != hi2);
    return ((uint64_t)hi << 32) | lo;
}

/* ---------------------------------------------------------------- caches */
#define L1_LINE 32u
void l1_clean_range(uint32_t a, uint32_t n) {
    for (uint32_t p = a & ~(L1_LINE - 1); p < a + n; p += L1_LINE) __asm__ volatile("mcr p15,0,%0,c7,c10,1" :: "r"(p) : "memory");
    dsb();
}
void l1_inv_range(uint32_t a, uint32_t n) {
    for (uint32_t p = a & ~(L1_LINE - 1); p < a + n; p += L1_LINE) __asm__ volatile("mcr p15,0,%0,c7,c6,1" :: "r"(p) : "memory");
    dsb();
}
void l1_clean_inv_range(uint32_t a, uint32_t n) {
    for (uint32_t p = a & ~(L1_LINE - 1); p < a + n; p += L1_LINE) __asm__ volatile("mcr p15,0,%0,c7,c14,1" :: "r"(p) : "memory");
    dsb();
}
/* PL310 (L2C-310): by-PA operations; each completes synchronously on the 'cache sync' (reg 0x730) */
static int g_l2_on;
static void l2_op(uint32_t reg, uint32_t a, uint32_t n) {
    if (!g_l2_on) return;
    for (uint32_t p = a & ~31u; p < a + n; p += 32) { REG(L2C_BASE + reg) = p; }
    REG(L2C_BASE + 0x730) = 0;
    dsb();
}
void cache_clean_range(uint32_t a, uint32_t n)     { l1_clean_range(a, n); l2_op(0x7B0, a, n); }
void cache_inv_range(uint32_t a, uint32_t n)       { l2_op(0x770, a, n); l1_inv_range(a, n); }
void cache_clean_inv_range(uint32_t a, uint32_t n) { l1_clean_inv_range(a, n); l2_op(0x7F0, a, n); }
void dcache_inv_all_l1(void) {
    uint32_t ccsidr; __asm__ volatile("mcr p15,2,%0,c0,c0,0" :: "r"(0));   /* L1 D */
    __asm__ volatile("mrc p15,1,%0,c0,c0,0" : "=r"(ccsidr));
    uint32_t sets = ((ccsidr >> 13) & 0x7FFF) + 1, ways = ((ccsidr >> 3) & 0x3FF) + 1;
    for (uint32_t w = 0; w < ways; w++) for (uint32_t s = 0; s < sets; s++) {
        uint32_t v = (w << 30) | (s << 5);
        __asm__ volatile("mcr p15,0,%0,c7,c6,2" :: "r"(v) : "memory");
    }
    dsb();
}
void dcache_flush_all(void) {                      /* clean and invalidate L1 by set/way (32 KB, 4 ways), then clean L2 by way */
    for (uint32_t w = 0; w < 4; w++) for (uint32_t s = 0; s < 256; s++) {
        uint32_t v = (w << 30) | (s << 5);
        __asm__ volatile("mcr p15,0,%0,c7,c14,2" :: "r"(v) : "memory");
    }
    dsb();
    if (g_l2_on) { REG(L2C_BASE + 0x7FC) = 0xFF; while (REG(L2C_BASE + 0x7FC) & 0xFF) { } REG(L2C_BASE + 0x730) = 0; dsb(); }
}

/* ---------------------------------------------------------------- MMU: 1 MB sections */
extern uint32_t __ttb[4096];
#define SEC_DDR_WBWA   0x15de6u    /* normal, inner+outer write-back write-allocate, shareable, AP=full, domain 15 */
#define SEC_DDR_NC     0x14de2u    /* normal, non-cacheable, shareable */
#define SEC_STRONG     0x00c02u    /* strongly ordered, AP=full, domain 0 */
static void mmu_setup(void) {
    for (uint32_t i = 0; i < 4096; i++) __ttb[i] = (i << 20) | SEC_STRONG;               /* everything strongly ordered */
    for (uint32_t i = 0; i < 512; i++) __ttb[i] = (i << 20) | SEC_DDR_WBWA;             /* DDR 0-512 MB cacheable */
    __ttb[0x30] = (0x30u << 20) | SEC_DDR_NC;      /* 0x03000000-0x030FFFFF: the console log, non-cacheable so JTAG reads see it */
    __ttb[0xFFF] = (0xFFFu << 20) | 0x04c0eu;                                            /* OCM high: normal WB (Xilinx value) */
}
void rt_init(int caches) {
    uart_init();
    mmu_setup();
    uint32_t zero = 0, ttb = (uint32_t)(uintptr_t)__ttb;
    __asm__ volatile("mcr p15,0,%0,c8,c7,0" :: "r"(zero));            /* invalidate TLB */
    __asm__ volatile("mcr p15,0,%0,c2,c0,2" :: "r"(zero));            /* TTBCR = 0 */
    __asm__ volatile("mcr p15,0,%0,c2,c0,0" :: "r"(ttb | 0x5B));      /* TTBR0: IRGN/RGN write-back write-allocate, shareable */
    __asm__ volatile("mcr p15,0,%0,c3,c0,0" :: "r"(0xFFFFFFFFu));     /* DACR: manager everywhere */
    __asm__ volatile("mcr p15,0,%0,c7,c5,0" :: "r"(zero));            /* invalidate I cache, branch predictor */
    __asm__ volatile("mcr p15,0,%0,c7,c5,6" :: "r"(zero));
    dcache_inv_all_l1();
    /* global timer on */
    REG(GTIMER + 0x08) = 0;  REG(GTIMER + 0x00) = 0; REG(GTIMER + 4) = 0; REG(GTIMER + 0x08) = 1;
    if (caches) {
        /* SCU: invalidate all tags, enable; ACTLR.SMP = 1 (needed for ACP coherency) */
        REG(SCU_BASE + 0x0C) = 0xFFFF;
        REG(SCU_BASE + 0x00) |= 1;
        uint32_t a; __asm__ volatile("mrc p15,0,%0,c1,c0,1" : "=r"(a)); a |= (1u << 6) | 1u;
        __asm__ volatile("mcr p15,0,%0,c1,c0,1" :: "r"(a));
        /* L2C-310: latencies as the Xilinx BSP uses for this part, invalidate all ways, enable */
        REG(L2C_BASE + 0x100) = 0;
        REG(L2C_BASE + 0x108) = 0x111; REG(L2C_BASE + 0x10C) = 0x121;
        REG(L2C_BASE + 0x104) = 0x72360000;
        REG(L2C_BASE + 0x77C) = 0xFFFF; while (REG(L2C_BASE + 0x77C)) { }
        REG(L2C_BASE + 0x730) = 0;
        REG(L2C_BASE + 0x100) = 1; g_l2_on = 1;
    }
    uint32_t sctlr; __asm__ volatile("mrc p15,0,%0,c1,c0,0" : "=r"(sctlr));
    sctlr |= 1u;                                       /* M */
    if (caches) sctlr |= (1u << 2) | (1u << 12) | (1u << 11);     /* C, I, Z */
    __asm__ volatile("mcr p15,0,%0,c1,c0,0" :: "r"(sctlr)); isb();
}

/* ---------------------------------------------------------------- aborts */
uint32_t dabt_c(uint32_t dfsr, uint32_t dfar, uint32_t lr, uint32_t spsr) {
    g_dabt.dfsr = dfsr; g_dabt.dfar = dfar; g_dabt.lr = lr; g_dabt.spsr = spsr; g_dabt.count++;
    return (uint32_t)g_dabt_skip;
}
void pabt_c(uint32_t ifsr, uint32_t ifar, uint32_t lr) { g_pabt.ifsr = ifsr; g_pabt.ifar = ifar; g_pabt.lr = lr; g_pabt.count++; for (;;) { } }
void async_abort_enable(void)  { __asm__ volatile("cpsie a" ::: "memory"); }
void async_abort_disable(void) { __asm__ volatile("cpsid a" ::: "memory"); }

/* ---------------------------------------------------------------- GIC */
void gic_enable_spi(int id, int level_high) {
    REG(GIC_DIST + 0x000) = 0;
    REG(GIC_CPU + 0x04) = 0xF0;                                         /* priority mask */
    uint32_t r = GIC_DIST + 0xC00 + 4 * (id / 16);                      /* ICDICFR: 2 bits per interrupt */
    uint32_t cfg = REG(r) & ~(3u << ((id % 16) * 2));
    cfg |= (level_high ? 0u : 2u) << ((id % 16) * 2);                  /* bit1 = edge; level-high is 0b01 on Zynq (1-N model reads) */
    REG(r) = cfg;
    REG(GIC_DIST + 0x800 + (id & ~3)) = 1u << (8 * (id & 3));           /* target CPU0 */
    REG(GIC_DIST + 0x100 + 4 * (id / 32)) = 1u << (id % 32);            /* set-enable */
    REG(GIC_CPU + 0x00) = 1;
    REG(GIC_DIST + 0x000) = 1;
}
void irq_c(void) {
    uint32_t ia = REG(GIC_CPU + 0x0C);
    uint32_t id = ia & 0x3FF;
    if (id < 1020 && g_irq_hook) g_irq_hook((int)id);
    REG(GIC_CPU + 0x10) = ia;
}
void irq_enable(void) { __asm__ volatile("cpsie i" ::: "memory"); }

/* ---------------------------------------------------------------- XADC via DEVCFG (UG585 XADC interface) */
#define XCFG   (DEVCFG_BASE + 0x100)
#define XSTS   (DEVCFG_BASE + 0x104)
#define XMSTS  (DEVCFG_BASE + 0x10C)
#define XCMD   (DEVCFG_BASE + 0x110)
#define XRD    (DEVCFG_BASE + 0x114)
#define XMCTL  (DEVCFG_BASE + 0x118)
void xadc_init(void) {
    REG(XMCTL) = 0x10;                  /* reset the FIFOs and the interface */
    REG(XMCTL) = 0;
    REG(XCFG) = 0x80000000u | (4u << 20) | (4u << 16) | (1u << 13) | (1u << 12) | (2u << 8) | 0x14u;
    REG(XSTS) = 0xFFFFFFFFu;
}
uint16_t xadc_read(int addr) {
    REG(XCMD) = 0x08000000u | ((uint32_t)addr << 16);
    REG(XCMD) = 0;                      /* NOP to push the read out */
    while (REG(XMSTS) & (1u << 8)) { }  /* RXEMPTY(?): wait for data (bit position verified on the board) */
    (void)REG(XRD);
    while (REG(XMSTS) & (1u << 8)) { }
    return (uint16_t)REG(XRD);
}
void xadc_write(int addr, uint16_t v) {
    REG(XCMD) = 0x04000000u | ((uint32_t)addr << 16) | v;
    while (REG(XMSTS) & (1u << 8)) { }
    (void)REG(XRD);                     /* every command, a write too, returns one word */
}
double xadc_temp_c(void) { return xadc_read(0x00) * 503.975 / 65536.0 - 273.15; }
double xadc_volts(int addr, double fs) { return xadc_read(addr) * fs / 65536.0; }

void rt_main(void) { app_main(); for (;;) { } }

/* libc stand-ins (the image links no C library); word-wise when aligned. -fno-tree-loop-distribute-patterns keeps GCC from
 * turning these loops back into calls to themselves. */
void *memset(void *d, int c, unsigned long n) { uint8_t *p = d; while (n--) *p++ = (uint8_t)c; return d; }
void *memcpy(void *d, const void *s, unsigned long n) {
    uint8_t *p = d; const uint8_t *q = s;
    if ((((uintptr_t)p | (uintptr_t)q) & 3) == 0) { uint32_t *pw = (uint32_t *)p; const uint32_t *qw = (const uint32_t *)q; while (n >= 4) { *pw++ = *qw++; n -= 4; } p = (uint8_t *)pw; q = (const uint8_t *)qw; }
    while (n--) *p++ = *q++;
    return d;
}
