# t1_elevator_fsm: reviewer notes

- **Twin:** none (no textbook analogue). No trap; `test_scan_keeps_direction` is the key directed test (from floor
  1 going up, calls for 0 and 3: SCAN serves 3 first, a nearest-first controller 0).
- **Left out of spec.md on purpose:** the exact decision rule and its order (own floor, then ahead, then turn); what
  a call for the floor whose door is open does (ignored); a call for the idle floor (opens without moving); that
  passing floors with calls stop on the way; that a switch already up after reset calls once; LED[14]; W1S for shell
  calls; the register map; the direction after reset (up).
- **How it is checked:** a clocked model (model.py) runs beside the RTL; pin events (depart, arrive, open, close)
  must match in order and floor, and every interval not containing idle time must be exact. Calls are placed away
  from decision clocks so a few clocks' difference in call latency cannot change the order.
- **Review:** the model's call latency is SW_LAT = 2 clocks in its own time base; only order and non-idle intervals
  are compared, so this constant is not imposed on the agent's design.
