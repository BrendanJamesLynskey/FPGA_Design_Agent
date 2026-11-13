/* demo_accel_driver.c: see demo_accel_driver.h. Written against the generated header only. */
#include "demo_accel_driver.h"
#include "demo_accel_regs.h"

#define RD(reg) demo_accel_read(base, DEMO_ACCEL_##reg##_OFFSET)
#define WR(reg, v) demo_accel_write(base, DEMO_ACCEL_##reg##_OFFSET, (v))

int demo_accel_probe(uintptr_t base)
{
    uint32_t id = RD(ID);
    if (DEMO_ACCEL_GET(ID, MAGIC, id) != DEMO_ACCEL_ID_MAGIC_RESET)
        return -1;
    if (DEMO_ACCEL_GET(ID, VERSION, id) >> 8 != DEMO_ACCEL_ID_VERSION_RESET >> 8)
        return -2;                                     /* a different major version of the register map */
    return 0;
}

void demo_accel_configure(uintptr_t base, unsigned mode, unsigned scale)
{
    /* read-modify-write that keeps the RW bits only: CTRL also holds the W1C bit OVERFLOW, and writing back a 1
     * read from it would clear an event nobody has handled yet */
    uint32_t v = RD(CTRL) & DEMO_ACCEL_CTRL_RW_MASK;
    v &= ~(DEMO_ACCEL_CTRL_MODE_MASK | DEMO_ACCEL_CTRL_SCALE_MASK);
    v |= DEMO_ACCEL_PUT(CTRL, MODE, mode) | DEMO_ACCEL_PUT(CTRL, SCALE, scale) | DEMO_ACCEL_PUT(CTRL, ENABLE, 1);
    WR(CTRL, v);
}

int demo_accel_run_job(uintptr_t base, int use_irq, unsigned timeout)
{
    WR(CMD, DEMO_ACCEL_PUT(CMD, START, 1));
    if (use_irq) {
        if (!demo_accel_platform_wait_irq(timeout))
            return -1;
        if (!DEMO_ACCEL_GET(IRQ_STATUS, DONE, RD(IRQ_STATUS)))
            return -1;                                 /* the line was high for another cause */
    } else {
        unsigned n = 0;
        while (!DEMO_ACCEL_GET(IRQ_STATUS, DONE, RD(IRQ_STATUS)))
            if (++n > timeout)
                return -1;
    }
    WR(IRQ_STATUS, DEMO_ACCEL_PUT(IRQ_STATUS, DONE, 1)); /* W1C: clear only DONE */
    return 0;
}
