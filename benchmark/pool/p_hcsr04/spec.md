# Ultrasonic range finder

I have an HC-SR04-style ultrasonic ranger on Pmod JD: JD1 is its trigger input and JD2 its echo output.

- To measure, the FPGA sends a trigger pulse. The ranger then sends a burst of ultrasound and raises the echo line for a
  time that is proportional to the distance. The distance in centimetres is the echo time divided by a fixed number of
  clocks per centimetre, rounded down.
- A measurement is started by a write from the test shell. If the echo never starts the ping counts as a time-out; an
  echo that is too long to be a real range counts as out of range.
- A single reading can be wrong, so the distance I want is the median of the last three good readings (with fewer than
  three readings, the median of those there are; of two, the smaller).
- The trigger must not go out again while the previous echo is still high.
- LED[7:0] show the filtered distance (255 at most) and LED[15] shows that a measurement is in progress.
- Over the test shell (USB-UART, 115200 baud) I can start a measurement and read the raw and filtered distances, the
  echo width, the counts of good readings, time-outs and out-of-range echoes, and whether it is busy. The design ID
  is "HCSR".

Test hooks: top module `p_hcsr04_top`, ports named as in the board's master XDC, the test shell's `CLKS_PER_BIT`,
`TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `TRIG_CYCLES` (trigger pulse width in clocks), `CLKS_PER_CM`,
`ECHO_WAIT` (clocks to wait for the echo to start after the trigger) and `MAX_ECHO` (the longest echo that counts as a
reading, in clocks) as top-level parameters.
