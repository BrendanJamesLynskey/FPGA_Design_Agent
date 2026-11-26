Module name: `fifo16`

A 16-entry, 8-bit synchronous FIFO with sticky error flags (the core of dev task t1_sync_fifo_regs, without the shell registers).

Ports (names exact; one clock `clk`; reset `rst_n` active low, synchronous):
- inputs: `clk`, `rst_n`, `push` (1), `push_data` (8), `pop` (1), `clear_err` (1)
- outputs: `head` (8), `count` (5), `empty` (1), `full` (1), `overflow_err` (1), `underflow_err` (1)

Behaviour (all outputs are functions of the registers after the clock edge just taken, not of the current inputs):
- After reset the FIFO is empty and both error flags are 0.
- `head` is the oldest stored byte, or 0 when the FIFO is empty. `count` is the number of stored bytes (0..16). `empty` is 1 when count is 0, `full` when count is 16.
- In a clock where `push` is 1, `push_data` is stored at the tail, unless the FIFO was full at the start of that clock, in which case the byte is lost and `overflow_err` is set (even if `pop` is 1 in the same clock).
- In a clock where `pop` is 1, the head is removed, unless the FIFO was empty at the start of that clock, in which case nothing is removed and `underflow_err` is set (even if `push` is 1 in the same clock; the pushed byte is still stored).
- Push and pop in the same clock on a FIFO that is neither empty nor full: both happen, the count is unchanged.
- `overflow_err` and `underflow_err` are sticky: they stay 1 until `clear_err` is 1 in a clock, which clears both, except that an error caused in that same clock stays set.
