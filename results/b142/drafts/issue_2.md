# Draft issue 2 (not posted): a shift register read at a run-time tap is not mapped to SRLC32E by `synth_xilinx` (xcup and xc7)

Status of the upstream check (2026-11-21, read-only search; the round was cut short by the API rate limit): "xilinx_srl variable" returns only #4590 and #3587, both closed and about other errors; "SRL variable tap" returns nothing.
The `xilinx_srl -variable` pass is in the flow (it ran in every run); not checked on a current master build.

Yosys 0.70+385 (OSS CAD Suite, git sha1 098e46a36), `read_slang` front end.

## Reproduction

`issue_2_repro/m26_srl_var.sv`: a 32-stage, 8-bit shift register `sh` whose output is `sh[tap]` with `tap` a run-time input, then registered.

```
yosys -p "plugin -i slang; read_slang --top m26_srl_var m26_srl_var.sv; synth_xilinx -family xcup -top m26_srl_var -noiopad -noclkbuf -flatten; stat"
```

Observed (xcup, and the same on xc7): 114 LUT and 264 FF (the 32 x 8 stages in flip-flops and a 32:1 mux per bit). With `-widemux 5 -flatten`: 72 LUT, 32 MUXF7, 16 MUXF8, 264 FF.
Vivado 2026.1 on xck26: 8 SRL (SRLC32E), 0 LUT, 8 FF. A fixed-tap shift register of the same depth maps to SRL16/SRLC32E in Yosys (`m25_srl32`, `m27_srl128`: 16 SRL, 0 FF), so the pass works; the variable tap is the gap.

Cost: 264 flip-flops and 114 LUTs against 8 SRLs.
