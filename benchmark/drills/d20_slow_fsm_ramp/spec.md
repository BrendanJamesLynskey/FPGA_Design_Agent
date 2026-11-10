# Slow ramp controller on one fast clock

I want a ramp controller on the Nexys A7-100T. A slow control state machine steps a level up to a top value and back
down to zero; a fast unit uses that level on every clock.

- **One clock only:** the board's 100 MHz clock. No MMCM or PLL, no divided or generated clock, no second clock
  domain. The controller is slow because it advances only on a **tick**, a clock enable that is 1 on exactly one clock
  in every 8, made by a counter on the same clock.
- **The controller**, on each tick: when idle and a start is pending, it starts ramping up (the pending start is
  used up). Ramping up, the level goes up by STEP but never above TOP; on the tick where it reaches TOP it turns
  round. Ramping down, the level goes down by STEP but never below 0; on the tick where it reaches 0 it goes idle.
- **The fast unit** keeps its own copy of the level, which it takes from the controller only on the tick. On every
  clock it adds its copy to a 32-bit sum, ACC. LED[15:8] show its copy of the level; LED[1:0] show the controller's
  state (0 idle, 1 up, 2 down); the other LEDs are off.
- **Timing constraints:** the controller's registers and the fast unit's copy of the level change only on the tick,
  so the paths between those registers have 8 clocks. Constrain exactly those paths as 8-clock paths, for setup and for
  hold, naming the registers the tick enables; every other path stays a normal one-clock path. Say in the constraint
  file why each exception is right.
- CPU_RESETN resets everything: idle, level 0, STEP 1, TOP 255, ACC 0, no start pending.
- Over the test shell (USB-UART, 115200 baud) I can set STEP (1 to 255; a write of 0 stores 1) and TOP (8 bits),
  start a ramp with a write to GO (ignored unless the controller is idle), read the state, read the fast unit's copy
  of the level, and read and clear ACC. The design ID is "RAMP".

Test hooks: top module `d20_slow_fsm_ramp_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
