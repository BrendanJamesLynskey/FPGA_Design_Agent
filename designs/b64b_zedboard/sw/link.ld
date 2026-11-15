/* Bare-metal image for the ZedBoard's Cortex-A9 core 0: loaded into DDR over JTAG (no FSBL, no SD, no flash). */
ENTRY(_start)
MEMORY { DDR (rwx) : ORIGIN = 0x00100000, LENGTH = 0x07F00000 }
SECTIONS {
  .text : { KEEP(*(.vectors)) *(.text*) *(.rodata*) } > DDR
  .data : { *(.data*) } > DDR
  .bss (NOLOAD) : { __bss_start = .; *(.bss*) *(COMMON) __bss_end = .; } > DDR
  . = ALIGN(16384);
  __ttb = .;               /* 16 KB first-level translation table, 16 KB aligned */
  . += 16384;
  . = ALIGN(4096);
  __stack_bottom = .;
  . += 0x40000;
  __stack_top = .;
  /* buffers for the DMA tests start at 0x04000000 (set in the C code), well above the image and stacks */
}
