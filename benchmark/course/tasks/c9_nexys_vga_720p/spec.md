# Colour bars on the Nexys A7 VGA connector at 1280 x 720

I want the Nexys A7-100T to put eight vertical colour bars on its VGA connector as a **1280 x 720 picture at 60 Hz**. (My capture dongle rejects 640 x 480, so it has to be 720p.)

- Inputs: the 100 MHz board clock `CLK100MHZ`, the centre button `BTNC` (a reset while pressed) and the switches `SW[1:0]` (the board's `SW` bus; the other switches are unused). Outputs: `VGA_R[3:0]`, `VGA_G[3:0]`, `VGA_B[3:0]`, `VGA_HS`, `VGA_VS`, and `LED[0]`, which lights when the video clock is stable. Use the board's own pin names.
- Timing: the CEA-861 1280 x 720 at 60 Hz timing: pixel clock 74.25 MHz, 1650 pixel clocks per line (1280 active, 110 front porch, 40 sync, 220 back porch) and 750 lines per frame (720 active, 5 front porch, 5 sync, 20 back porch). Both sync pulses are positive (idle low, high during the sync).
- Picture, when `SW[1:0]` = 00: eight bars of 160 pixels each, left to right white, yellow, cyan, green, magenta, red, blue, black, at full intensity (a lit colour channel is 4'b1111). Everywhere outside the 1280 x 720 active area the colour outputs are zero. What the other switch values show is up to you; I only test 00.
- The colour outputs and both sync outputs leave the chip aligned with each other: the first white pixel appears exactly 220 pixel clocks after the horizontal sync pulse ends, and the first picture line exactly 20 lines after the vertical sync pulse ends.
- While `BTNC` is pressed, or the video clock is not yet stable, the outputs show no picture (colours zero).
- The design must close timing at the pixel clock.
- I will watch the outputs for a frame in simulation and measure the line and frame periods, the sync widths and polarity, the position of the picture against the sync pulses, and the colours of the bars. (In my simulation the clock input is treated as the pixel clock; in the real design it is the 100 MHz board clock.)
- The test shell is on the USB-UART at 115200 baud, as for every board design; its window needs only one status register for this design. The design ID is "V720".

Test hooks: top module `c9_nexys_vga_720p_top`, ports named as in the board's master XDC, the test shell's `CLKS_PER_BIT`,
`TIMEOUT_CYCLES` and `BUILD_STAMP` parameters as top-level parameters, and a one-bit parameter `SIM_DIRECT_CLOCK`
(default 0): when 1 the `CLK100MHZ` input is used directly as the pixel clock (no clock generator in the design, the clock counts as stable).
There are no other time constants.
