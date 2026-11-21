# results/137_arith_pareto: a verified, measured Pareto surface for CORDIC sin/cos (brief 137, phase 0)

Thirteen CORDIC sin/cos implementations chosen to span the architecture and word-length knobs were each verified against a bit-exact model in simulation, then
implemented out of context in Vivado 2026.1 on an Artix-7 part (all thirteen) and on the Zynq UltraScale+ K26 (four of them), with utilisation, timing and
vectorless power recorded. The analytical cost models of HW_Design_Space_Agent were then asked to predict every measurement, to decide whether such a model is
good enough to prune a design space. The plan for the whole line of work is [docs/arithmetic_pareto_plan.md](../../docs/arithmetic_pareto_plan.md).

## Results

All numbers are in `comparison.md` (tables) and the JSON records below; this is the reading of them.

**The surface** ([fig1_pareto_artix7.svg](fig1_pareto_artix7.svg)). On xc7a35t-1 at a 3.5 ns out-of-context target the points span 161 to 1449 LUTs, 86 to 1249 FFs, 4 to 20 clocks of latency
and Fmax from 39 to 301 MHz after routing. The families separate as expected: `iterative` is smallest (P01: 161 LUTs, 86 FFs, 196 MHz, 15 clocks, 13 Msps);
`pipelined` reaches 270 to 301 MHz at one result per clock but costs hundreds of LUTs and as many FFs; `pipelined_m` and `unrolled_k` sit between and
fall off in Fmax as m or k grow (P12, m=8: 58 MHz; P05, k=6: 39 MHz). With accuracy as a third objective most points are non-dominated (a wider word is more accurate and
bigger), so the front under a stated spec is more useful: among the 10 points with at least 8 accuracy bits the area-against-latency front is P01, P08, P12
and the area-against-throughput front is the same three.

**The cost model against Vivado** ([fig2_model_vs_vivado.svg](fig2_model_vs_vivado.svg)), 13 points, none in either calibration file. Default two-anchor model, post-route: RMS error 15.5 % on LUTs
(max 42.2 %), 3.4 % on FFs (max 5.9 %), 7.3 % on Fmax (max 20.0 %). Refit model: 14.3 %, 3.0 %, 10.7 %. Spearman rank correlation of prediction against measurement is 0.977 for LUTs, 1.0 for FFs and
0.984 for Fmax. The model's front equals the measured front for both views, so it would not have pruned a front point on this set. Where it is wrong: LUT counts of the `unrolled_k` k=6 point P05
(-42 % default, -31 % refit) and the iterative W=20 point P02 (+26 %, +39 % refit); the cause was not investigated; Fmax of P05 (+20 %, +31 %). Everything with a fixed shift (`pipelined`, `pipelined_m`) is within about 10 % on LUTs and 11 % on Fmax. Refitting on the earlier-release data did not
improve out-of-sample LUT error here.

**Between families** ([fig3_k26_vs_artix7.svg](fig3_k26_vs_artix7.svg)). The same four RTL points on the K26 have nearly the same LUT and FF counts (LUTs 0.2 to 10 % fewer, FFs identical) and a post-route Fmax 2.3 to 2.6 times higher,
in the same rank order; the Artix-7-calibrated Fmax prediction is 58 to 60 % low on every K26 point, a near-constant factor, so one scale constant per family would carry the model across, but the model's
LUT and FF counts transfer unchanged (RMS 5.9 % and 3.6 %). The static power of the K26 is 0.288 W against 0.068 W, so its total power is higher for the small designs; the dynamic power is within 0.75 to 1.33 times.

**Verification.** All 13 points pass: every output code of the generated RTL equals the bit-exact model's on every angle of the sweep (all 2^W codes for W <= 16, 2^17 strided and seeded-random codes above), every
latency equals the schedule's, in Icarus Verilog (Verilator is not installed on this PC). The error against ideal sin/cos is stated per point in `verify.json` (4.6 to 11.9 LSB maximum: the unguarded configurations
are loose; it is a property of the numerics, identical in model and RTL). Vivado's post-synthesis netlists were checked equivalent to the RTL for four points with Yosys SAT, bounded to latency + 4 clocks from reset
(`equiv_artix7.json`): P06, P08, P10 and P12 equivalent; P01 (iterative, 15 clocks) did not finish in 240 s. A seeded change to one LUT initial value of P06's netlist was caught, run by hand and not recorded.

