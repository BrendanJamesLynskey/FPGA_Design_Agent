#include "bench.h"

int16_t g_coef[16];
uint32_t g_s[MAXS];

/* ---------------- DMA ---------------- */
void chain_init(int c) {
    uint32_t d = DMA_B[c];
    wr32(d + MM2S_CR, 4); wr32(d + S2MM_CR, 4);            /* soft reset (self-clearing) */
    while (rd32(d + MM2S_CR) & 4) { }
    wr32(d + MM2S_CR, 1); wr32(d + S2MM_CR, 1);            /* RS = 1, no interrupts */
}
uint32_t chain_job(int c, uint32_t in_addr, uint32_t in_len, uint32_t out_addr, uint32_t out_len) {
    uint32_t d = DMA_B[c], a = ACC_B[c];
    wr32(a + ACC_CMD, 1);                                   /* START */
    wr32(d + S2MM_DA, out_addr);
    wr32(d + S2MM_LEN, out_len);
    wr32(d + MM2S_SA, in_addr);
    wr32(d + MM2S_LEN, in_len);
    uint32_t sr;
    while (!((sr = rd32(d + S2MM_SR)) & (SR_IOC | SR_ERRS))) { }
    uint32_t e = sr & SR_ERRS;
    wr32(d + S2MM_SR, SR_IOC);
    /* the MM2S side finishes before S2MM; clear its IOC flag too */
    uint32_t t = 0; while (!(rd32(d + MM2S_SR) & (SR_IOC | SR_ERRS)) && ++t < 100000) { }
    wr32(d + MM2S_SR, SR_IOC);
    return e;
}
uint32_t acc_job_cycles(int c) { return rd32(ACC_B[c] + ACC_JOB_CYCLES); }

/* ---------------- CRC-32 ---------------- */
static uint32_t T[8][256];
void crc_init_tables(void) {
    for (uint32_t i = 0; i < 256; i++) { uint32_t c = i; for (int k = 0; k < 8; k++) c = (c >> 1) ^ ((c & 1) ? 0xEDB88320u : 0); T[0][i] = c; }
    for (uint32_t i = 0; i < 256; i++) for (int t = 1; t < 8; t++) T[t][i] = (T[t-1][i] >> 8) ^ T[0][T[t-1][i] & 0xFF];
}
uint32_t crc32_bytewise(const uint8_t *p, uint32_t n) {
    uint32_t c = 0xFFFFFFFFu;
    while (n--) c = T[0][(c ^ *p++) & 0xFF] ^ (c >> 8);
    return ~c;
}
uint32_t crc32_slice8(const uint8_t *p, uint32_t n) {
    uint32_t c = 0xFFFFFFFFu;
    while (n >= 8) {
        uint32_t a = c ^ *(const uint32_t *)p, b = *(const uint32_t *)(p + 4);
        c = T[7][a & 0xFF] ^ T[6][(a >> 8) & 0xFF] ^ T[5][(a >> 16) & 0xFF] ^ T[4][a >> 24]
          ^ T[3][b & 0xFF] ^ T[2][(b >> 8) & 0xFF] ^ T[1][(b >> 16) & 0xFF] ^ T[0][b >> 24];
        p += 8; n -= 8;
    }
    while (n--) c = T[0][(c ^ *p++) & 0xFF] ^ (c >> 8);
    return ~c;
}

/* ---------------- FIR: y[n] = sum_{k<16} h[k] x[n-k], x = low 16 bits (signed) of each input word, zero history ---------------- */
void fir16_sw(const uint32_t *in, int32_t *out, uint32_t n, const int16_t *h) {
    for (uint32_t i = 0; i < n; i++) {
        int32_t acc = 0;
        uint32_t kmax = i < 15 ? i : 15;
        for (uint32_t k = 0; k <= kmax; k++) acc += (int32_t)h[k] * (int16_t)in[i - k];
        out[i] = acc;
    }
}

