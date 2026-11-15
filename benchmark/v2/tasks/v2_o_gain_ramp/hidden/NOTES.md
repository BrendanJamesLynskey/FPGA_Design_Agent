# Oracle ambiguity list for v2_o_gain_ramp (what spec.md leaves out on purpose)

The interview should ask; the spec oracle answers from `spec.yaml`:

1. The form of the slide: a constant step (linear), not a one-pole filter. spec.md says "the same fixed amount on every sample".
2. When the step is applied: before the gain is used on the same sample.
3. Rounding of the product: floor (arithmetic shift), not round-to-nearest, not truncation toward zero.
4. What the status bits mean exactly: RAMPING is live against the present target; SAT is per sample, not sticky.
5. What the sample register reads back (the last sample, sign-extended) and the register offsets.
6. Whether mute holds the output at zero at once (no: it slides).
7. Reset value of the gain (1.0) and that the applied gain restarts at 1.0.
