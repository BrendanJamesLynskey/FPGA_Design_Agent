# IP library variants: one block, several implementations

Some blocks can be built several ways: a filter can use many multipliers for speed, or one multiplier for size. This
page describes how the library stores those implementations ("variants") with the same ports and the same bit-exact
result, and what each one costs in logic, memory, multipliers, speed and latency. The costs are measured on an Artix-7
(xc7a100t) with Vivado 2026.1; no other device family has been measured, and nothing here has run on a board.

**Try it** (plain Python, no Vivado needed):

```
python3 -m flow.ipvariants fir --params TAPS=32,FOLD=8 --budget dsp=0 --objective fabric   # rank the FIR's variants
python3 -m flow.ipvariants --search fir filter                                            # find library entries
python3 -m flow.ipvariants                                                                # check every entry
```

The planning stage reads these costs to pick a variant, and the timing-repair loop may swap one variant for another.
`flow/ipvariants.py` reads the data; `flow/ipchar.py` measures it. Code outside the library reads variants only through
`flow/ipvariants.py`, so the file formats below can grow without breaking its callers.

**Words used here**

- **Variant**: one implementation of a library entry, chosen by a string parameter (`IMPL`).
- **MAC**: multiply-accumulate, the core operation of a filter; a DSP slice does one per clock.
- **DSP slice**: a hard multiplier-adder block in the FPGA. **Block RAM tile**: a 36 Kb hard memory (half a tile is 18 Kb).
- **LUT RAM**: small memories built from the lookup tables (LUTs) of general logic.
- **II (initiation interval)**: clocks between accepted inputs; 1 means a new input every clock.
- **Latency**: clocks from an accepted input to its result.
- **Out of context (OOC)**: the block is built alone, without the rest of a design or any pin or I/O constraints.
- **WNS (worst negative slack)**: the worst timing margin against the target clock; below zero means the target was missed.
- **Fmax estimate**: 1000 / (period - WNS) from one routed run, in MHz.
- **Vectorless power**: power estimated with default switching rates instead of simulated activity; good for ranking only.
- **Characterisation**: measuring every variant at a few fixed parameter points.
- **Direct versus transposed form** (FIR): the direct form stores the last samples and multiplies each by its
  coefficient; the transposed form multiplies each new sample by every coefficient and stores running partial sums.
  The library's parallel FIR is direct form, because a transposed form mixes old and new coefficients for TAPS - 1
  outputs after a coefficient reload.

## 1. `ip.yaml`: what an entry declares

Three keys sit beside the existing ones (`parameters`, `latency`, `sweep_tested` and the rest):

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
    requires:                     # optional: expressions that must hold for this variant (its RTL guard refuses the rest)
    - FOLD >= 2 and FOLD <= TAPS
    params: {}                    # optional: parameters the variant fixes (none in the first three entries)
constraints:                      # expressions that must hold for every variant
- DATA_W + COEF_W + clog2(TAPS) <= 48
sweep_tested:                     # simulated points; variant_param may list several variants
- {IMPL: [dsp_bram, dist_ram, serial, lut_mult], TAPS: 16, DATA_W: 16, COEF_W: 16, FOLD: 4}
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
- Expressions use the entry's numeric parameters, `+ - * / // %`, `ceil`, `floor`, `min`, `max`, `clog2`, `log2`,
  `pow2` (2 to the power 0..64; there is no `**` operator, so an expression cannot build a huge number),
  comparisons, `and`/`or`/`not` and `a if c else b`. They are parsed, never executed as code. They must evaluate at the defaults, at every
  `sweep_tested` point and at every characterisation point.
- Every variant has its own RTL branch (its name appears as a string literal in the entry's RTL, which is also what
  the RTL's own guard accepts), runs in at least one `sweep_tested` point, and, unless it is the default, is named in
  a test file listed in `evidence.tests`. A variant declared without RTL or without a test fails the check.
- `characterisation` exists and its file `char/<part>.json` holds an `ok` row for every variant at every point, made
  with Vivado 2026.1. A row's latency and II equal the ip.yaml expressions at that point, and its DSP slices and block
  RAM tiles equal the variant's declared `uses` (so a planned DSP built in LUTs, or an adder pulled into a DSP slice,
  fails the check).
- Malformed input (a variant that is not a mapping, an expression that does not parse) is reported as a problem, not
  as a traceback.
