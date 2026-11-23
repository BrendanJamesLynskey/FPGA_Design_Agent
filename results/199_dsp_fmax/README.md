# Brief 199: is the DSP Fmax honest? (pulse-width / minimum-period check) and the SIMD probe

Vivado 2026.1, one routed out-of-context run per row, one thread. Parts: a7 = `xc7a100tcsg324-1`, k26 = `xck26-sfvc784-2LV-c`. The wrapper is the brief-185 fully registered 18 x 18 multiply (1,1,1); `bufg` variants put the clock through a BUFG (`dsp_mul_pipe_ooc_bufg.sv`). Script `pw_probe.tcl`, rerun with `run_probe.sh`; reports in `pulse_width/`.

## Pulse-width and minimum-period checks (`report_pulse_width`)

| run | clock ns | WNS ns | limiting Min Period check (required ns = MHz) | other checks |
| --- | --- | --- | --- | --- |
| a7 bare | 1.8 | +0.147 | DSP48E1/CLK 2.154 = 464.3 | FDRE pulse width 0.500 |
| a7 bufg | 1.8 | +0.279 | BUFG/I 2.155 = 464.0; DSP48E1/CLK 2.154 | |
| k26 bare | 1.0 | -0.195 | DSP_OUTPUT/CLK 0.850 = 1176.5; FDRE/C 0.550 | no clock buffer in the path, so no buffer check |
| k26 bufg | 1.0 | -0.195 | **BUFGCE/I 1.379 = 725.2** (slack -0.379); DSP_OUTPUT/CLK 0.850 | |
| k26 bufg | 1.3 | +0.105 | BUFGCE/I 1.379 (slack -0.079); setup met | setup-derived Fmax 837 again |

## Findings

1. The 185 method already applied the slice's own Min Period (`min(setup, 1000 / Min Period)`); the K26 slice's Min Period in Vivado is 0.85 ns (1176 MHz), looser than DS925. So the pulse-width section was not ignored; the 837 MHz was set by setup slack (WNS -0.195 at 1.0 ns, the same with and without a BUFG).
2. What the out-of-context run did not see is the **clock buffer**. With the clock through a BUFG, `report_pulse_width` adds `Min Period BUFGCE/I 1.379 ns` on the -2LV part (725 MHz = DS925 Table 84, BUFG FMAX, -2 at 0.72 V) and `BUFG/I 2.155 ns` on the Artix-7 -1 part (464 MHz, the same as the slice's 2.154 ns). A real design clocked through a BUFG cannot pass the buffer limit, so the Fmax of every k26 point above 725 MHz was too high.
3. Vivado does not turn DS925 Table 83 (DSP48 FMAX 775 MHz at -2, 0.85 V; 644 MHz at 0.72 V) into a DSP check. The 725 MHz now reported is therefore still above the data sheet's DSP figure for the 0.72 V column; the data-sheet figure remains the sign-off ceiling. That the BUFG limit equals the 0.72 V column's 725 MHz suggests Vivado times the -2LV part at 0.72 V (an inference).
4. Fix: `results/185_dsp_slices/run_dsp.py` (`fmax_limits`, `BUF_MIN_PERIOD_NS`, command `recompute`) now takes Fmax = min(setup, slice Min Period, BUFG Min Period) and records which one limited; unit tests in `flow/tests/test_199_dsp_fmax.py`. a7 values are unchanged (the slice limit and the buffer limit are 1 ps apart); 12 of 58 k26 points change (all were above 725 MHz).

## SIMD probe (`simd/`, synthesis only, `results.txt`)

| source | a7 | k26 |
| --- | --- | --- |
| `(* use_dsp = "simd" *)` on the module, four 10-bit or 12-bit lanes (AMD template shape; `t_tmpl`, `t_tmpl12`) | 1 DSP48, `USE_SIMD=FOUR12`, AREG=1, PREG=1; 0 fabric registers | same (DSP48E2, FOUR12) |
| same attribute on the module, our 4 x 12-bit packed in one 48-bit word (`t_ours_mod`) | 1 DSP, FOUR12, AREG=1, PREG=1; 0 registers | same |
| attribute on the signal (`t_ours`, as in 185) | **not mapped**: 0 DSP, 144 registers | **not mapped**: 0 DSP, 144 registers |

So `USE_SIMD` does map, but only when the `use_dsp = "simd"` attribute is on the module (UG901's placement); on a signal it is ignored. The input and output registers are absorbed into the slice (AREG, PREG). Registers other than AREG and PREG (BREG, CREG) were not printed by the probe.
