/* stale_btb.c (brief 64A2): a custom instruction that the branch predictor predicts taken. The pinned BRV32P core
 * acts on a branch mispredict even while EX is stalled (brv32p_core.v, branch_mispredict_ex): with a custom
 * instruction that stalls EX (the EX style), the mispredict flushes the stalled instruction itself and redirects past
 * it, so its result is never written. A predicted-taken non-branch needs a stale BTB entry: here a taken branch is
 * trained at an address, then a custom instruction is written over it (fence.i refetches the code; the predictor keeps
 * its entry). main returns 0 only if the instruction's result is right. run_bench.py builds it with STALE_A, STALE_B
 * and STALE_EXPECT (crc32_word of the two, from ip_lib/crc32_step/model.py). */
#include <stdint.h>

static volatile uint32_t code[4] __attribute__((aligned(16), section(".data"))) = {0, 0, 0, 0};

typedef uint32_t (*fn_t)(uint32_t, uint32_t);

int main(void)
{
    fn_t f = (fn_t)(uintptr_t)code;
    code[0] = 0x00000463u;                 /* beq x0, x0, +8: always taken */
    code[1] = 0x00000013u;                 /* nop (skipped) */
    code[2] = 0x00008067u;                 /* ret */
    __asm__ volatile(".word 0x0000100f" ::: "memory");   /* fence.i (the -march has no Zifencei) */
    for (int i = 0; i < 8; i++)            /* train the direction counter and the BTB entry at code[0] */
        (void)f(1u, 2u);
    code[0] = 0x00b5055bu;                 /* crc32.w a0, a0, a1: custom-2, funct3 0, funct7 0 */
    code[1] = 0x00008067u;                 /* ret */
    code[2] = 0x00000013u;
    __asm__ volatile(".word 0x0000100f" ::: "memory");   /* fence.i (the -march has no Zifencei) */
    return f(STALE_A, STALE_B) == STALE_EXPECT ? 0 : 1;
}