## Records

| File | What |
|---|---|
| `verify.json` | per point: simulator version, sweep, mismatches, latency expected and measured, error against ideal sin/cos, pass |
| `artix7/measured.json`, `k26/measured.json` | per point: post-synthesis and post-route LUT, FF, carry cells, DSP, BRAM, WNS, WHS, Fmax, and vectorless power; Vivado 2026.1, 4 threads, wall seconds |
| `artix7/reports/<id>/`, `k26/reports/<id>/` | the Vivado utilisation, timing-summary and power reports (dates, host and paths removed) |
| `equiv_artix7.json` | bounded equivalence of Vivado's post-synthesis netlist against the generated RTL, with the tool and depth |
| `comparison.json`, `comparison.md` | the objectives per point, the fronts, the cost-model predictions (two calibrations) and the per-axis errors, post-synthesis and post-route |
| `fig1_pareto_artix7`, `fig2_model_vs_vivado`, `fig3_k26_vs_artix7` (`.svg`, `.png`) | the figures |

Code: [flow/arith_pareto.py](../../flow/arith_pareto.py); tests: [flow/tests/test_137_arith_pareto.py](../../flow/tests/test_137_arith_pareto.py). The RTL generator, bit-exact model and cost models are imported from a
HW_Design_Space_Agent checkout (main 80415c6, unchanged).

## Reproduce

1. `python3 flow/arith_pareto.py verify` (Icarus; no Vivado; about 6 minutes) writes `verify.json`.
2. `python3 flow/arith_pareto.py export --part xc7a35tcpg236-1 --work <dir> --threads 4`, then `vivado -mode batch -source <dir>/run.tcl` (Vivado 2026.1, in a heavy slot taken with `_handoff/take_heavy_slot.sh`, 6 GB scope; 26 minutes for the 13 Artix-7 points at 4 threads, peak 2.6 GB; 17 minutes and peak 4.5 GB for the 4 K26 points), then `python3 flow/arith_pareto.py collect --part xc7a35tcpg236-1 --work <dir> --out results/137_arith_pareto/artix7`. Repeat with `--part xck26-sfvc784-2LV-c` for the K26 (clock 2.0 ns by default; Artix-7 3.5 ns).
3. `python3 flow/arith_pareto.py equiv --work <dir> --out results/137_arith_pareto/equiv_artix7.json --yosys <yosys> --ids P06 P08 P10 P12` (OSS CAD or the formal environment's Yosys).
4. `python3 flow/arith_pareto.py report` rewrites `comparison.*` and the figures (needs matplotlib and the HW_DSE source, `HW_DSE_SRC`).

## Known gaps and limits

- One Vivado run per point; no repeat to measure run-to-run spread. Placement noise of a few percent on Fmax is not separated from model error.
- The target clock is tight (3.5 ns on Artix-7, 2.0 ns on K26) so that the tool works as hard as it can; where the constraint was met (Artix-7 P06 and P08, K26 P01 and P07) the Fmax shown is `1000/(T-WNS)` and is a lower bound on what the tool could reach.
- Out-of-context: no input or output delays, no neighbouring logic; a block in a real design will not reach these Fmax figures unless its ports are registered. Power is vectorless (12.5 % default toggle, confidence Medium), at the target clock, Vivado's model, not a measurement.
- CORDIC has no DSP or BRAM use, so the DSP-against-LUT and BRAM-against-LUT knobs are untested; every DSP and BRAM column is zero. A second function is needed (the plan's phase 2).
- Verification is one simulator (Icarus), exhaustive for W <= 16 and dense above; the error bound is a measured lower bound on the worst case, not a proof. The netlist equivalence is bounded, covers four of 13 points, and P01 timed out; no point has a post-implementation simulation or a Lean proof.
- Thirteen points are too few to say the cost model is good in general: the verdict is that it ranks well and mispredicts LUTs by up to 40 % on the unrolled and iterative shapes with guard bits. The earlier-release refit did not generalise better than the two-anchor model on this set.
- The Artix-7 part is the small xc7a35t used by HW_Design_Space_Agent; other devices of the family and speed grades were not run. The K26 run reuses the Artix-7-calibrated model, so its Fmax error is a calibration gap, not a model-structure finding.
- The Vivado peak memory declared in the heavy slot was 4G; the K26 run peaked at 4.5 GB resident.
