# IP library variants: schema and data contract (brief 63A)

An `ip_lib` entry can hold several **implementation variants** behind one contract: the same ports, parameters,
function (bit-exact against the same Python model) and interface protocol. Variants differ only in resources, latency,
throughput and Fmax. The architecture stage (brief 62) reads their measured cost to choose one; the closure loop can
swap one for another as a repair.

This page is the contract between the library and its readers. The reader is `flow/ipvariants.py`; the writer of the
measured data is `flow/ipchar.py`. Code outside the library reads variants only through `flow/ipvariants.py`, so the
file formats below can grow without breaking the planner.

## 1. `ip.yaml`: what an entry declares

Three keys sit beside brief 28's keys (`parameters`, `latency`, `sweep_tested` and the rest):

```yaml
variant_param: IMPL               # the parameter that selects a variant (a string parameter of the top module)
variants:
  dsp_bram:                       # one key per variant; the names are the values of variant_param
    summary: one line, what the variant is
    when: one line, when to pick it
    uses:                         # predicted resources, expressions over the parameters (optional per key)
      dsp: ceil(TAPS / FOLD)
      bram_tiles: 0.5 * (ceil(ceil(TAPS / FOLD) * DATA_W / 36) + ceil(ceil(TAPS / FOLD) * COEF_W / 36))
    latency: FOLD + 8 + clog2(ceil(TAPS / FOLD))      # clocks, an expression; must equal the RTL's own figure
    ii: FOLD + 3                  # initiation interval in clocks (1 = a new input every clock)
    params: {}                    # optional: parameters the variant fixes (none in the first three entries)
characterisation:
  part: xc7a100tcsg324-1          # one file per part: char/<part>.json
  clock_ns: 4.0                   # the target clock of the out-of-context runs
  points:                         # parameter points to measure; every variant is measured at every point
  - {TAPS: 16, DATA_W: 16, COEF_W: 16, FOLD: 4}
```

Rules, checked by `python3 -m flow.ipvariants` and by `python3 flow/net/ipdoc.py --check` (CI):

- `variant_param` is a declared parameter with `type: string`, its `set` equals the variant names, and its default
  is a variant. The RTL top has the same parameter with the same default (ipdoc compares them).
- Every variant has `summary`, `when`, `uses`, `latency` and `ii`. `uses` keys are among `lut`, `ff`, `lutram`,
  `bram_tiles`, `dsp`.
- Expressions use the entry's numeric parameters, `+ - * / // % **`, `ceil`, `floor`, `min`, `max`, `clog2`, `log2`,
  comparisons and `a if c else b`. They are parsed, never executed as code. They must evaluate at the defaults, at every
  `sweep_tested` point and at every characterisation point.
- `characterisation` exists and its file `char/<part>.json` holds an `ok` row (or a recorded failure) for every
  variant at every point; a row's latency and II equal the ip.yaml expressions at that point.
- **Latency is part of the contract only as a declared number.** A variant may have its own latency, but the RTL then
  exposes it (the `fir` top has `LATENCY` and `II` localparams; `dds_awg` and `adc_histogram` keep the same latency in
  every variant) and the tests measure it. A caller reads it and never assumes it.

Selection in RTL: one parameter (`IMPL`) with generate blocks when one top can hold all variants (all three entries
so far). Separate RTL files per variant behind a common wrapper are allowed too; `fir` keeps the folded core
(`fir_fold.sv`, three variants) and the parallel core (`fir_parallel.sv`) in their own files under one wrapper.
`IMPL` is an untyped string parameter (`parameter IMPL = "dsp_bram"`): Icarus Verilog 12 mis-sizes a typed `parameter
string` when it is overridden (an internal assertion), and the untyped form behaves the same in Vivado.

Variants steer synthesis by inference attributes (`use_dsp`, `ram_style`, `rom_style`) and by structure (a registered
read for block RAM, two RAM copies for a third port), never by instantiating a primitive, and never with an IP-catalog
core.

## 2. `char/<part>.json`: what the runner measures

`python3 -m flow.ipchar <block> [<block> ...]` runs every variant at every point in one Vivado batch session
(`flow/ipchar.tcl`): `synth_design -mode out_of_context`, `opt_design`, `place_design`, `route_design`, with a clock of
`clock_ns` on port `clk` and no I/O constraints. Take a heavy slot first; the runner itself runs under
`systemd-run --user --scope -p MemoryMax=6G nice -n 15`, one thread.

