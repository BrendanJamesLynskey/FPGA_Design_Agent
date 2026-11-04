# t1_gray_stepper: reviewer notes

- **Twin:** none (no textbook or Digilent demo is a Gray stepper). No trap.
- **Left out of spec.md on purpose:** the Gray code variant (reflected binary, GRAY = BIN xor BIN >> 1); exactly how
  the automatic timing is phased (prescaler restarts on CTRL/RATE writes; steps exactly RATE * TICK_CYCLES apart);
  that RATE = 0 keeps AUTO set; the reset rate (250); the register map; press/auto collisions; that BIN writes are
  not steps.
- **What is checked:** a monitor records every LED[9:0] change; each must be one bit and the model's next code.
  `test_every_transition_one_bit` drives all 1024 transitions in each direction at RATE = 1 (REQ-01's simulation
  half). REQ-01/02 also ask for formal proof: the reference has `ifdef FORMAL` assertions (one-bit step, GRAY =
  f(BIN)); they are not run by the bench (no formal tool in check_task).
- **Review:** LED[9:0] must be a register (the spec says so) so a design deriving the LEDs combinationally still
  passes simulation; only formal/hardware would see a glitch. The `wrap_at_1000` mutant models a decimal-wrap habit.
- **v1.2 (2026-11-04):** `test_press_during_auto` added (a press while AUTO = 1 gives one extra step and leaves the
  automatic grid at exactly RATE * TICK_CYCLES clocks); mutant `press_restarts_prescaler` (a press restarts the prescaler)
  is killed by it. The formal half of REQ-01/02 is still not scored by the bench: a score here covers simulation only.
