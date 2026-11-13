/* demo_accel_driver.h: a small bare-metal style driver for the demo_accel block (brief 64A example).
 * It uses only the generated header (generated/demo_accel_regs.h), so the same source runs on the board (volatile
 * loads and stores at the block's base address) and in co-simulation (hwsw/tests/c_cosim_harness.c routes the
 * bus over a pipe to the RTL under cocotb). */
#ifndef DEMO_ACCEL_DRIVER_H
#define DEMO_ACCEL_DRIVER_H

#include <stdint.h>

/* Platform hook: wait until the block's interrupt line is high, at most timeout units (the board: a blocking read()
 * on the UIO device; the co-simulation: clocks). Returns 1 if the line was seen high, 0 on timeout. */
int demo_accel_platform_wait_irq(unsigned timeout);

int demo_accel_probe(uintptr_t base);                                  /* 0 if the ID matches */
void demo_accel_configure(uintptr_t base, unsigned mode, unsigned scale);
int demo_accel_run_job(uintptr_t base, int use_irq, unsigned timeout); /* 0 done, -1 timeout */

#endif
