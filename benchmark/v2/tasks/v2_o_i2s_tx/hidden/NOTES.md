# Oracle ambiguity list for v2_o_i2s_tx (what spec.md leaves out on purpose)

1. Which I2S-like format (Philips I2S: MSB one bit clock after the word-select edge), which edge SDO changes on (falling).
2. What "commit" snapshots and when: the staging registers at the moment of the write; the pair goes out at the next frame start.
3. That later staging writes never reach the wire without a new commit.
4. What FRAMES counts (left-slot starts) and which bit clears it.
5. Register offsets, readback of the staging registers (sign-extended 24 bits), reset values.
6. The bit-clock ratio the bench uses (board clock 12 times faster); the allowed range is 8 to 100.
7. That the padding bits are zero.
