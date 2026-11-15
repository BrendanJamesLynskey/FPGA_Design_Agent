# Notes for v2_b_halfband_dec

What spec.md does not say:
- the coefficients [-1, 0, 9, 16, 9, 0, -1] (sum 32), the shift 5;
- which sample of a pair makes the result (the second; the first is the trap);
- the convergent (ties to even) rule in integers, with examples; saturation limits;
- queue depth 8, full-queue rule (drop the new result), the ODD bit in STATUS;
- what CLEAR resets (history, parity, queue, SAT, OVR);
- the register layout.

Trap: a polyphase decimator that keeps the first sample of each pair.
