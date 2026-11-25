#!/usr/bin/env python3
"""Writes results/185_dsp_slices/README.md from data/{a7,k26}.json (brief 185): every number in it is read from those files."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = {k: json.loads((HERE / "data" / f"{k}.json").read_text()) for k in ("a7", "k26")}
P = {k: {p["id"]: p for p in v["points"]} for k, v in D.items()}


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
       "- **Fmax** = the smaller of `1000 / (target period - worst setup slack)` and `1000 / the largest Min Period a clock pin requires` in the routed timing summary. "
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
out += ["", "The SIMD coding was **not** mapped to a slice on either part (fabric adders instead); the pattern-detect compare was. Why was not investigated.", "",
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
        "- Why an asynchronous reset on a lone register moved it into PREG (multiplier left unregistered) on a7 was not investigated.",
        "- The cascade, dot and wide styles are one coding each; a different coding could change slice counts (for example the cascade used more slices than the tool's split at 44 x 35 on k26).",
        "- Methodology DRC rows (DPIP-1, DPOP-1, DPOP-2) are recorded per point in `raw/`; they flag unregistered slices but not how fast the slice then runs.",
        "- Slice limits are best cases of few runs: `flow/dsp_regs_limits.json` is advisory, not a guarantee.", "",
        "## Next steps", "",
        "- Repeat points to get a spread; add accumulate and wide-accumulator points; investigate the asynchronous-reset and SIMD results; measure the UltraScale+ cascade with the skew lines forced into the slices' input registers.",
        "- Run the agent on a task that needs slice usage and see whether the advisory check changes its design (no agent run uses it yet).", ""]
(HERE / "README.md").write_text("\n".join(out) + "\n")
print("wrote README.md", len(out), "lines")
