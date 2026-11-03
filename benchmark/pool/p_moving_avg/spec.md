# Moving average filter

I want to try a small smoothing filter on numbers I send from the PC, such as readings from a noisy sensor.

- Each time I send a sample (12 bits, unsigned) it goes into a window that holds the six most recent samples, and the
  filter output is their average, rounded down.
- Until six samples have arrived the average is taken over the samples that have arrived, not over six.
- Spikes should not drag the output around: once the window is full, a new sample that is further from the current
  average than a limit I can set is pulled in to that limit before it goes into the window.
- LED[11:0] show the average.
- Over the test shell (USB-UART, 115200 baud) I can send samples, read the average, the window sum and how many
  samples are in the window, set the limit, and empty the window. The design ID is "MAVG".

Test hooks: top module `p_moving_avg_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
