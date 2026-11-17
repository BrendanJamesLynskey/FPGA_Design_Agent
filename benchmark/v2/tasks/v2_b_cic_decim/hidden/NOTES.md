# Notes for v2_b_cic_decim (what spec.md leaves out, and what the tests cannot reach)

What spec.md does not say, so the interview has to ask (the oracle answers from hidden/spec.yaml):
- register layout (CTRL, BITS, STATUS, RESULT, NEXT at offsets 0..4) and which bit of STATUS is which;
- queue depth 16, and that a result arriving at a full queue is dropped (not the oldest);
- how many outputs are fills (two), the 46-bit window that makes them fills, and that the integrators start at 0;
- bit order of a BITS word (bit 0 first) and the mapping 1 -> +1, 0 -> -1;
- register width (14 bits are enough for the exact output between -4096 and +4096).

Trap: a textbook CIC outputs from the first decimation instant; the request says only fully made results count.

Not reachable by the bench: a write to BITS while BUSY (the shell is far slower than the 32 clocks it takes to feed a word) and
the abandonment of bits being fed when CLEAR arrives mid-word. Both are documented in spec.yaml and not tested. The decimation
phase at CLEAR is always 0 for the same reason (words are multiples of the rate), so a mutant that keeps the phase is equivalent.
