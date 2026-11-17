/* Minimal bare-metal runtime for the Zynq-7000 Cortex-A9 core 0 (ZedBoard): UART1 console, MMU, caches, SCU/L2,
 * global timer, GIC and the PS-side XADC interface. Written against the register descriptions in UG585. */
#ifndef RT_H
#define RT_H
#include <stdint.h>
#define REG(a) (*(volatile uint32_t *)(uintptr_t)(a))

/* PS addresses (UG585 register map) */
#define UART1_BASE   0xE0001000u
#define SLCR_BASE    0xF8000000u
#define SCU_BASE     0xF8F00000u
#define GIC_CPU      0xF8F00100u
#define GTIMER       0xF8F00200u
#define GIC_DIST     0xF8F01000u
#define L2C_BASE     0xF8F02000u
#define DEVCFG_BASE  0xF8007000u
/* PL window used by the design (M_AXI_GP0 is 0x40000000-0x7FFFFFFF) */
#define PL_BASE      0x40000000u

/* The A9 global timer runs at PERIPHCLK = CPU clock / 2 = 333.33 MHz (CPU 666.67 MHz) */
#define GT_HZ 333333333.0

void rt_init(int caches);               /* MMU (DDR cacheable, the rest strongly ordered), SCU, L1 and L2 */
extern int g_uart_on;                   /* 0: console text goes only to the DDR log (benchmarks) */
void uart_puts(const char *s);
void uart_putc(char c);
void uart_hex(uint32_t v);
void uart_dec(int64_t v);
static inline uint32_t gt_lo(void) { return REG(GTIMER + 0x00); }
uint64_t gt_now(void);
void l1_clean_range(uint32_t a, uint32_t n);
void l1_clean_inv_range(uint32_t a, uint32_t n);
void l1_inv_range(uint32_t a, uint32_t n);
void cache_clean_range(uint32_t a, uint32_t n);      /* L1 then L2 (PL310) clean, by address */
void cache_inv_range(uint32_t a, uint32_t n);        /* L2 then L1 invalidate (n and a must be line-aligned) */
void cache_clean_inv_range(uint32_t a, uint32_t n);
void dcache_flush_all(void);
void dcache_inv_all_l1(void);
static inline void dsb(void) { __asm__ volatile("dsb" ::: "memory"); }
static inline void isb(void) { __asm__ volatile("isb" ::: "memory"); }
void *memcpy(void *d, const void *s, unsigned long n);
void *memset(void *d, int c, unsigned long n);
void rt_main(void);
void app_main(void);

/* Aborts: the handlers record the last abort here. */
typedef struct { volatile uint32_t count, dfsr, dfar, lr, spsr, ifsr, ifar, pcount; } abort_rec_t;
extern abort_rec_t g_dabt, g_pabt;
extern volatile int g_dabt_skip;           /* bytes added to lr on return (4 skips the faulting instruction) */
/* GIC */
void gic_enable_spi(int id, int level_high);
extern void (*g_irq_hook)(int id);
void irq_enable(void);
void async_abort_enable(void);
void async_abort_disable(void);
/* XADC through the PS interface */
void xadc_init(void);
uint16_t xadc_read(int addr);           /* DRP register read (16-bit) */
void xadc_write(int addr, uint16_t v);
double xadc_temp_c(void);
double xadc_volts(int addr, double fullscale);
#endif
