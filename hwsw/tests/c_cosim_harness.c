/* c_cosim_harness.c: runs the demo_accel C driver (hwsw/examples/demo_accel_driver.c) against the RTL in simulation.
 * Each bus access becomes a line on stdout ("R <hex addr>", "W <hex addr> <hex data>", "I <clocks>" to wait for the
 * interrupt); regmap_cocotb.py's c_driver_cosim test performs it on the AXI4-Lite bus and answers on stdin.
 * Build (the test does this): cc -std=c99 -Wall -Wextra -Werror -I hwsw/examples -I <generated> \
 *   hwsw/tests/c_cosim_harness.c -o c_cosim */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static uint32_t pipe_read32(uintptr_t addr);
static void pipe_write32(uintptr_t addr, uint32_t v);
#define DEMO_ACCEL_IO_READ32(addr) pipe_read32((uintptr_t)(addr))
#define DEMO_ACCEL_IO_WRITE32(addr, v) pipe_write32((uintptr_t)(addr), (uint32_t)(v))
#include "demo_accel_driver.c"                      /* the driver itself, one translation unit with the pipe bus */

static unsigned bad_resp;

static uint32_t pipe_read32(uintptr_t addr)
{
    unsigned v, resp;
    printf("R %lx\n", (unsigned long)addr);
    fflush(stdout);
    if (scanf("%x %u", &v, &resp) != 2)
        exit(3);
    bad_resp += resp != 0;
    return v;
}

static void pipe_write32(uintptr_t addr, uint32_t v)
{
    unsigned resp;
    printf("W %lx %lx\n", (unsigned long)addr, (unsigned long)v);
    fflush(stdout);
    if (scanf("%u", &resp) != 1)
        exit(3);
    bad_resp += resp != 0;
}

int demo_accel_platform_wait_irq(unsigned timeout)
{
    int seen;
    printf("I %u\n", timeout);
    fflush(stdout);
    if (scanf("%d", &seen) != 1)
        exit(3);
    return seen;
}

static int finish(int rc, const char *msg)
{
    char bye[8];
    printf("DONE %d %s\n", rc, msg);
    fflush(stdout);
    if (scanf("%7s", bye) != 1)
        return 3;
    return rc;
}

int main(void)
{
    const uintptr_t base = 0;                          /* the window's base as the bench sees it */
    if (demo_accel_probe(base))
        return finish(1, "ID mismatch");
    demo_accel_configure(base, 5u, 0x180u);
    uint32_t ctrl = demo_accel_read(base, DEMO_ACCEL_CTRL_OFFSET);
    if (DEMO_ACCEL_GET(CTRL, MODE, ctrl) != 5u || DEMO_ACCEL_GET(CTRL, SCALE, ctrl) != 0x180u ||
        !DEMO_ACCEL_GET(CTRL, ENABLE, ctrl))
        return finish(2, "CTRL readback");
    for (int i = 0; i < 3; i++)                        /* polled completion */
        if (demo_accel_run_job(base, 0, 200))
            return finish(4, "polled job timed out");
    demo_accel_write(base, DEMO_ACCEL_IRQ_ENABLE_OFFSET, DEMO_ACCEL_PUT(IRQ_ENABLE, DONE, 1));
    for (int i = 0; i < 3; i++)                        /* interrupt-driven completion */
        if (demo_accel_run_job(base, 1, 400))
            return finish(5, "interrupt job timed out");
    uint32_t st = demo_accel_read(base, DEMO_ACCEL_STATUS_OFFSET);
    if (DEMO_ACCEL_GET(STATUS, LEVEL, st) != 6u || DEMO_ACCEL_GET(STATUS, BUSY, st))
        return finish(6, "STATUS after six jobs");
    demo_accel_write(base, DEMO_ACCEL_SCRATCH_OFFSET, 0x64A0C0DEu);
    if (demo_accel_read(base, DEMO_ACCEL_SCRATCH_OFFSET) != 0x64A0C0DEu)
        return finish(7, "SCRATCH");
    if (demo_accel_read(base, 0x0F8u) != 0u)           /* an unmapped word reads 0 (and answers SLVERR) */
        return finish(8, "unmapped read");
    if (bad_resp != 1u)                                /* exactly the one deliberate unmapped access was refused */
        return finish(9, "bus errors");
    return finish(0, "ok");
}
