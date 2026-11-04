# Request/acknowledge responder

I want to practise the classic four-phase handshake, with me as the requester on SW[0].

- When I raise REQ (SW[0] up) the responder takes a fixed number of clocks to think, then raises ACK on LED[0]. ACK
  stays up as long as REQ does, and drops once REQ has dropped.
- If REQ is withdrawn before ACK has come up, that is an aborted request: no ACK is given, and it is counted.
- A requester that sits on ACK for too long is a fault: the responder drops ACK anyway and lights LED[1] until REQ
  goes low again.
- LED[2] is lit while the responder is thinking.
- Over the test shell (USB-UART, 115200 baud) I can read how many handshakes completed, how many were aborted and
  how many timed out, and clear the counts. The design ID is "HSHK".

Test hooks: top module `p_handshake_fsm_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `ACK_DELAY` (clocks the responder thinks for)
and `HOLD_LIMIT` (clocks ACK may stay up) as top-level parameters.
