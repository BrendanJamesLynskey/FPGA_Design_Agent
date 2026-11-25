Module name: `bcd_updown`

A four-digit decimal up/down counter with selectable step (the core of dev task t1_bcd_updown, without the debouncer, display or shell).

Ports (names exact; one clock `clk`; reset `rst_n` active low, synchronous):
- inputs: `clk`, `rst_n`, `up` (1), `down` (1), `step_sel` (2 bits)
- outputs: `bcd` (16 bits, four BCD digits, the thousands digit in bits 15:12), `wraps` (8 bits)

Behaviour: the count is 0 and `wraps` is 0 after reset. In a clock where `up` is 1 and `down` is 0, the count increases by the step; where `down` is 1 and `up` is 0, it decreases by the step; with both or neither nothing changes. The step is chosen by `step_sel`: 0 gives 1, 1 gives 2, 2 gives 5, 3 gives 10. The count runs 0..9999 and wraps modulo 10000 at both ends (9998 + 5 gives 3; 2 - 5 gives 9997). Every clock in which the count wraps round (up past 9999, or down below 0) adds 1 to `wraps`, an 8-bit counter that itself wraps from 255 to 0. `bcd` and `wraps` show the state as updated by the clock edge just taken (functions of registers, not of the current inputs).
