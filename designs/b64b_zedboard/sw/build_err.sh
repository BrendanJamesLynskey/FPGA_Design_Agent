#!/bin/bash
# build_err.sh: one ELF per bus-error access (e_<target><write><attr>.elf): target 0..4 = hole_okay, hole_slverr, hole_split,
# outside_decerr, outside_decerr2; write 0 read / 1 write; attr 0 strongly ordered / 1 device / 2 normal non-cacheable.
cd "$(dirname "$0")"
CC=/opt/Xilinx/2026.1/Vitis/gnu/aarch32/lin/gcc-arm-none-eabi/bin/arm-none-eabi-gcc
for s in 0 1 2 3 4; do for w in 0 1; do for a in 0 1 2; do
  $CC -O2 -mcpu=cortex-a9 -marm -mfloat-abi=soft -ffreestanding -fno-builtin -fno-tree-loop-distribute-patterns -nostdlib -Wall -Wextra -Wno-unused-parameter -g \
    -DSEL=$s -DSELW=$w -DSELA=$a crt0.S rt.c bench.c t_err.c -o e_$s$w$a.elf -T link.ld -Wl,--gc-sections -Wl,--no-warn-rwx-segments -lgcc || exit 1
done; done; done
