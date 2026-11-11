# Burst sequencer that answers in the same clock

I want a burst sequencer on the Nexys A7-100T that talks to an external bus partner over two Pmods. The partner reacts in the same clock as the state table, so the outputs must not be late.

- **The partner** is a bus partner on Pmod JA. Its signals are inputs, each sampled on every rising edge of CLK100MHZ:
  `cmd_valid` JA1, `gnt` JA2, `ack` JA3, `nack` JA4, `rsp_ready` JA7.
- **The controller** (one clock, CLK100MHZ) is a sequencer with these states: IDLE, LOAD, REQ, ADDR, DATA, TURN, WACK, RETRY,
  RESP, ERR and COOL. It moves on the rising edge after the condition holds:
  - IDLE: `cmd_valid` high gives LOAD. LOAD always gives REQ.
  - REQ: `gnt` high gives ADDR (until then it waits). ADDR always gives DATA.
  - DATA lasts exactly 4 clocks (four beats), then TURN (one clock), then WACK.
  - WACK waits up to 8 clocks: `ack` gives RESP; otherwise `nack` gives RETRY; otherwise, if none of the 8 clocks had either, ERR
    (`ack` wins over `nack` when both are high). RETRY (one clock) gives REQ.
  - RESP and ERR wait for `rsp_ready` high, then COOL, which lasts exactly 3 clocks and gives IDLE.
- **The outputs** are on Pmod JB, decoded from the state: `req` JB1 (REQ, ADDR or DATA), `addr_v` JB2 (ADDR), `valid` JB3 (DATA),
  `last` JB4 (the fourth DATA clock), `rsp_valid` JB7 (RESP or ERR), `rsp_err` JB8 (ERR), `cmd_ready` JB9 (IDLE) and `cmd_ack` JB10.
- **No added latency:** the partner reacts to each output in the clock where the state table says it is high, so no output may be
  later than the state. `cmd_ack` is high in the clock where the controller is in IDLE and `cmd_valid` is high (the clock in which
  the command is taken). There is no restriction on what drives the pins.
- CPU_RESETN resets everything: IDLE, the counts zero.
- Over the test shell (USB-UART, 115200 baud) I can read BURSTS (window offset 0, the number of responses taken in RESP, that is
  clocks in RESP with `rsp_ready` high, 16 bits, wrapping) and ERRS (offset 1, the same for ERR), and write CLEAR (offset 2, any
  data), which zeroes both. The design ID is "NXLT".

Test hooks: top module `d24_no_extra_latency_top`, ports named as in the board's master XDC (the scalar names `JA1` ... `JB10`), and the test
shell's `CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
