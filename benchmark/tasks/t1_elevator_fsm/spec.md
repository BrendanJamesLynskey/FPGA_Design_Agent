# Four-floor lift controller

I want a model of a lift serving four floors (0 to 3) on the Nexys A7-100T.

- SW[3:0] are the call buttons, one per floor: flicking a switch up calls the lift to that floor. Leaving it up
  doesn't call again; it has to go down and up again.
- The lift takes a fixed time to travel one floor, and when it stops at a floor that was called its door stays
  open for a fixed time. It should behave like a real lift: keep going in the same direction while there are calls
  further on, and only then turn round. It starts at floor 0 with the door shut.
- LED[3:0] show which floor the lift is at (one LED lit) and LED[15] is lit while the door is open. Also show the
  outstanding calls on LED[7:4]. LED[14] is lit while the lift is moving between floors.
- CPU_RESETN resets everything.
- Over the test shell (USB-UART, 115200 baud) I can read the floor, the direction, the outstanding calls, what the
  lift is doing and how many floors it has travelled, and place calls. The design ID is "ELEV".

Test hooks: top module `t1_elevator_fsm_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `FLOOR_CYCLES` (clocks to travel one floor) and
`DOOR_CYCLES` (clocks the door stays open) as top-level parameters.
