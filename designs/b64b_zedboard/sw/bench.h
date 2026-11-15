/* Shared parts of the ZedBoard benchmarks (brief 64B): addresses, DMA/accelerator driver, software kernels, statistics. */
#ifndef BENCH_H
#define BENCH_H
#include "rt.h"
#include "gen_regs.h"     /* offsets generated from the register maps */

#define IN_BUF   0x04000000u
#define OUT_BUF  0x04400000u
#define REF_BUF  0x04800000u
#define SRC_BUF  0x04C00000u     /* pristine input data, copied to IN_BUF before a timed job (so the lines are dirty in the caches) */

static inline uint32_t rd32(uint32_t a) { return REG(a); }
static inline void wr32(uint32_t a, uint32_t v) { REG(a) = v; }

/* ---------------- AXI DMA (simple mode) + accelerator, chain 0 = HP0, chain 1 = ACP ---------------- */
static const uint32_t DMA_B[2] = {PL_BASE + 0x40000u, PL_BASE + 0x60000u};
static const uint32_t ACC_B[2] = {PL_BASE + 0x50000u, PL_BASE + 0x70000u};
#define MM2S_CR 0x00
#define MM2S_SR 0x04
#define MM2S_SA 0x18
#define MM2S_LEN 0x28
#define S2MM_CR 0x30
#define S2MM_SR 0x34
#define S2MM_DA 0x48
#define S2MM_LEN 0x58
#define SR_IDLE (1u << 1)
#define SR_IOC  (1u << 12)
#define SR_ERRS ((1u << 4) | (1u << 5) | (1u << 6) | (1u << 14) | (1u << 15) | (1u << 13))

void chain_init(int c);
/* one job: accel START, S2MM then MM2S started, poll S2MM IOC. Returns 0 or an error status word. */
uint32_t chain_job(int c, uint32_t in_addr, uint32_t in_len, uint32_t out_addr, uint32_t out_len);
uint32_t acc_job_cycles(int c);

/* ---------------- software kernels ---------------- */
void crc_init_tables(void);
uint32_t crc32_bytewise(const uint8_t *p, uint32_t n);
uint32_t crc32_slice8(const uint8_t *p, uint32_t n);      /* n multiple of 4; same result as bytewise */
void fir16_sw(const uint32_t *in, int32_t *out, uint32_t n, const int16_t *h);
extern int16_t g_coef[16];

/* ---------------- statistics ---------------- */
#define MAXS 4096
extern uint32_t g_s[MAXS];
void stat_report(const char *name, uint32_t size, uint32_t n, double tick_ns, const char *unit);   /* min/p50/p95/max/mean + a 16-bin histogram */
uint32_t xorshift(void);
void xadc_report(const char *tag);
void xadc_alarms_setup(void);
void ops_banner(const char *name);
#endif
