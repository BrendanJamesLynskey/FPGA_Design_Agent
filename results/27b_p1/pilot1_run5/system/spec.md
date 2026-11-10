# Video pipeline with a median filter (pilot 1)

I want the Nexys A7-100T to show a test picture on its VGA connector at **1280 x 720, 60 Hz**, after it has gone
through a **3 x 3 median filter**, so that I can see the filter's effect on the capture dongle and check it from the
host.

- The picture comes from a 720p timing generator with a test pattern: eight vertical colour bars of 160 pixels (white,
  yellow, cyan, green, magenta, red, blue, black) by default. Timing is CEA-861 720p60: 74.25 MHz pixel clock, 1650
  clocks per line (1280 active, 110 front porch, 40 sync, 220 back porch), 750 lines (720 active, 5, 5, 20), both
  syncs positive.
- The median filter takes each pixel's 3 x 3 neighbourhood and outputs the median of each colour channel. The syncs
  and the picture leave the chip aligned with each other, as they would without the filter.
- Outside the active picture, and while the centre button `BTNC` is pressed or the pixel clock is not stable, the
  colour outputs are 0. `LED[0]` lights when the pixel clock is stable.
- The test shell is on the USB-UART at 115200 baud; design ID "VMED". Through it I choose the pattern and read a frame
  counter.
