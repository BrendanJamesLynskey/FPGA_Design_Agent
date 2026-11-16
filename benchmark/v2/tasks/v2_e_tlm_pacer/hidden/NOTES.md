# What the v2_e_tlm_pacer request omits

Questions an interviewing agent should raise (the oracle reads `spec.yaml` to reply):

- Counting semantics: the counter counts ticks, the frame falls due on the tick that makes it reach the period, so a period of N gives a frame on every Nth tick.
- A request change applies at the next boundary (or switch-on), not at once.
- Overrun: dropped, never queued; totals survive switching off.
- The request register keeps the raw value; EFF shows the clamped one.
- PERIOD_MIN is a parameter (default 4); TICK is a count write, n in 0..255.
