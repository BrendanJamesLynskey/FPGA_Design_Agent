# Bare-metal build for the Cortex-A9: AMD's arm-none-eabi GCC from the Vitis 2026.1 install (no BSP; rt.c is the runtime).
CC := /opt/Xilinx/2026.1/Vitis/gnu/aarch32/lin/gcc-arm-none-eabi/bin/arm-none-eabi-gcc
CFLAGS := -O2 -mcpu=cortex-a9 -marm -mfloat-abi=soft -ffreestanding -fno-builtin -fno-tree-loop-distribute-patterns -nostdlib -Wall -Wextra -Wno-unused-parameter -g
LDFLAGS := -T link.ld -nostdlib -Wl,--gc-sections -Wl,--no-warn-rwx-segments
COMMON := crt0.S rt.c rt.h link.ld
hello.elf: hello.c $(COMMON)
	$(CC) $(CFLAGS) crt0.S rt.c hello.c -o $@ $(LDFLAGS) -lgcc
t_%.elf: t_%.c bench.c bench.h gen_regs.h $(COMMON)
	$(CC) $(CFLAGS) crt0.S rt.c bench.c $< -o $@ $(LDFLAGS) -lgcc
clean:
	rm -f *.elf
