# VGA test picture: a disc in a frame

I want a VGA picture at 640x480 and 60 Hz: a coloured disc in the middle of the screen, a white frame round the edge
and a black background.

- The standard 640x480 mode: 800 pixel times per line (640 visible, then front porch 16, sync 96 and back porch
  48) and 525 lines per frame (480 visible, front porch 10, sync 2, back porch 33), both sync pulses active low. The
  pixel rate is a quarter of the 100 MHz board clock, so each pixel lasts four clocks.
- The disc is centred in the visible area, with a radius of a quarter of the visible height. Its colour comes from the
  switches: SW[11:8] red, SW[7:4] green and SW[3:0] blue, four bits each.
- The frame is white and 4 pixels thick, drawn over everything else, and it follows the edge of the visible area.
- Outside the visible area the colour outputs are black. A new colour set on the switches takes effect from the next
  frame, so there is never a split-colour disc.
- LED[11:0] show the colour in use. Over the test shell (USB-UART, 115200 baud) I can read the colour in use and the
  number of frames drawn. The design ID is "VGAD".

Test hooks: top module `p_vga_disc_top`, ports named as in the board's master XDC, the test shell's `CLKS_PER_BIT`,
`TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `H_ACTIVE`, `H_FP`, `H_SYNC`, `H_BP`, `V_ACTIVE`, `V_FP`, `V_SYNC`
and `V_BP` (the line and frame structure in pixels and lines), `PIX_DIV` (clocks per pixel) and `BORDER` (the white
frame's thickness in pixels) as top-level parameters.
