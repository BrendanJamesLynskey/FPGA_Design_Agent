# Capture an external ADC on the board clock

I want to read an external 8-bit ADC module on Pmod JA of the Nexys A7-100T.

- **The ADC:** its conversion clock is the board's 100 MHz oscillator, which also drives CLK100MHZ (the board fans the
  one oscillator out to both; the two clock traces are matched). It drives its 8 data bits D[7:0] on JA: D[3:0] on JA1
  to JA4, D[7:4] on JA7 to JA10, new data after every rising edge of that clock.
- **Data-sheet excerpt (the ADC):** clock-to-data-out tCO is 1.0 ns minimum and 5.0 ns maximum.
- **The board:** the data traces from the ADC to the FPGA add 0.5 ns.
- **The oscillator:** its data sheet gives a period jitter of 50 ps (peak-to-peak).
- **Capture:** take a sample on every rising edge of CLK100MHZ, in input flip-flops in the FPGA's I/O blocks.
- **The fast unit:** LAST is the latest sample; MIN and MAX are the smallest and largest samples since the last clear
  (or reset). LED[7:0] show LAST; the other LEDs are off.
- **Timing constraints:** constrain the ADC inputs from the data sheet for setup and for hold, and say in the
  constraint file how each number is derived. Tell the timing analysis about the oscillator's jitter. I also want the
  implementation tools to aim for 0.3 ns more setup margin on every clock than the real requirement, but the timing
  sign-off must be against the real requirement, without that margin.
- CPU_RESETN resets everything: LAST 0, and MIN and MAX as a CLEAR does.
- Over the test shell (USB-UART, 115200 baud) I can read LAST, MIN and MAX, and write CLEAR (any data), which sets MIN
  to 255 and MAX to 0. The design ID is "ADC8".

Test hooks: top module `d20_adc_capture_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
