# A bouncing 16 x 16 sprite on VGA

I want one small sprite on a VGA monitor from the Nexys A7-100T, at the ordinary 640 x 480, 60 Hz mode (25 MHz
pixel rate made from the 100 MHz clock with an enable, no clocking wizard; standard timing and sync polarity for
that mode).

- The sprite is 16 x 16 pixels, one bit per pixel: 1 draws the sprite colour, 0 lets the background show
  through. I load its 16 rows from the test shell.
- I can set its position (X, Y of its top-left corner), the sprite colour and the background colour (12-bit RGB),
  and switch it off.
- Optional bounce mode: once per frame it moves one pixel horizontally and one vertically, and turns round when it
  reaches an edge of the screen, like the old screen savers.
- It must behave sensibly if I put it partly or completely off the screen.
- Outside the visible area the colour outputs are black. A frame counter would help me check it runs.
- Design ID "SPRT".

Test hooks: top module `t2_vga_sprite_top`, ports named as in the board's master XDC (`VGA_R`, `VGA_G`, `VGA_B`,
`VGA_HS`, `VGA_VS`, the USB-UART pins, `CLK100MHZ`, `CPU_RESETN`), the test shell's `CLKS_PER_BIT`,
`TIMEOUT_CYCLES` and `BUILD_STAMP` parameters as top-level parameters. The video timing is fixed (no parameters).