```json
{
 "schema": "ipchar/1",
 "block": "fir", "version": "0.1.0", "part": "xc7a100tcsg324-1", "clock_ns": 4.0,
 "tool": "Vivado 2026.1 (build ...)", "date": "2026-11-12",
 "flow": "how the numbers were made, in words",
 "results": [
  {"variant": "dsp_bram", "params": {"TAPS": 16, "DATA_W": 16, "COEF_W": 16, "FOLD": 4},
   "status": "ok",
   "lut": 0, "ff": 0, "lutram": 0, "srl": 0, "bram_tiles": 0.0, "ramb36": 0, "ramb18": 0, "dsp": 0,
   "wns_ns": 0.0, "fmax_mhz": 0.0,
   "power_w": {"total": 0.0, "dynamic": 0.0, "static": 0.0, "confidence": "Low"},
   "latency": 0, "ii": 0}
 ]
}
```

- `params` is the full point without `variant_param` (defaults filled in).
- `status` is `ok`, `not run`, or `error: <first line>`; only `ok` rows carry numbers.
- `bram_tiles` counts 36 Kb tiles (a RAMB18 is 0.5), as the utilisation report does.
- `fmax_mhz = 1000 / (clock_ns - wns_ns)` after routing: an estimate from one run at the target clock, not a closure at
  that frequency. A design far below the target is under-optimised at the target; one far above it was not pushed.
- `power_w` is `report_power` without activity files (vectorless, default toggle rates). It ranks variants; it is not a
  board measurement. `static` is the whole device's static power and is the same for every row on a part.
- Out of context, I/O paths are not timed: WNS covers register-to-register paths inside the block only.

## 3. `flow/ipvariants.py`: the read API for the planner

Plain Python and PyYAML; no Vivado and no simulator.

| Call | Returns |
|---|---|
| `entries_with_variants()` | entry names with a `variants:` block |
| `search(text)` | entries whose name, summary or variant summaries contain every word: the architecture stage searches the library before writing new RTL |
| `variants(block)` | the `variants:` mapping as written |
| `predict(block, variant, params)` | `{"variant", "params", "latency", "ii", "uses": {...}}` at that point, from ip.yaml |
| `measured(block, part=None)` | the rows of `char/<part>.json`, each with `part`, `clock_ns` and `tool` added |
| `variant_costs(block, params=None, part=None, clock_ns=None)` | one row per variant: `predicted` (above), `measured` (the nearest characterised point, with `exact: true` only at that very point) and, with `clock_ns`, `meets_clock` |
| `choose(block, params, part, budget, clock_ns, need_ii, objective)` | the `variant_costs` rows ranked, each with `fits` and `reasons` (over budget, misses the clock, II too large, not characterised) |

`budget` maps the `uses` keys (`lut`, `ff`, `lutram`, `bram_tiles`, `dsp`) to what the plan has left for this block.
`objective` orders the fitting rows: `area` (fewest DSP, then block RAM tiles, then LUTs), `fabric` (fewest LUTs, then
FFs), `throughput` (lowest II, then highest Fmax) or `fmax`. The planner applies brief 62's rule itself: prefer a free
hard resource over fabric, so a plan that has DSP slices to spare passes them in `budget` and asks for `fabric`; a plan
that has spent them passes `dsp: 0` and the DSP variants drop out with a reason.

CLI, the same data as JSON:

```
python3 -m flow.ipvariants                                     # validate every entry with variants
python3 -m flow.ipvariants fir --params TAPS=32,FOLD=8 --clock-ns 5 --budget dsp=0 --objective fabric
python3 -m flow.ipvariants --search fir filter
```

When the measured point is not exact, the numbers are the nearest point's (by the sum of log ratios of the numeric
parameters); `predicted` still gives the exact latency and II and the expression-based resource estimate. A planner
that needs the exact point measured adds it to `characterisation.points` and runs the characterisation.

## 4. A new variant (63B and later)

1. Add the RTL behind the same top (`IMPL` value, generate branch or a new core file) and the `variants:` entry.
2. Run the entry's existing tests at the variant (add it to the tests' parameter points) and the differential test if
   the entry has one; add a seeded fault that only the new variant's code can catch.
3. Characterise: `python3 -m flow.ipchar <block> --only <variant>` under a heavy slot. Rows of other variants stay.
4. `python3 flow/net/ipdoc.py` regenerates the README's Variants table; bump the entry's version and CHANGELOG.

Entries with variants so far: [fir](../ip_lib/fir/README.md) (four), [dds_awg](../ip_lib/dds_awg/README.md) (two),
[adc_histogram](../ip_lib/adc_histogram/README.md) (two).
