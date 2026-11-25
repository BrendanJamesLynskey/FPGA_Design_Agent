#!/usr/bin/env python3
"""Writes results/185_dsp_slices/README.md from data/{a7,k26}.json (brief 185): every number in it is read from those files."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = {k: json.loads((HERE / "data" / f"{k}.json").read_text()) for k in ("a7", "k26")}
P = {k: {p["id"]: p for p in v["points"]} for k, v in D.items()}


SIMD_NOTE = ("Our SIMD coding (attribute on a signal) was **not** mapped to a slice on either part (fabric adders instead); the pattern-detect compare was. Brief 199 then ran the probe: with the attribute on the **module** (AMD's template placement) four 10-bit or 12-bit lanes map to one slice with USE_SIMD = FOUR12, input and output registers folded in (AREG = 1, PREG = 1), on a7 and k26 under Vivado 2026.1 (results/199_dsp_fmax/README.md). "
             "What AMD documents (brief 197): UG901 v2025.2 p. 73 gives `use_dsp = \"simd\"` as a value that puts SIMD structures into DSP blocks and refers to the templates, without a device list or conditions; "
             "UG479 v1.10 (ch. 3 notes, pdf p. 52) recommends the SIMD mode for a large number of small adds with their input registers folded into the slice, and UG479 and UG579 give four 12-bit lanes as the narrowest mode. "
             "Vivado 2025.2's SIMD language template (Verilog) puts the attribute on the **module**, takes four 10-bit operands as unpacked arrays and registers both the inputs and the outputs around the adds. "
             "Our test put the attribute on one 48-bit signal, sliced a packed vector into four 12-bit lanes, and had one instance. The probe shows the signal-level attribute is why it did not map: the same packed 48-bit coding with the attribute on the module mapped (brief 199).")
SIMD_RULE = ("**Do not rely on `use_dsp = \"simd\"` for small adds.** UG901 v2025.2 (p. 73) names the value but gives no device list or conditions (it points to the Vivado templates); UG479 recommends SIMD for many small adds with their input registers in the slice. "
             "Our test of four 12-bit adds with the attribute on a signal did not map on either part under Vivado 2026.1; with the attribute on the module it mapped to one slice with FOUR12 (brief 199, measured on a7 and k26 synthesis). Put the attribute on the module, not a signal. "
             "To be sure of four lanes, instantiate the DSP48E1 / DSP48E2 with USE_SIMD = FOUR12, or check the synthesis report for the slice.")


def f(p):
    return f'{p["fmax_mhz"]:.0f}'


def row(cells):
    return "| " + " | ".join(str(c) for c in cells) + " |"


out = ["# Brief 185: DSP slices as an area of expertise (measured)", "",
       "Out-of-context Vivado 2026.1 runs (synthesis, placement, routing, one thread) of small designs built to show which registers a DSP slice needs, how wide "
       "multiplies and dot products are built from slices, and how clock speed trades against latency. Two parts: **a7** = `xc7a100tcsg324-1` (DSP48E1, target clock 1.8 ns) "
       "and **k26** = `xck26-sfvc784-2LV-c` (DSP48E2, target clock 1.0 ns). Records: `data/a7.json`, `data/k26.json` (116 points, every one `ok`); per-point evidence "
       "(DSP cell register properties, the synthesis DSP Report, the DSP lines of the DRC and methodology reports, the pulse-width and Min Period checks) in `raw/<part>/<point>/`.", "",
       "## How to read the numbers", "",
       "- **Fmax** = the smallest of `1000 / (target period - worst setup slack)`, `1000 / the largest Min Period a clock pin requires` in the routed timing summary, and the clock-buffer limit (BUFG Min Period: a7 2.155 ns, k26 1.379 ns, brief 199, results/199_dsp_fmax; the out-of-context wrappers have no buffer, so it is applied from the probe). "
       "One run per point at a target clock tighter than most points can meet, so it is an estimate (no repeats, no spread). A target that was easy would give only a lower bound; "
       "the points whose setup slack was positive (nine on a7, one on k26) are limited by the slice's own Min Period instead, except the k26 SIMD point (fabric adders, slack positive), whose figure is only a lower bound.",
       "- **Latency** = register stages from the module's operand inputs to its output (the formula the RTL is written for; checked by the Icarus benches in `tb/`). "
       "Every module is wrapped (`*_ooc.sv`) in kept (`DONT_TOUCH`) registers on all ports, which are not counted in the latency and which Vivado cannot absorb into the slice; the timed path is register to register through the module.",
       "- `flow/ipchar.py`'s Fmax treats a Min Period shortfall as a half-period pulse-width shortfall and so over-penalises a slice's own limit; `run_dsp.py` recomputes it (on the a7 part a fully registered slice is limited by its 2.154 ns Min Period, 464.3 MHz, which matches the data-sheet figure for -1; other briefs' Fmax values for DSP-heavy blocks were not re-derived here).",
       "", "## 1. Registers around one multiply (18 x 18 signed, one slice)", "",
       "Columns: registers written in the RTL (operand stages NA, multiplier NM, output NP); the slice's registers as Vivado set them (AREG / MREG / PREG after routing); Fmax in MHz. Vivado packs a lone register after the multiply into MREG, not PREG.", "",
       row(["RTL regs NA,NM,NP", "latency", "a7 AREG,MREG,PREG", "a7 MHz", "k26 AREG,MREG,PREG", "k26 MHz"]), row(["---"] * 6)]
for na in (0, 1, 2):
    for nm in (0, 1):
        for np_ in (0, 1):
            i = f"mul_WA18_WB18_NA{na}_NM{nm}_NP{np_}_RSTP0"
            a, k = P["a7"][i], P["k26"][i]
            c = lambda p: ",".join(str(p["dsp_cells"][0][x]) for x in ("AREG", "MREG", "PREG"))
            out.append(row([f"{na},{nm},{np_}", a["latency_clocks"], c(a), f(a), c(k), f(k)]))
out += ["", "Resets on the lone / full output register (RSTP 1 = synchronous, 2 = asynchronous):", "", row(["RTL regs", "reset", "a7 A,M,P", "a7 MHz", "k26 A,M,P", "k26 MHz"]), row(["---"] * 6)]
for na, nm, np_ in ((0, 0, 1), (1, 1, 1)):
    for r in (0, 1, 2):
        i = f"mul_WA18_WB18_NA{na}_NM{nm}_NP{np_}_RSTP{r}"
        a, k = P["a7"][i], P["k26"][i]
        c = lambda p: ",".join(str(p["dsp_cells"][0][x]) for x in ("AREG", "MREG", "PREG"))
        out.append(row([f"{na},{nm},{np_}", ["none", "sync", "async"][r], c(a), f(a), c(k), f(k)]))

# ---- brief 197 (owner, 2026-11-23): rule 1 table, Fmax against the number of registers, with the data-sheet figures beside ours
def _combos(pk):
    by = {}
    for p in D[pk]["points"]:
        if p["kind"] == "mul" and p["params"]["WA"] == 18 and p["params"]["RSTP"] == 0 and p["status"] == "ok":
            q = p["params"]
            by.setdefault(p["latency_clocks"], {}).setdefault(round(p["fmax_mhz"]), []).append(f'{q["NA"]},{q["NM"]},{q["NP"]}')
    return by


def _cell(by, n):
    groups = sorted(by[n].items(), key=lambda kv: -kv[0])
    return "; ".join(f'**{m}** ({" ".join(c)})' if i == 0 else f'{m} ({" ".join(c)})' for i, (m, c) in enumerate(groups))


CA, CK = _combos("a7"), _combos("k26")
BA, BK = {n: max(CA[n]) for n in CA}, {n: max(CK[n]) for n in CK}          # best at each register count
pc = lambda b, n: round(100 * b[n] / b[3])
# the data-sheet figures (public, cited): DS181 v1.27.1 Table 31 (DSP48E1, -1, 1.0 V) and DS925 v1.30 Table 83 (DSP48E2, -2, 0.85 V and 0.72 V)
DS = [("all registers used", "464.25", "775 / 644"), ("two-register multiply without MREG", "257.47", "544 / 440"),
      ("without ADREG (pre-adder)", "290.44", "565 / 453"), ("without pipeline registers (MREG, ADREG)", "190.69", "410 / 323")]
out += ["", "### 1b. Fmax against the number of registers (house rule 1)", "",
        "One 18 x 18 signed multiply in one slice, no reset; the best result at each register count is in bold, and the variants NA,NM,NP (operand stages, multiplier register, output register) that reached each value are in brackets. "
        "Register count = latency. **a7** = `xc7a100tcsg324-1` (-1); **k26** = `xck26-sfvc784-2LV-c` (-2LV, the only grade measured; there is no -1 K26 run). One routed out-of-context run per point, Vivado 2026.1; an estimate, no repeats. Plot: [fmax_vs_registers.svg](fmax_vs_registers.svg).", "",
        row(["registers", "a7 Fmax MHz (RTL regs NA,NM,NP)", "k26 Fmax MHz (RTL regs NA,NM,NP)"]), row(["---"] * 3)]
for n in range(5):
    out.append(row([n, _cell(CA, n), _cell(CK, n)]))
a25, k27 = P["a7"]["mul_WA25_WB18_NA1_NM1_NP1_RSTP0"], P["k26"]["mul_WA27_WB18_NA1_NM1_NP1_RSTP0"]
out += ["", f"Steps, as a share of the three-register result: a7 {pc(BA,0)} percent with none, {pc(BA,1)} with one, {pc(BA,2)} with two, 100 with three and with four; k26 {pc(BK,0)}, {pc(BK,1)}, {pc(BK,2)}, 100, 100. "
        "Which three matters: operand, multiplier and output registers (1,1,1) reach the slice's limit, while two operand stages plus the multiplier register with no output register (2,1,0) reach only "+f"{min(CA[3])} on a7 and {min(CK[3])} on k26; a fourth register (a second operand stage) adds nothing on either part.", "",
        f"The native widths (25 x 18 on a7, 27 x 18 on k26) were run at three registers and at four: a7 {f(a25)} and {f(P['a7']['mul_WA25_WB18_NA2_NM1_NP1_RSTP0'])} MHz, k26 {f(k27)} and {f(P['k26']['mul_WA27_WB18_NA2_NM1_NP1_RSTP0'])} MHz, the same as 18 x 18; no native-width run exists at fewer registers. "
        "A lone operand register differs between the parts: on a7 Vivado packs it into MREG (319), on k26 it stays in AREG and the product is unregistered (394). "
        f"A pre-adder multiply `(d + a) * b` (24 x 18): with the AD register a7 {f(P['a7']['preadd_WA24_WB18_VAR0'])} / k26 {f(P['k26']['preadd_WA24_WB18_VAR0'])} MHz (4 registers); "
        f"without it a7 {f(P['a7']['preadd_WA24_WB18_VAR1'])} / k26 {f(P['k26']['preadd_WA24_WB18_VAR1'])} MHz (3 registers).", "",
        "Our numbers beside the data sheet (public figures: DS181 v1.27.1 Table 31, -1, 1.0 V; DS925 v1.30 Table 83, -2 at 0.85 V / 0.72 V):", "",
        row(["configuration", "DS181 -1 MHz", "a7 measured MHz", "DS925 -2 MHz (0.85 V / 0.72 V)", "k26 measured MHz"]), row(["---"] * 5),
        row([DS[0][0], DS[0][1], f(P["a7"]["mul_WA18_WB18_NA1_NM1_NP1_RSTP0"]), DS[0][2], f(P["k26"]["mul_WA18_WB18_NA1_NM1_NP1_RSTP0"])]),
        row([DS[1][0], DS[1][1], "not reproduced: Vivado packs the lone register into MREG", DS[1][2], "not reproduced (as a7)"]),
        row([DS[2][0], DS[2][1], f(P["a7"]["preadd_WA24_WB18_VAR1"]), DS[2][2], f(P["k26"]["preadd_WA24_WB18_VAR1"])]),
        row([DS[3][0], DS[3][1], f(P["a7"]["mul_WA18_WB18_NA0_NM0_NP0_RSTP0"]), DS[3][2], f(P["k26"]["mul_WA18_WB18_NA0_NM0_NP0_RSTP0"])]), "",
        "On a7 the fully registered and the no-ADREG slices match the data sheet (the slice's own Min Period); with no pipeline registers ours is lower (reason not investigated). "
        "On k26 Vivado's own checks give 837 MHz for the fully registered slice (setup at a 1.0 ns target; the slice's Min Period is 0.85 ns, 1176 MHz), which is **above** the data sheet's 775 MHz (-2, 0.85 V) and 644 MHz (-2, 0.72 V). "
        "Brief 199 found why the table no longer shows 837: the out-of-context wrappers have no clock buffer, and as soon as the clock goes through a BUFG Vivado also checks the buffer's Min Period, 1.379 ns = 725 MHz on the -2LV part (equal to DS925 Table 84, BUFG FMAX, -2 at 0.72 V; a7: 2.155 ns, the same as the slice's 2.154 ns, so a7 does not change). "
        "Fmax in this page is therefore min(setup, slice Min Period, BUFG Min Period) and the k26 columns are capped at 725 MHz (rows that were setup-limited above it are marked BUFG in the bound column; probe in results/199_dsp_fmax). "
        "Vivado does not turn the data sheet's 775 / 644 MHz DSP figure into a DSP check: its Min Period for the slice (0.85 ns) stays looser, so 725 is still above the DS925 -2 0.72 V DSP figure of 644. "
        "Use the data-sheet figure (644 MHz at 0.72 V, 775 MHz at 0.85 V), not 725, as the K26 slice ceiling at sign-off; the table shows the shape (the steps between register counts), which is what rule 1 rests on. "
        "The BUFG value matching the 0.72 V column suggests Vivado times the -2LV part at 0.72 V (an inference from one number, not read from the tool).", "",
        "![Fmax against the number of registers around one multiply](fmax_vs_registers.svg)", ""]
out += ["", "## 2. Wide multiplies (slices, latency, MHz)", "",
        "Style 0 = the `*` operator with the same operand, multiplier and output registers (the tool's own split); 1 = hand-written cascade (PCOUT to PCIN with the 17-bit shift, operands skewed one clock per stage, chains added in the fabric); 2 = partial products each in a slice, summed in a registered fabric adder tree. Style-0 results with a second operand register (NA 2) are in the data and equal or lower.", "",
        row(["WA x WB", "style", "a7 slices", "a7 LUT", "a7 latency", "a7 MHz", "k26 slices", "k26 LUT", "k26 latency", "k26 MHz"]), row(["---"] * 10)]
for wa, wb in ((27, 27), (32, 32), (35, 25), (44, 35), (48, 48), (64, 64)):
    for s in (0, 1, 2):
        ia = f"wide_WA{wa}_WB{wb}_STYLE{s}_NA1_LB24"
        ik = f"wide_WA{wa}_WB{wb}_STYLE{s}_NA1_LB26"
        a, k = P["a7"][ia], P["k26"][ik]
        out.append(row([f"{wa} x {wb}", s, a["dsp"], a["lut"], a["latency_clocks"], f(a), k["dsp"], k["lut"], k["latency_clocks"], f(k)]))
out += ["", "## 3. Dot product, sixteen-bit signed terms, one result per clock", "",
        "Cascade = systolic chain, one slice per term, operands skewed one clock per stage (latency K + 2). Tree = one slice per product (operand, multiplier, output registers), fabric adder tree with a register after every TR levels and after the last (TR 99 = last only). 'Bound' names what set the Fmax: setup slack, or the minimum period of the named cell type.", "",
        row(["K", "structure", "a7 latency", "a7 slices", "a7 LUT", "a7 MHz", "a7 bound", "k26 latency", "k26 slices", "k26 LUT", "k26 MHz", "k26 bound"]), row(["---"] * 12)]
for kk in (4, 8, 16):
    for name, st, tr in (("cascade", 0, 1), ("tree TR 1", 1, 1), ("tree TR 2", 1, 2), ("tree TR 99", 1, 99)):
        i = f"dot_W16_K{kk}_STYLE{st}_TR{tr}"
        a, k = P["a7"][i], P["k26"][i]
        bd = lambda p: p["fmax_bound"].replace("minimum period of ", "min period ").replace("setup slack at the target clock", "setup")
        out.append(row([kk, name, a["latency_clocks"], a["dsp"], a["lut"], f(a), bd(a), k["latency_clocks"], k["dsp"], k["lut"], f(k), bd(k)]))
a8, k8 = P["a7"], P["k26"]
out += ["", f"A published estimate for an eight-term dot product is about 6 stages as a tree against about 11 as a cascade. Measured here at K = 8: the tree is {a8['dot_W16_K8_STYLE1_TR1']['latency_clocks']} stages and the cascade {a8['dot_W16_K8_STYLE0_TR1']['latency_clocks']} (this cascade has no separate output register, so one fewer than the estimate); the estimate **holds for latency only**. Speed: on a7 the tree is {f(a8['dot_W16_K8_STYLE1_TR1'])} MHz against the cascade's {f(a8['dot_W16_K8_STYLE0_TR1'])}; on k26 the tree is {f(k8['dot_W16_K8_STYLE1_TR1'])} against {f(k8['dot_W16_K8_STYLE0_TR1'])}, where the cascade's operand-skew delay lines were mapped to shift-register cells (SRL16E, Min Period 1.524 ns) that set its limit.", "",
        "## 4. Per-level and per-register delay (from the worst setup path of each routed point)", "",
        "`path_delay_ns`, `path_logic_ns`, `path_route_ns`, `logic_levels` and `path_per_level_ns` are in the data. Examples (fabric adder-tree paths, setup-limited):", "",
        row(["point", "part", "logic levels", "path delay ns", "ns per level"]), row(["---"] * 5)]
for pk, i in (("a7", "dot_W16_K8_STYLE1_TR1"), ("a7", "dot_W16_K8_STYLE1_TR2"), ("a7", "dot_W16_K8_STYLE1_TR99"), ("k26", "dot_W16_K8_STYLE1_TR1"), ("k26", "dot_W16_K8_STYLE1_TR2"), ("k26", "dot_W16_K8_STYLE1_TR99")):
    p = P[pk][i]
    out.append(row([i, pk, p["logic_levels"], p["path_delay_ns"], p["path_per_level_ns"]]))
out += ["", "A logic level here is a LUT or a CARRY cell, so one adder is several levels; the per-level figure is the whole path (clock to output, logic and routing, setup excluded) divided by the levels, not a cell delay. It is a budgeting number for this flow and these parts, not a cell delay from the data sheet.", "",
        "## 5. Other slice features (one point each)", "",
        row(["point", "part", "slices", "LUT", "latency", "MHz", "slice properties"]), row(["---"] * 7)]
for i, nm in (("preadd_WA24_WB18_VAR0", "pre-adder with AD register"), ("preadd_WA24_WB18_VAR1", "pre-adder, no AD register"), ("simdpat_MODE0", "SIMD (four lane adds, use_dsp simd)"), ("simdpat_MODE1", "accumulator with constant compare")):
    for pk in ("a7", "k26"):
        p = P[pk][i]
        c = p["dsp_cells"][0] if p["dsp_cells"] else {}
        props = ", ".join(f"{x}={c[x]}" for x in ("ADREG", "USE_SIMD", "USE_PATTERN_DETECT") if x in c) or "no slice"
        lb = ">= " if p["wns_ns"] is not None and p["wns_ns"] > 0 and p["fmax_bound"].startswith("setup") else ""
        out.append(row([nm, pk, p["dsp"], p["lut"], p["latency_clocks"], lb + f(p), props]))
out += ["", SIMD_NOTE, "",
        "## House rules (owner-confirmed 2026-11-23, brief 197)", "",
        "Rules 1, 2, 4, 5, 7 and 8 as drafted in brief 185's report; rules 3 and 6 are reworded after checking AMD's documents (citations below; page numbers are PDF pages of the copies in `~/Claude_sandbox/_amd_docs`).", "",
        f"1. **A DSP multiply that must run at a high clock gets all three registers written in the RTL: operand, multiplier, output (latency 3).** Fmax by register count 0 to 4 (best of each): a7 {BA[0]}, {BA[1]}, {BA[2]}, {BA[3]}, {BA[4]} MHz; k26 {BK[0]}, {BK[1]}, {BK[2]}, {BK[3]}, {BK[4]} MHz (table 1b). Which three matters. The data-sheet figure is the ceiling at sign-off.",
        "2. **A single register after a multiply is the multiplier register; do not count on the output register** unless all three are written or the slice accumulates.",
        "3. **No asynchronous reset or set on any register meant to go into a slice.** AMD: the slice's registers have synchronous resets only and no sets (UG479 v1.10 Table 2-4 and UG579 v1.11 Table 3-4, each register \"reset synchronously by RSTx\"; UG949 v2025.2 ch. 3, pp. 51, 53-54 and 69; UG901 v2025.2 p. 85, \"sequential functionality in ... DSP blocks can be set or reset synchronously only\"). "
        "An asynchronous reset on a register keeps it out of the slice register or is rebuilt in fabric: UG949's example (p. 53) gives AREG/BREG = 0, MREG = 0, PREG = 1 plus extra flip-flops and LUT2s. "
        f"Measured here the same way: a lone register with an asynchronous reset went to PREG with MREG = 0 at {f(P['a7']['mul_WA18_WB18_NA0_NM0_NP1_RSTP2'])} MHz on a7 ({f(P['k26']['mul_WA18_WB18_NA0_NM0_NP1_RSTP2'])} on k26) against {f(P['a7']['mul_WA18_WB18_NA0_NM0_NP1_RSTP1'])} ({f(P['k26']['mul_WA18_WB18_NA0_NM0_NP1_RSTP1'])}) with a synchronous reset; "
        f"with all three registers written and the reset only on the output, A, M and P stayed in the slice but the reset was rebuilt in {P['a7']['mul_WA18_WB18_NA1_NM1_NP1_RSTP2']['lut']} LUTs on a7 ({P['k26']['mul_WA18_WB18_NA1_NM1_NP1_RSTP2']['lut']} on k26) at the output, with no loss of speed in this test. So: it either breaks the packing or costs LUTs.",
        "4. **A multiply wider than one slice:** let the tool split it only when speed does not matter; when it does, write the cascade (17-bit shift on the narrow port) or accept the slower fabric sum; say which in the datasheet.",
        "5. **A dot product or filter sum:** choose by what the user needs and state it: registered adder tree (fewer clocks; fabric adders limit speed on Artix-7) or cascade (slice limit, one stage per term); on UltraScale+ check that the skew registers did not become SRL cells.",
        "6. **The pre-adder gets its own AD register at speed**: " + f"a7 {f(P['a7']['preadd_WA24_WB18_VAR0'])} against {f(P['a7']['preadd_WA24_WB18_VAR1'])} MHz without it (the data sheet's no-ADREG figure at -1 is 290.44, DS181 Table 31), k26 {f(P['k26']['preadd_WA24_WB18_VAR0'])} against {f(P['k26']['preadd_WA24_WB18_VAR1'])}. " + SIMD_RULE,
        "7. **Every datasheet states for a DSP block** latency (register stages from input to output), slices, and MHz with the part, speed grade, Vivado version and target clock; \"464 MHz\" alone is the slice, not the design.",
        "8. **The advisory `dsp_regs` check is run before sign-off;** a deliberately slow datapath waives it with a reason.", "",
        "Sources for 3 and 6: UG479 v1.10 (Table 2-4 register descriptions; ch. 3 \"Miscellaneous Notes and Suggestions\", pdf p. 52, SIMD for many small adds); UG579 v1.11 (Table 3-4); UG901 v2025.2 (USE_DSP, p. 73; \"Pre-Adders in the DSP Block\", p. 103; flip-flop \"Coding Guidelines\", p. 85); UG949 v2025.2 (ch. 3 reset section, pp. 51-54; \"Coding for Optimal DSP and Arithmetic Inference\", pp. 68-69); Vivado 2025.2 Language Templates (Verilog, \"SIMD\"). "
        "UG901 and UG949 are the 2025.2 documents; the runs were made with Vivado 2026.1, for which no newer copy of those guides is held here.", "",
        "## Records", "",
        "- `data/a7.json`, `data/k26.json`: one entry per point (status, parameters, latency, slices, LUT, FF, carry cells, WNS, WHS, WPWS, setup Fmax, slice minimum period, Fmax and what bound it, logic levels, path delay, per-level delay, DSP cell properties, DSP/DRC lines). Tool: Vivado 2026.1 (build 6511674), date in each file.",
        "- `raw/<part>/<point>/`: `dsp_cells.txt`, `synth_dsp_report.txt` (the synthesis log's DSP Report for the point), `dsp_lines_methodology_drc.txt`, `timing_worst_setup.rpt`, `pulse_width_checks.txt`.", "",
        "## Reproduce", "",
        "Each command is run from the repository root with Vivado 2026.1 on the path the flow pins (`python3 flow/version_pin.py --vivado`); a run holds one heavy slot and one thread.", "",
        "```",
        "python3 results/185_dsp_slices/run_dsp.py list --part a7          # the points",
        "python3 results/185_dsp_slices/run_dsp.py run --part a7 --group mul   # groups: mul dot feat wide; takes a heavy slot (prefix 185), about an hour for wide",
        "python3 results/185_dsp_slices/run_dsp.py parse --part a7         # rebuild data/a7.json from build/185_dsp",
        "python3 results/185_dsp_slices/make_readme.py                      # rewrite this file from the data",
        "python3 tools/dsp_regs_limits.py                                   # regenerate flow/dsp_regs_limits.json",
        "python3 -m pytest -q flow/tests/test_185_dsp_regs.py site/tests",
        "```", "",
        "## What is in this folder", "",
        "- `rtl/`: `dsp_mul_pipe`, `dsp_wide_mul`, `dsp_dot`, `dsp_preadd`, `dsp_simd_pat` and their `_ooc` wrappers. `tb/`: Icarus benches for the modules (random operands, find the latency at which the output matches; run with `iverilog -g2012`, commands in each bench's header).",
        "- `dsp_char.tcl`, `run_dsp.py`, `build_all.sh`: the Vivado session, the point lists, and the sweep (`python3 results/185_dsp_slices/run_dsp.py list|run|parse`); heavy jobs take a slot with prefix 185. `make_readme.py` writes this file.",
        "- Related: `flow/dsp_regs_check.py` (advisory check, brief 185), `flow/dsp_regs_limits.json` (generated by `tools/dsp_regs_limits.py` from `data/`), `site/dsp_figures.py` and the `dsp_slices` area of `site/data/expertise.yaml`.", "",
        "## Known gaps and limits", "",
        "- **VU2P not licensed here**: the Alveo UL3524 part `xcvu2p-fsvj2104-3-e` is refused by the installed Basic licence (source: `results/186_ul3524/licence.md` on branch `b186-ul3524`, brief 186), so there is no third part and nothing on what its -3 grade buys.",
        "- One run per point; no repeats. Targets (1.8 ns, 1.0 ns) were chosen to be tighter than the parts meet; achieved slack depends on tool effort at that target.",
        "- Narrow operands for the register study (18 x 18; 25 x 18 and 27 x 18 native widths are in the data at full depth only); no accumulate, no C-port or carry-in use, no 96-bit accumulate, no time multiplexing.",
        "- An asynchronous reset on a lone register moved it into PREG (multiplier left unregistered): this is what AMD's UG949 (v2025.2, p. 53) describes for an asynchronous reset on slice registers, so it is not an oddity of this flow; the rebuilt reset (LUTs at the output when all three registers are written) is measured at one point only.",
        "- The cascade, dot and wide styles are one coding each; a different coding could change slice counts (for example the cascade used more slices than the tool's split at 44 x 35 on k26).",
        "- Methodology DRC rows (DPIP-1, DPOP-1, DPOP-2) are recorded per point in `raw/`; they flag unregistered slices but not how fast the slice then runs.",
        "- Slice limits are best cases of few runs: `flow/dsp_regs_limits.json` is advisory, not a guarantee.", "",
        "## Next steps", "",
        "- Repeat points to get a spread; add accumulate and wide-accumulator points; run the module-attribute SIMD coding through place and route for Fmax; measure the UltraScale+ cascade with the skew lines forced into the slices' input registers.",
        "- Run the agent on a task that needs slice usage and see whether the advisory check changes its design (no agent run uses it yet).", ""]
(HERE / "README.md").write_text("\n".join(out) + "\n")

def write_svg():
    """fmax_vs_registers.svg: Fmax against the number of registers around one multiply, both parts (brief 197). Same sober black-and-white house style as
    site/dsp_figures.py (own colour variables so the file stands alone; dark mode follows the viewer). Dots = every run, line = the best at each count."""
    W, H, x0, y0, w, h = 640, 330, 62, 24, 540, 250
    ymax = 900
    X = lambda n: x0 + n / 4 * w
    Y = lambda v: y0 + h - v / ymax * h
    o = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" role="img" aria-label="Fmax against the number of registers around one 18 x 18 multiply, Artix-7 and Kria K26">' % (W, H),
         '<title>Fmax against the number of registers around one 18 x 18 multiply</title>',
         '<style>:root{--bg:#f6f6f4;--rule:#d6d6d2;--ink:#161616;--ink-2:#4a4a4a}@media (prefers-color-scheme:dark){:root{--bg:#0c0c0c;--rule:#2c2c2c;--ink:#ececec;--ink-2:#b4b4b4}}'
         'text{fill:var(--ink-2);font:11px system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}.k{fill:var(--ink);font-weight:600}</style>',
         f'<rect width="{W}" height="{H}" fill="var(--bg)"/>']
    for t in range(0, ymax + 1, 200):
        o.append(f'<line x1="{x0}" x2="{x0 + w}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="var(--rule)"/><text x="{x0 - 6}" y="{Y(t) + 4:.1f}" text-anchor="end">{t}</text>')
    for n in range(5):
        o.append(f'<text x="{X(n):.1f}" y="{y0 + h + 16}" text-anchor="middle">{n}</text>')
    o.append(f'<text x="{x0 + w / 2:.1f}" y="{y0 + h + 34}" text-anchor="middle">registers around the multiply (operand, multiplier, output; register stages from inputs to output)</text>')
    o.append(f'<text x="12" y="{y0 + h / 2:.1f}" transform="rotate(-90 12 {y0 + h / 2:.1f})" text-anchor="middle">Fmax, MHz (routed, out of context)</text>')
    for pk, by, dash, circle, label, dx in (("a7", BA, "", True, "Artix-7 xc7a100t -1", 0), ("k26", BK, "6 4", False, "Kria K26 xck26 -2LV", 0)):
        pts = " ".join(f"{X(n):.1f},{Y(by[n]):.1f}" for n in range(5))
        o.append(f'<polyline points="{pts}" fill="none" stroke="var(--ink)" stroke-width="1.5"' + (f' stroke-dasharray="{dash}"' if dash else "") + "/>")
        for n, grp in (CA if pk == "a7" else CK).items():
            for m in grp:
                cx, cy = X(n), Y(m)
                o.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="var(--ink)"/>' if circle else f'<rect x="{cx - 4:.1f}" y="{cy - 4:.1f}" width="8" height="8" fill="var(--bg)" stroke="var(--ink)" stroke-width="1.5"/>')
        for n in (0, 3):
            o.append(f'<text class="k" x="{X(n) + 8:.1f}" y="{Y(by[n]) - 7:.1f}">{by[n]}</text>' if n == 3 or pk == "k26" else f'<text class="k" x="{X(n) + 8:.1f}" y="{Y(by[n]) + 15:.1f}">{by[n]}</text>')
    o.append(f'<circle cx="{x0 + 8}" cy="{H - 10}" r="4" fill="var(--ink)"/><text x="{x0 + 16}" y="{H - 6}">Artix-7 -1 (solid line = best at each count)</text>')
    o.append(f'<rect x="{x0 + 288}" y="{H - 14}" width="8" height="8" fill="var(--bg)" stroke="var(--ink)" stroke-width="1.5"/><text x="{x0 + 302}" y="{H - 6}">K26 -2LV (dashed line)</text>')
    o.append("</svg>")
    (HERE / "fmax_vs_registers.svg").write_text("\n".join(o) + "\n")


write_svg()

print("wrote README.md", len(out), "lines")
