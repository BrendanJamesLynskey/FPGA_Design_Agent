# Oracle ambiguity list for v2_o_audio_path (what spec.md leaves out on purpose)

1. Where the meters tap the signal: after gain, mute and limiting (spec.md says "on the processed signal").
2. The delay: exactly one frame; silence in the first frame.
3. How the smoother works: a constant step per sample (not a one-pole filter), landing exactly on the target, the step taken before use.
4. Rounding of the gain product (floor) and the limiter's behaviour at the end of the range.
5. The peak's hold and fall: a thirty-second of the reading per sample with a floor of one, the hold reloaded by an equal magnitude, one HOLD for both channels.
6. The RMS definition: sum of squares at full width, one division per block, floor mean, floor root.
7. What the clip counter counts (each sample at either end, not runs; the ends themselves).
8. The register map, which bits of CTRL and CLR do what, what WINDOWS and FRAMES count (left blocks, right samples).
9. MCLK: board clock / 8, 50 % duty.
10. The bit-clock ratio the bench uses (12); the allowed range 8 to 100.

Not testable through the shell: the saturation of the clip count at 0xFFFF, the wrap of WINDOWS and FRAMES (65 536 frames).
