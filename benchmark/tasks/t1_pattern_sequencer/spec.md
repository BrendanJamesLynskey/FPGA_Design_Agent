# LED pattern sequencer

I want the Nexys A7-100T's sixteen LEDs to play back a little light show that I program over the test shell.

- The show is up to sixteen steps. Each step is a 16-bit LED pattern and how long to show it, in milliseconds, up
  to a couple of hundred. I choose how many steps are in use.
- It can loop for ever or play once and stop on the last step. I start and stop it over the shell; starting
  always begins at the first step.
- BTNC pauses and resumes the show (it bounces, so debounce it).
- When I change a step's pattern while the show runs, I want to see the change straight away.
- CPU_RESETN resets everything.
- Over the test shell (USB-UART, 115200 baud) I can write the steps, set the length and the mode, start and stop,
  and read which step is playing, whether it is running, paused or finished, and how many times it has gone round.
  The design ID is "PSEQ".

Test hooks: top module `t1_pattern_sequencer_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `DEBOUNCE_CYCLES` (debounce time in clocks) and
`TICK_CYCLES` (clocks per millisecond, the unit of step durations) as top-level parameters.
