/* Cortex-A9 start-up: vectors, stacks, MMU/cache set-up is done in C (rt.c). */
    .section .vectors, "ax"
    .arm
    .global _start
_start:
    ldr pc, =reset_h
    ldr pc, =undef_h
    ldr pc, =svc_h
    ldr pc, =pabt_h
    ldr pc, =dabt_h
    nop
    ldr pc, =irq_h
    ldr pc, =fiq_h
    .ltorg

    .text
reset_h:
    cpsid aif, #0x13                 @ supervisor, interrupts and aborts masked
    ldr r0, =__stack_top
    @ stacks: abort mode and irq mode get 4 KB each below the supervisor stack
    cps #0x17
    sub sp, r0, #0x2000
    cps #0x12
    sub sp, r0, #0x3000
    cps #0x1B
    sub sp, r0, #0x4000
    cps #0x13
    mov sp, r0
    @ VBAR = start of this image (the vectors are first in .text)
    ldr r1, =_start
    mcr p15, 0, r1, c12, c0, 0
    @ clear bss
    ldr r1, =__bss_start
    ldr r2, =__bss_end
    mov r3, #0
1:  cmp r1, r2
    strlo r3, [r1], #4
    blo 1b
    @ SCTLR: clear V (low vectors off), keep MMU/caches as they are (rt_init sets them)
    mrc p15, 0, r1, c1, c0, 0
    bic r1, r1, #(1<<13)
    mcr p15, 0, r1, c1, c0, 0
    bl rt_main
2:  wfi
    b 2b

undef_h:
    b undef_c_tramp
svc_h:
    b svc_h
fiq_h:
    b fiq_h

/* Data abort: save lr and spsr, call C with DFSR/DFAR read there; return by the C-chosen offset. */
dabt_h:
    sub lr, lr, #8                   @ lr = address of the faulting (precise) or an interrupted (imprecise) instruction
    stmfd sp!, {r0-r12, lr}
    mrc p15, 0, r0, c5, c0, 0        @ DFSR
    mrc p15, 0, r1, c6, c0, 0        @ DFAR
    mov r2, lr
    mrs r3, spsr
    bl dabt_c                        @ returns the number of bytes to add to lr (4: skip the faulting instruction, 0: retry)
    add lr, lr, r0
    str lr, [sp, #(13*4)]
    ldmfd sp!, {r0-r12, pc}^
pabt_h:
    sub lr, lr, #4
    stmfd sp!, {r0-r12, lr}
    mrc p15, 0, r0, c5, c0, 1        @ IFSR
    mrc p15, 0, r1, c6, c0, 2        @ IFAR
    mov r2, lr
    bl pabt_c
    ldmfd sp!, {r0-r12, pc}^
undef_c_tramp:
    b undef_c_tramp
irq_h:
    sub lr, lr, #4
    stmfd sp!, {r0-r12, lr}
    bl irq_c
    ldmfd sp!, {r0-r12, pc}^
    .ltorg