/* ---------------- statistics ---------------- */
uint32_t xorshift(void) { static uint32_t s = 2463534242u; s ^= s << 13; s ^= s >> 17; s ^= s << 5; return s; }
static void sort_u32(uint32_t *a, uint32_t n) {            /* shell sort */
    for (uint32_t gap = n / 2; gap > 0; gap /= 2)
        for (uint32_t i = gap; i < n; i++) { uint32_t t = a[i], j = i; for (; j >= gap && a[j - gap] > t; j -= gap) a[j] = a[j - gap]; a[j] = t; }
}
static void pr_fix(double v) {                              /* print a double with 3 decimals, no libc */
    if (v < 0) { uart_putc('-'); v = -v; }
    uint64_t w = (uint64_t)v, f = (uint64_t)((v - (double)w) * 1000.0 + 0.5);
    if (f >= 1000) { w++; f -= 1000; }
    uart_dec((int64_t)w); uart_putc('.');
    uart_putc('0' + f / 100); uart_putc('0' + (f / 10) % 10); uart_putc('0' + f % 10);
}
/* "S <name> <size> n=<n> unit=<unit> min p50 p95 max mean"  (values in <unit>) and "B ..." 16 bins from min to max */
void stat_report(const char *name, uint32_t size, uint32_t n, double tick, const char *unit) {
    sort_u32(g_s, n);
    double sum = 0; for (uint32_t i = 0; i < n; i++) sum += g_s[i];
    uart_puts("S "); uart_puts(name); uart_putc(' '); uart_dec(size); uart_puts(" n="); uart_dec(n); uart_puts(" unit="); uart_puts(unit);
    uart_putc(' '); pr_fix(g_s[0] * tick); uart_putc(' '); pr_fix(g_s[n / 2] * tick); uart_putc(' '); pr_fix(g_s[(n * 95) / 100] * tick);
    uart_putc(' '); pr_fix(g_s[n - 1] * tick); uart_putc(' '); pr_fix(sum / n * tick); uart_puts("\n");
    uint32_t lo = g_s[0], hi = g_s[n - 1], w = (hi - lo) / 16 + 1; uint32_t bins[16] = {0};
    for (uint32_t i = 0; i < n; i++) bins[(g_s[i] - lo) / w]++;
    uart_puts("B "); uart_puts(name); uart_putc(' '); uart_dec(size); uart_puts(" lo="); pr_fix(lo * tick); uart_puts(" w="); pr_fix(w * tick);
    for (int i = 0; i < 16; i++) { uart_putc(' '); uart_dec(bins[i]); }
    uart_puts("\n");
}

/* ---------------- XADC readings: operating conditions ---------------- */
static void pr_v(double v) { pr_fix(v); }
void xadc_report(const char *tag) {
    uart_puts("XADC "); uart_puts(tag);
    uart_puts(" Tj_C="); pr_v(xadc_temp_c());
    uart_puts(" VCCINT="); pr_v(xadc_volts(0x01, 3.0));
    uart_puts(" VCCAUX="); pr_v(xadc_volts(0x02, 3.0));
    uart_puts(" VCCBRAM="); pr_v(xadc_volts(0x06, 3.0));
    uart_puts(" VCCPINT="); pr_v(xadc_volts(0x0D, 3.0));
    uart_puts(" VCCPAUX="); pr_v(xadc_volts(0x0E, 3.0));
    uart_puts(" VCCO_DDR="); pr_v(xadc_volts(0x0F, 3.0));
    uart_puts(" ALM_STS="); uart_hex(REG(DEVCFG_BASE + 0x104) & 0xFF); uart_puts("\n");
}
void ops_banner(const char *name) {
    uart_puts("BENCH "); uart_puts(name); uart_puts("\n");
    xadc_init();
    xadc_report("start");
}

/* Alarm thresholds at the recommended operating conditions of a -1 Zynq-7000 (DS187 Table 2: VCCINT/VCCPINT/VCCBRAM 0.95-1.05 V,
 * VCCAUX/VCCPAUX 1.71-1.89 V; VCCO_DDR 1.14-1.89 V, here tightened to the DDR3 range 1.425-1.575 V; commercial Tj 0-85 C), with
 * 20 mV added on each supply side (the XADC's supply accuracy is about 1 % of its 3 V full scale, UG480). The alarm outputs
 * latch in INT_STS between polls (cleared by writing 1). Temperature: upper alarm 85 C; over-temperature 90 C. */
static uint16_t vcode(double v) { return (uint16_t)(v / 3.0 * 65536.0); }
void xadc_alarms_setup(void) {
    xadc_write(0x50, (uint16_t)((85.0 + 273.15) / 503.975 * 65536.0));       /* temperature upper (alarm) */
    xadc_write(0x54, (uint16_t)((60.0 + 273.15) / 503.975 * 65536.0));       /* temperature lower: alarm clears below 60 C */
    xadc_write(0x53, (uint16_t)((90.0 + 273.15) / 503.975 * 65536.0));       /* over-temperature */
    xadc_write(0x57, (uint16_t)((70.0 + 273.15) / 503.975 * 65536.0));
    xadc_write(0x51, vcode(1.07)); xadc_write(0x55, vcode(0.93));            /* VCCINT */
    xadc_write(0x52, vcode(1.91)); xadc_write(0x56, vcode(1.69));            /* VCCAUX */
    xadc_write(0x58, vcode(1.07)); xadc_write(0x5C, vcode(0.93));            /* VCCBRAM */
    xadc_write(0x59, vcode(1.07)); xadc_write(0x5D, vcode(0.93));            /* VCCPINT */
    xadc_write(0x5A, vcode(1.91)); xadc_write(0x5E, vcode(1.69));            /* VCCPAUX */
    xadc_write(0x5B, vcode(1.595)); xadc_write(0x5F, vcode(1.405));          /* VCCO_DDR */
    REG(DEVCFG_BASE + 0x104) = 0xFFFFFFFFu;                                  /* clear INT_STS (latched alarms) */
}
