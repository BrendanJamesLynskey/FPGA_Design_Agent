# Round-robin arbiter

I want an arbiter for four requesters, with the requests on SW[3:0] and the grant on LED[3:0], one LED at a time.

- Only one requester is granted at a time. A grant is kept until the requester lets go of its request.
- Fairness: when the grant becomes free, the next requester in rotation after the one that was granted last gets it,
  so a requester cannot be starved. Nobody holds a grant for ever when someone else is waiting: after a fixed
  number of clocks a grant is taken away if another request is pending.
- Between two grants the grant lines drop for a moment.
- Over the test shell (USB-UART, 115200 baud) I can read how many grants each requester has had, how many were taken
  away, and which one was granted last. The design ID is "RRAR".

Test hooks: top module `p_rr_arbiter_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `MAX_HOLD` (clocks a grant may last while others
wait) as a top-level parameter.