- Known limit: the RTL and test ties are text matches. A variant whose name appears only in an RTL comment and a test
  comment would pass them; a stronger check would read the test module's variant list or the `IMPL ==` comparisons.
  Review catches the deliberate case; the check catches the honest mistake of declaring a variant and building nothing.
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
`clock_ns` on port `clk` and no I/O constraints. Each point takes a few minutes and up to about 6 GB of memory, so run
characterisations one at a time. Artix-7 only so far: no other family has been measured.

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
  Negative WNS means the target clock was missed; the figure is then the speed the same run would reach.
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
| `check_point(block, variant, params)` | why a point is outside the variant's space: unknown names, ranges, sets, `constraints`, the variant's `requires` (empty list: fine) |
| `predict(block, variant, params)` | `{"variant", "params", "latency", "ii", "uses": {...}}` at that point, from ip.yaml; ValueError outside the space |
| `measured(block, part=None)` | the rows of `char/<part>.json`, each with `part`, `clock_ns` and `tool` added |
| `variant_costs(block, params=None, part=None, clock_ns=None)` | one row per variant: `valid`, `predicted` (above), `measured` (the nearest characterised point, `exact: true` only at that very point), `cost` (predicted `uses`, overlaid with measured values only when exact) and, with `clock_ns`, `meets_clock` (None unless measured here) |
| `choose(block, params, part, budget, clock_ns, need_ii, objective)` | the `variant_costs` rows ranked, each with `fits` and `reasons` (outside the space, over budget, not known at this point, misses the clock, II too large); `note` on every row when the part has no measurements |

`budget` maps the `uses` keys (`lut`, `ff`, `lutram`, `bram_tiles`, `dsp`) to what the plan has left for this block.
`objective` orders the fitting rows: `area` (fewest DSP, then block RAM tiles, then LUTs), `fabric` (fewest LUTs, then
FFs), `throughput` (lowest II, then highest Fmax) or `fmax`. The planner applies its own rule: prefer a free
hard resource over fabric, so a plan that has DSP slices to spare passes them in `budget` and asks for `fabric`; a plan
that has spent them passes `dsp: 0` and the DSP variants drop out with a reason.

CLI, the same data as JSON:

```
python3 -m flow.ipvariants                                     # validate every entry with variants
python3 -m flow.ipvariants fir --params TAPS=32,FOLD=8 --clock-ns 5 --budget dsp=0 --objective fabric
python3 -m flow.ipvariants --search fir filter
```

Every check is made at the requested point. A budget key is checked against the ip.yaml prediction at that point
(DSP slices and block RAM tiles are declared for every variant), or against a measurement made at exactly that point;
a value known only from a nearby measured point is never used to pass a budget, and the row says the value is not
known there. The same holds for the clock: the Fmax estimate must have been measured at this point. The nearest
measured row is still returned in `measured`, for context. A planner that needs a point measured adds it to
`characterisation.points` and runs the characterisation. A point outside an entry's space (a parameter out of range, a
broken constraint, or a variant's own `requires`, such as `TAPS <= 64` for `lut_mult`) is never offered.

## 4. Adding a variant

1. Add the RTL behind the same top (`IMPL` value, generate branch or a new core file) and the `variants:` entry.
2. Run the entry's existing tests at the variant (add it to the tests' parameter points) and the differential test if
   the entry has one; add a seeded fault that only the new variant's code can catch.
3. Characterise: `python3 -m flow.ipchar <block> --only <variant>` (Vivado, minutes per point). Rows of other variants stay.
4. `python3 flow/net/ipdoc.py` regenerates the README's Variants table; bump the entry's version and CHANGELOG.

Entries with variants so far: [fir](../ip_lib/fir/README.md) (four), [dds_awg](../ip_lib/dds_awg/README.md) (two),
[adc_histogram](../ip_lib/adc_histogram/README.md) (two), [crc32_step](../ip_lib/crc32_step/README.md) (two; a CPU
function unit, docs/hwsw.md). An entry whose logic sits only between its input ports and its output registers has no
register-to-register path out of context: its row records no WNS and no Fmax estimate, and its LUT count can be far
below the in-context one, because the untimed input path is optimised for area (`crc32_step` `word`: 95 LUTs out of
context, 297 inside the BRV32P core, results/64a_hwsw/core_ooc.json).
