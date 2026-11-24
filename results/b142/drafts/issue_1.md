# Draft issue 1 (not posted): `synth_xilinx -family xcup` does not absorb a multiply-accumulate feedback into the DSP48E2; `-family xc7` does

Status of the upstream check (2026-11-21, read-only GitHub search of YosysHQ/yosys issues and pull requests; the second round was cut short by the API rate limit): no issue or pull request found for "DSP48E2 accumulator", "xilinx_dsp pre-adder",
"xilinx_dsp accumulate", "xcup DSP". Related but different: #6252 (open, DSP register absorption corrupts a signed product), #6046 and #6504 (closed, init values). Not checked on a
current master build (the machine cannot build one), so confirm on master before posting.

Yosys 0.70+385 (OSS CAD Suite, git sha1 098e46a36), `read_slang` front end.

## Reproduction

`issue_1_repro/m14_mac.sv`: an 18x18 signed multiply with input and product registers whose accumulator `acc <= (clr ? 0 : acc) + m` is the DSP's P-register feedback.

```
yosys -p "plugin -i slang; read_slang --top m14_mac m14_mac.sv; synth_xilinx -family xcup -top m14_mac -noiopad -noclkbuf -flatten; stat"
```

| | xc7 (DSP48E1) | xcup (DSP48E2) | Vivado 2026.1 on xck26 |
|---|---|---|---|
| m14_mac | 1 DSP, 0 LUT, 2 FF | 1 DSP, 48 LUT, 12 CARRY4, 122 FF | 1 DSP, 0 LUT, 1 FF |

Same pattern on xcup: `m14b_mac_noclr` (no clear: 48 LUT, 12 CARRY4), `m15_patdet` (pattern detect: 61 LUT against 14 on xc7) and `m35_mac_ce_rst` (clock enable and reset: 48 LUT against 0 on xc7). A registered MAC from the arithmetic library (`r08_mac_dsp`) is in the fabric on both families (40 LUT, 10 CARRY4; Vivado 0 LUT, 2 DSPs), so that one is not an xcup-only gap. The multiplier itself maps to the DSP48E2 on xcup (`m11_mult18`, `m12_mult27x18`); the accumulating adder stays in the fabric.

Cost to the user: after place and route in Vivado (xck26, out of context, 2.5 ns clock, one run each) the Yosys netlist of `m14_mac` has WNS -0.397 ns with 48 LUT and 6 CARRY8 against +1.285 ns with 0 LUT for Vivado's own synthesis
(`results/b142/impl_table.md`).

Pre-adder (`m13_preadd`) and SIMD (`m17_simd`) are also not absorbed on xcup, and the pre-adder is not absorbed on xc7 either (26 LUT, 2 DSPs); Vivado uses the DSP's pre-adder and 0 LUT.
