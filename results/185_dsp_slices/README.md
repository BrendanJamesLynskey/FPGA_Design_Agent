# Brief 185: DSP slices as an area of expertise (measured)

Out-of-context Vivado 2026.1 runs (synthesis, placement, routing, one thread) of small designs built to show which registers a DSP slice needs, how wide multiplies and dot products are built from slices, and how clock speed trades against latency. Two parts: **a7** = `xc7a100tcsg324-1` (DSP48E1, target clock 1.8 ns) and **k26** = `xck26-sfvc784-2LV-c` (DSP48E2, target clock 1.0 ns). Records: `data/a7.json`, `data/k26.json` (116 points, every one `ok`); per-point evidence (DSP cell register properties, the synthesis DSP Report, the DSP lines of the DRC and methodology reports, the pulse-width and Min Period checks) in `raw/<part>/<point>/`.

## How to read the numbers

- **Fmax** = the smaller of `1000 / (target period - worst setup slack)` and `1000 / the largest Min Period a clock pin requires` in the routed timing summary. One run per point at a target clock tighter than most points can meet, so it is an estimate (no repeats, no spread). A target that was easy would give only a lower bound; the points whose setup slack was positive (nine on a7, one on k26) are limited by the slice's own Min Period instead, except the k26 SIMD point (fabric adders, slack positive), whose figure is only a lower bound.
- **Latency** = register stages from the module's operand inputs to its output (the formula the RTL is written for; checked by the Icarus benches in `tb/`). Every module is wrapped (`*_ooc.sv`) in kept (`DONT_TOUCH`) registers on all ports, which are not counted in the latency and which Vivado cannot absorb into the slice; the timed path is register to register through the module.
- `flow/ipchar.py`'s Fmax treats a Min Period shortfall as a half-period pulse-width shortfall and so over-penalises a slice's own limit; `run_dsp.py` recomputes it (on the a7 part a fully registered slice is limited by its 2.154 ns Min Period, 464.3 MHz, which matches the data-sheet figure for -1; other briefs' Fmax values for DSP-heavy blocks were not re-derived here).

## 1. Registers around one multiply (18 x 18 signed, one slice)

Columns: registers written in the RTL (operand stages NA, multiplier NM, output NP); the slice's registers as Vivado set them (AREG / MREG / PREG after routing); Fmax in MHz. Vivado packs a lone register after the multiply into MREG, not PREG.

| RTL regs NA,NM,NP | latency | a7 AREG,MREG,PREG | a7 MHz | k26 AREG,MREG,PREG | k26 MHz |
| --- | --- | --- | --- | --- | --- |
| 0,0,0 | 0 | 0,0,0 | 175 | 0,0,0 | 354 |
| 0,0,1 | 1 | 0,1,0 | 319 | 0,1,0 | 571 |
| 0,1,0 | 1 | 0,1,0 | 319 | 0,1,0 | 571 |
| 0,1,1 | 2 | 0,1,1 | 325 | 0,1,1 | 678 |
| 1,0,0 | 1 | 0,1,0 | 319 | 1,0,0 | 394 |
| 1,0,1 | 2 | 1,1,0 | 327 | 1,1,0 | 596 |
| 1,1,0 | 2 | 1,1,0 | 327 | 1,1,0 | 596 |
| 1,1,1 | 3 | 1,1,1 | 464 | 1,1,1 | 837 |
| 2,0,0 | 2 | 1,1,0 | 327 | 2,0,0 | 394 |
| 2,0,1 | 3 | 2,1,0 | 317 | 2,1,0 | 596 |
| 2,1,0 | 3 | 2,1,0 | 317 | 2,1,0 | 596 |
| 2,1,1 | 4 | 2,1,1 | 464 | 2,1,1 | 837 |

Resets on the lone / full output register (RSTP 1 = synchronous, 2 = asynchronous):

| RTL regs | reset | a7 A,M,P | a7 MHz | k26 A,M,P | k26 MHz |
| --- | --- | --- | --- | --- | --- |
| 0,0,1 | none | 0,1,0 | 319 | 0,1,0 | 571 |
| 0,0,1 | sync | 0,1,0 | 319 | 0,1,0 | 614 |
| 0,0,1 | async | 0,0,1 | 199 | 0,0,1 | 440 |
| 1,1,1 | none | 1,1,1 | 464 | 1,1,1 | 837 |
| 1,1,1 | sync | 1,1,1 | 464 | 1,1,1 | 837 |
| 1,1,1 | async | 1,1,1 | 464 | 1,1,1 | 837 |

### 1b. Fmax against the number of registers (house rule 1)

One 18 x 18 signed multiply in one slice, no reset; the best result at each register count is in bold, and the variants NA,NM,NP (operand stages, multiplier register, output register) that reached each value are in brackets. Register count = latency. **a7** = `xc7a100tcsg324-1` (-1); **k26** = `xck26-sfvc784-2LV-c` (-2LV, the only grade measured; there is no -1 K26 run). One routed out-of-context run per point, Vivado 2026.1; an estimate, no repeats. Plot: [fmax_vs_registers.svg](fmax_vs_registers.svg).

| registers | a7 Fmax MHz (RTL regs NA,NM,NP) | k26 Fmax MHz (RTL regs NA,NM,NP) |
| --- | --- | --- |
| 0 | **175** (0,0,0) | **354** (0,0,0) |
| 1 | **319** (0,0,1 0,1,0 1,0,0) | **571** (0,0,1 0,1,0); 394 (1,0,0) |
| 2 | **327** (1,0,1 1,1,0 2,0,0); 325 (0,1,1) | **678** (0,1,1); 596 (1,0,1 1,1,0); 394 (2,0,0) |
| 3 | **464** (1,1,1); 317 (2,0,1 2,1,0) | **837** (1,1,1); 596 (2,0,1 2,1,0) |
| 4 | **464** (2,1,1) | **837** (2,1,1) |

Steps, as a share of the three-register result: a7 38 percent with none, 69 with one, 70 with two, 100 with three and with four; k26 42, 68, 81, 100, 100. Which three matters: operand, multiplier and output registers (1,1,1) reach the slice's limit, while two operand stages plus the multiplier register with no output register (2,1,0) reach only 317 on a7 and 596 on k26; a fourth register (a second operand stage) adds nothing on either part.

The native widths (25 x 18 on a7, 27 x 18 on k26) were run at three registers and at four: a7 464 and 464 MHz, k26 837 and 837 MHz, the same as 18 x 18; no native-width run exists at fewer registers. A lone operand register differs between the parts: on a7 Vivado packs it into MREG (319), on k26 it stays in AREG and the product is unregistered (394). A pre-adder multiply `(d + a) * b` (24 x 18): with the AD register a7 464 / k26 837 MHz (4 registers); without it a7 290 / k26 500 MHz (3 registers).

Our numbers beside the data sheet (public figures: DS181 v1.27.1 Table 31, -1, 1.0 V; DS925 v1.30 Table 83, -2 at 0.85 V / 0.72 V):

| configuration | DS181 -1 MHz | a7 measured MHz | DS925 -2 MHz (0.85 V / 0.72 V) | k26 measured MHz |
| --- | --- | --- | --- | --- |
| all registers used | 464.25 | 464 | 775 / 644 | 837 |
| two-register multiply without MREG | 257.47 | not reproduced: Vivado packs the lone register into MREG | 544 / 440 | not reproduced (as a7) |
| without ADREG (pre-adder) | 290.44 | 290 | 565 / 453 | 500 |
| without pipeline registers (MREG, ADREG) | 190.69 | 175 | 410 / 323 | 354 |

On a7 the fully registered and the no-ADREG slices match the data sheet (the slice's own Min Period); with no pipeline registers ours is lower (reason not investigated). On k26 the fully registered 837 MHz is **above** the data sheet's 775 MHz (-2, 0.85 V) and 644 MHz (-2, 0.72 V): it is a setup estimate at a 1.0 ns target, and the Min Period Vivado reports for the slice (0.85 ns) is looser than the data sheet's. Use the data-sheet figure, not 837, as the K26 slice ceiling at sign-off; the table shows the shape (the steps between register counts), which is what rule 1 rests on. Which supply voltage the -2LV run assumed was not recorded.

![Fmax against the number of registers around one multiply](fmax_vs_registers.svg)


## 2. Wide multiplies (slices, latency, MHz)

Style 0 = the `*` operator with the same operand, multiplier and output registers (the tool's own split); 1 = hand-written cascade (PCOUT to PCIN with the 17-bit shift, operands skewed one clock per stage, chains added in the fabric); 2 = partial products each in a slice, summed in a registered fabric adder tree. Style-0 results with a second operand register (NA 2) are in the data and equal or lower.

| WA x WB | style | a7 slices | a7 LUT | a7 latency | a7 MHz | k26 slices | k26 LUT | k26 latency | k26 MHz |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 27 x 27 | 0 | 3 | 175 | 3 | 126 | 2 | 0 | 3 | 493 |
| 27 x 27 | 1 | 4 | 30 | 5 | 309 | 2 | 0 | 4 | 794 |
| 27 x 27 | 2 | 4 | 80 | 5 | 200 | 2 | 37 | 4 | 433 |
| 32 x 32 | 0 | 4 | 47 | 3 | 252 | 4 | 47 | 3 | 346 |
| 32 x 32 | 1 | 4 | 40 | 5 | 306 | 4 | 38 | 5 | 552 |
| 32 x 32 | 2 | 4 | 106 | 5 | 194 | 4 | 104 | 5 | 412 |
| 35 x 25 | 0 | 2 | 0 | 3 | 257 | 2 | 0 | 3 | 493 |
| 35 x 25 | 1 | 2 | 0 | 4 | 464 | 2 | 0 | 4 | 794 |
| 35 x 25 | 2 | 2 | 43 | 4 | 198 | 2 | 43 | 4 | 420 |
| 44 x 35 | 0 | 6 | 76 | 3 | 221 | 4 | 62 | 3 | 346 |
| 44 x 35 | 1 | 6 | 64 | 6 | 308 | 6 | 62 | 6 | 577 |
| 44 x 35 | 2 | 6 | 207 | 6 | 197 | 6 | 206 | 6 | 412 |
| 48 x 48 | 0 | 9 | 80 | 3 | 135 | 9 | 87 | 3 | 261 |
| 48 x 48 | 1 | 6 | 81 | 6 | 266 | 6 | 79 | 6 | 571 |
| 48 x 48 | 2 | 6 | 241 | 6 | 194 | 6 | 241 | 6 | 413 |
| 64 x 64 | 0 | 16 | 178 | 3 | 110 | 16 | 177 | 3 | 209 |
| 64 x 64 | 1 | 12 | 195 | 7 | 212 | 12 | 207 | 7 | 538 |
| 64 x 64 | 2 | 12 | 616 | 7 | 194 | 12 | 620 | 7 | 392 |

## 3. Dot product, sixteen-bit signed terms, one result per clock

Cascade = systolic chain, one slice per term, operands skewed one clock per stage (latency K + 2). Tree = one slice per product (operand, multiplier, output registers), fabric adder tree with a register after every TR levels and after the last (TR 99 = last only). 'Bound' names what set the Fmax: setup slack, or the minimum period of the named cell type.

| K | structure | a7 latency | a7 slices | a7 LUT | a7 MHz | a7 bound | k26 latency | k26 slices | k26 LUT | k26 MHz | k26 bound |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | cascade | 6 | 4 | 0 | 464 | min period DSP48E1/CLK | 6 | 4 | 0 | 837 | setup |
| 4 | tree TR 1 | 5 | 4 | 97 | 331 | setup | 5 | 4 | 97 | 701 | setup |
| 4 | tree TR 2 | 4 | 4 | 125 | 264 | setup | 4 | 4 | 122 | 575 | setup |
| 4 | tree TR 99 | 4 | 4 | 125 | 264 | setup | 4 | 4 | 122 | 575 | setup |
| 8 | cascade | 10 | 8 | 64 | 464 | min period DSP48E1/CLK | 10 | 8 | 64 | 656 | min period SRL16E/CLK |
| 8 | tree TR 1 | 6 | 8 | 229 | 328 | setup | 6 | 8 | 229 | 702 | setup |
| 8 | tree TR 2 | 5 | 8 | 285 | 256 | setup | 5 | 8 | 281 | 552 | setup |
| 8 | tree TR 99 | 4 | 8 | 254 | 157 | setup | 4 | 8 | 257 | 392 | setup |
| 16 | cascade | 18 | 16 | 192 | 464 | min period DSP48E1/CLK | 18 | 16 | 192 | 656 | min period SRL16E/CLK |
| 16 | tree TR 1 | 7 | 16 | 496 | 327 | setup | 7 | 16 | 496 | 703 | setup |
| 16 | tree TR 2 | 5 | 16 | 602 | 244 | setup | 5 | 16 | 626 | 546 | setup |
| 16 | tree TR 99 | 4 | 16 | 456 | 116 | setup | 4 | 16 | 461 | 299 | setup |

A published estimate for an eight-term dot product is about 6 stages as a tree against about 11 as a cascade. Measured here at K = 8: the tree is 6 stages and the cascade 10 (this cascade has no separate output register, so one fewer than the estimate); the estimate **holds for latency only**. Speed: on a7 the tree is 328 MHz against the cascade's 464; on k26 the tree is 702 against 656, where the cascade's operand-skew delay lines were mapped to shift-register cells (SRL16E, Min Period 1.524 ns) that set its limit.

## 4. Per-level and per-register delay (from the worst setup path of each routed point)

`path_delay_ns`, `path_logic_ns`, `path_route_ns`, `logic_levels` and `path_per_level_ns` are in the data. Examples (fabric adder-tree paths, setup-limited):

| point | part | logic levels | path delay ns | ns per level |
| --- | --- | --- | --- | --- |
| dot_W16_K8_STYLE1_TR1 | a7 | 10 | 3.07 | 0.307 |
| dot_W16_K8_STYLE1_TR2 | a7 | 11 | 3.933 | 0.358 |
| dot_W16_K8_STYLE1_TR99 | a7 | 13 | 6.385 | 0.491 |
| dot_W16_K8_STYLE1_TR1 | k26 | 6 | 1.386 | 0.231 |
| dot_W16_K8_STYLE1_TR2 | k26 | 5 | 1.771 | 0.354 |
| dot_W16_K8_STYLE1_TR99 | k26 | 9 | 2.543 | 0.283 |

A logic level here is a LUT or a CARRY cell, so one adder is several levels; the per-level figure is the whole path (clock to output, logic and routing, setup excluded) divided by the levels, not a cell delay. It is a budgeting number for this flow and these parts, not a cell delay from the data sheet.

## 5. Other slice features (one point each)

| point | part | slices | LUT | latency | MHz | slice properties |
| --- | --- | --- | --- | --- | --- | --- |
| pre-adder with AD register | a7 | 1 | 0 | 4 | 464 | ADREG=1, USE_SIMD=ONE48, USE_PATTERN_DETECT=NO_PATDET |
| pre-adder with AD register | k26 | 1 | 0 | 4 | 837 | ADREG=1, USE_SIMD=ONE48, USE_PATTERN_DETECT=NO_PATDET |
| pre-adder, no AD register | a7 | 1 | 0 | 3 | 290 | ADREG=0, USE_SIMD=ONE48, USE_PATTERN_DETECT=NO_PATDET |
| pre-adder, no AD register | k26 | 1 | 0 | 3 | 500 | ADREG=0, USE_SIMD=ONE48, USE_PATTERN_DETECT=NO_PATDET |
| SIMD (four lane adds, use_dsp simd) | a7 | 0 | 48 | 2 | 462 | no slice |
| SIMD (four lane adds, use_dsp simd) | k26 | 0 | 48 | 2 | >= 1126 | no slice |
| accumulator with constant compare | a7 | 1 | 0 | 3 | 393 | ADREG=1, USE_SIMD=ONE48, USE_PATTERN_DETECT=PATDET |
| accumulator with constant compare | k26 | 1 | 0 | 3 | 743 | ADREG=1, USE_SIMD=ONE48, USE_PATTERN_DETECT=PATDET |

The SIMD coding was **not** mapped to a slice on either part (fabric adders instead); the pattern-detect compare was. What AMD documents (brief 197): UG901 v2025.2 p. 73 gives `use_dsp = "simd"` as a value that puts SIMD structures into DSP blocks and refers to the templates, without a device list or conditions; UG479 v1.10 (ch. 3 notes, pdf p. 52) recommends the SIMD mode for a large number of small adds with their input registers folded into the slice, and UG479 and UG579 give four 12-bit lanes as the narrowest mode. Vivado 2025.2's SIMD language template (Verilog) puts the attribute on the **module**, takes four 10-bit operands as unpacked arrays and registers both the inputs and the outputs around the adds. Our test put the attribute on one 48-bit signal, sliced a packed vector into four 12-bit lanes, and had one instance. It is not known whether the coding, the signal-level attribute, the single instance or Vivado 2026.1 is why it did not map; the template coding was not run (the heavy-slot queue was full; the four variants and a Tcl driver are in the planner's research folder, `_handoff/fpga_agent/research/197_simd_probe/`).

## House rules (owner-confirmed 2026-11-23, brief 197)

Rules 1, 2, 4, 5, 7 and 8 as drafted in brief 185's report; rules 3 and 6 are reworded after checking AMD's documents (citations below; page numbers are PDF pages of the copies in `~/Claude_sandbox/_amd_docs`).

1. **A DSP multiply that must run at a high clock gets all three registers written in the RTL: operand, multiplier, output (latency 3).** Fmax by register count 0 to 4 (best of each): a7 175, 319, 327, 464, 464 MHz; k26 354, 571, 678, 837, 837 MHz (table 1b). Which three matters. The data-sheet figure is the ceiling at sign-off.
2. **A single register after a multiply is the multiplier register; do not count on the output register** unless all three are written or the slice accumulates.
3. **No asynchronous reset or set on any register meant to go into a slice.** AMD: the slice's registers have synchronous resets only and no sets (UG479 v1.10 Table 2-4 and UG579 v1.11 Table 3-4, each register "reset synchronously by RSTx"; UG949 v2025.2 ch. 3, pp. 51, 53-54 and 69; UG901 v2025.2 p. 85, "sequential functionality in ... DSP blocks can be set or reset synchronously only"). An asynchronous reset on a register keeps it out of the slice register or is rebuilt in fabric: UG949's example (p. 53) gives AREG/BREG = 0, MREG = 0, PREG = 1 plus extra flip-flops and LUT2s. Measured here the same way: a lone register with an asynchronous reset went to PREG with MREG = 0 at 199 MHz on a7 (440 on k26) against 319 (614) with a synchronous reset; with all three registers written and the reset only on the output, A, M and P stayed in the slice but the reset was rebuilt in 36 LUTs on a7 (35 on k26) at the output, with no loss of speed in this test. So: it either breaks the packing or costs LUTs.
4. **A multiply wider than one slice:** let the tool split it only when speed does not matter; when it does, write the cascade (17-bit shift on the narrow port) or accept the slower fabric sum; say which in the datasheet.
5. **A dot product or filter sum:** choose by what the user needs and state it: registered adder tree (fewer clocks; fabric adders limit speed on Artix-7) or cascade (slice limit, one stage per term); on UltraScale+ check that the skew registers did not become SRL cells.
6. **The pre-adder gets its own AD register at speed**: a7 464 against 290 MHz without it (the data sheet's no-ADREG figure at -1 is 290.44, DS181 Table 31), k26 837 against 500. **Do not rely on `use_dsp = "simd"` for small adds.** UG901 v2025.2 (p. 73) names the value but gives no device list or conditions (it points to the Vivado templates); UG479 recommends SIMD for many small adds with their input registers in the slice. Our test of four 12-bit adds did not map on either part under Vivado 2026.1 (coding differs from AMD's template: attribute on a signal, packed vector, one instance; the template coding was not run). When four lanes are needed, instantiate the DSP48E1 / DSP48E2 with USE_SIMD = FOUR12, or check the synthesis report for the slice.
7. **Every datasheet states for a DSP block** latency (register stages from input to output), slices, and MHz with the part, speed grade, Vivado version and target clock; "464 MHz" alone is the slice, not the design.
8. **The advisory `dsp_regs` check is run before sign-off;** a deliberately slow datapath waives it with a reason.

Sources for 3 and 6: UG479 v1.10 (Table 2-4 register descriptions; ch. 3 "Miscellaneous Notes and Suggestions", pdf p. 52, SIMD for many small adds); UG579 v1.11 (Table 3-4); UG901 v2025.2 (USE_DSP, p. 73; "Pre-Adders in the DSP Block", p. 103; flip-flop "Coding Guidelines", p. 85); UG949 v2025.2 (ch. 3 reset section, pp. 51-54; "Coding for Optimal DSP and Arithmetic Inference", pp. 68-69); Vivado 2025.2 Language Templates (Verilog, "SIMD"). UG901 and UG949 are the 2025.2 documents; the runs were made with Vivado 2026.1, for which no newer copy of those guides is held here.

## Records

- `data/a7.json`, `data/k26.json`: one entry per point (status, parameters, latency, slices, LUT, FF, carry cells, WNS, WHS, WPWS, setup Fmax, slice minimum period, Fmax and what bound it, logic levels, path delay, per-level delay, DSP cell properties, DSP/DRC lines). Tool: Vivado 2026.1 (build 6511674), date in each file.
- `raw/<part>/<point>/`: `dsp_cells.txt`, `synth_dsp_report.txt` (the synthesis log's DSP Report for the point), `dsp_lines_methodology_drc.txt`, `timing_worst_setup.rpt`, `pulse_width_checks.txt`.

## Reproduce

Each command is run from the repository root with Vivado 2026.1 on the path the flow pins (`python3 flow/version_pin.py --vivado`); a run holds one heavy slot and one thread.

```
python3 results/185_dsp_slices/run_dsp.py list --part a7          # the points
python3 results/185_dsp_slices/run_dsp.py run --part a7 --group mul   # groups: mul dot feat wide; takes a heavy slot (prefix 185), about an hour for wide
python3 results/185_dsp_slices/run_dsp.py parse --part a7         # rebuild data/a7.json from build/185_dsp
python3 results/185_dsp_slices/make_readme.py                      # rewrite this file from the data
python3 tools/dsp_regs_limits.py                                   # regenerate flow/dsp_regs_limits.json
python3 -m pytest -q flow/tests/test_185_dsp_regs.py site/tests
```

## What is in this folder

- `rtl/`: `dsp_mul_pipe`, `dsp_wide_mul`, `dsp_dot`, `dsp_preadd`, `dsp_simd_pat` and their `_ooc` wrappers. `tb/`: Icarus benches for the modules (random operands, find the latency at which the output matches; run with `iverilog -g2012`, commands in each bench's header).
- `dsp_char.tcl`, `run_dsp.py`, `build_all.sh`: the Vivado session, the point lists, and the sweep (`python3 results/185_dsp_slices/run_dsp.py list|run|parse`); heavy jobs take a slot with prefix 185. `make_readme.py` writes this file.
- Related: `flow/dsp_regs_check.py` (advisory check, brief 185), `flow/dsp_regs_limits.json` (generated by `tools/dsp_regs_limits.py` from `data/`), `site/dsp_figures.py` and the `dsp_slices` area of `site/data/expertise.yaml`.

## Known gaps and limits

- **VU2P not licensed here**: the Alveo UL3524 part `xcvu2p-fsvj2104-3-e` is refused by the installed Basic licence (source: `results/186_ul3524/licence.md` on branch `b186-ul3524`, brief 186), so there is no third part and nothing on what its -3 grade buys.
- One run per point; no repeats. Targets (1.8 ns, 1.0 ns) were chosen to be tighter than the parts meet; achieved slack depends on tool effort at that target.
- Narrow operands for the register study (18 x 18; 25 x 18 and 27 x 18 native widths are in the data at full depth only); no accumulate, no C-port or carry-in use, no 96-bit accumulate, no time multiplexing.
- An asynchronous reset on a lone register moved it into PREG (multiplier left unregistered): this is what AMD's UG949 (v2025.2, p. 53) describes for an asynchronous reset on slice registers, so it is not an oddity of this flow; the rebuilt reset (LUTs at the output when all three registers are written) is measured at one point only.
- The cascade, dot and wide styles are one coding each; a different coding could change slice counts (for example the cascade used more slices than the tool's split at 44 x 35 on k26).
- Methodology DRC rows (DPIP-1, DPOP-1, DPOP-2) are recorded per point in `raw/`; they flag unregistered slices but not how fast the slice then runs.
- Slice limits are best cases of few runs: `flow/dsp_regs_limits.json` is advisory, not a guarantee.

## Next steps

- Repeat points to get a spread; add accumulate and wide-accumulator points; run the SIMD variants in `_handoff/fpga_agent/research/197_simd_probe/` (AMD's template coding against ours); measure the UltraScale+ cascade with the skew lines forced into the slices' input registers.
- Run the agent on a task that needs slice usage and see whether the advisory check changes its design (no agent run uses it yet).

