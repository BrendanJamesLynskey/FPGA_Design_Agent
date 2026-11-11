# Burst sequencer whose pins come straight from flip-flops

I want a burst sequencer on the Nexys A7-100T that talks to an external bus partner over two Pmods. The partner's input stage has no slack for logic, so the outputs have to come from flip-flops.

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
- **Pin timing (the device on JB samples them with a data sheet that leaves no room for logic after the last flip-flop):** every
  output pin on JB must be driven directly by a flip-flop, with no logic between that flip-flop and the pin, so that it cannot
  glitch. `cmd_ack` is high in LOAD. The outputs may show the state one clock late: all eight lag the state by the same number of
  clocks, 0 or 1; that lag is the only thing that may differ from the state table above.
- CPU_RESETN resets everything: IDLE, the counts zero.
- Over the test shell (USB-UART, 115200 baud) I can read BURSTS (window offset 0, the number of responses taken in RESP, that is
  clocks in RESP with `rsp_ready` high, 16 bits, wrapping) and ERRS (offset 1, the same for ERR), and write CLEAR (offset 2, any
  data), which zeroes both. The design ID is "RGOU".

Test hooks: top module `d24_registered_outputs_top`, ports named as in the board's master XDC (the scalar names `JA1` ... `JB10`), and the test
shell's `CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
