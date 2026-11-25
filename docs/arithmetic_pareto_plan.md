# Verified Pareto surfaces for an arithmetic function on a given FPGA fabric: plan (brief 137)

The idea (owner, 2026-11-21): for a given arithmetic function, find the best implementations on a given FPGA fabric under a trade-off of
power, performance and area (PPA); map a surface (or volume) of good implementations; verify every one; link it to the project that explores
the design space of a function, whose main example is CORDIC. This page is the plan for the whole line of work and the scope of its first,
measured phase (phase 0). The measured result is in [results/137_arith_pareto](../results/137_arith_pareto/README.md).

## What exists to build on

| Piece | Where | What it gives |
|---|---|---|
| Design-space project | `HW_Design_Space_Agent` (public, main 80415c6) | Four CORDIC families (`iterative`, `unrolled_k`, `pipelined`, `pipelined_m`) with numeric knobs; a bit-exact NumPy model of the reference RTL (`models/cordic_bitexact.py`); a parametric SystemVerilog generator (`rtl/generator.py`); Icarus and Verilator harness (`rtl/sim.py`, `rtl_harness/tb_generated.sv`); SymbiYosys proofs at W=8 (`rtl/formal.py`); an analytical Artix-7 cost model with a two-anchor default calibration and a 51-point refit (`models/cost_fpga.py`, `calibration_artix7_refit_*-m4.yaml`); 14 generated designs measured on an earlier Vivado release (`eval/data/vivado_measured*.csv`, `vivado_power.csv`); an ASIC cost model on sky130; the search (Optuna NSGA-II) and the LLM-as-architect graph with the rule that the model never produces a number |
| Flow | `flow/` here | `flow/run_vivado.sh` (memory-safe runner), the out-of-context pattern of `designs/b110_itch_ouch/ooc/ooc.tcl`, the design gates, the build cache, `flow/trace_v1.py` (requirements to evidence), the family matrix in the knowledge bank (per-family advice and measured limits) |
| Arithmetic know-how | the FPGA course Part 8 (private repo `FPGA_Design_Course`, `labs/p8_arith`) | DSP48E1 limits (a MAC tops out near 300 MHz even with the multiplier register; minimum period 3.884 ns with no MREG, 2.154 ns with every register), a W-bit adder with carry out takes `ceil((W+1)/4)` CARRY4, and the lesson that an out-of-context run at an easy clock hides Fmax (use a tight target) |

What the two projects do not share yet: the cost model is fitted to 7-series post-synthesis numbers at a 10 ns clock; there is no UltraScale+ calibration, no DSP or BRAM
in the space, no post-route model, and the measured points are not tied to a requirement-to-evidence record.

## The problem, stated precisely

Given a function f (for example sin/cos of an angle), a fabric (a part: LUT6 + carry chains + DSP + BRAM, with its speed grade) and a clock target, find the set of
implementations that no other implementation beats on every axis, and prove each one correct.

**Knobs** (what a design point is). CORDIC has all of these except DSP use; the next functions in the roadmap have the others.

| Knob | CORDIC today | Notes |
|---|---|---|
| Iterations N | 4 to 30 | accuracy against area and latency |
| Word length W, angle path width A, fractional guard g | W 8 to 28, A-W -2 to 4, g 0 to 4 | accuracy against area; the cheapest axis to move |
| Rounding | trunc / round | rounding folds into the adder carry-in, almost free in fixed-shift stages |
| Architecture family | iterative, unrolled_k (k per cycle), pipelined, pipelined_m (register every m stages) | the big latency, throughput and Fmax lever |
| Unroll k, pipeline interval m | 2 to 8 / 1 to 8 | k trades cycles for path length; m trades flip-flops for path length |
| DSP against LUT | not present | CORDIC is shift-add; a polynomial or multiplier-based sin/cos (minimax, Taylor with a DSP48) is the DSP knob, so a second function is needed |
| BRAM against LUT | not present | the atan table is small and becomes LUTs; a LUT-based sin/cos with table interpolation exercises BRAM |
| Retiming and synthesis strategy | not used | `synth_design -retiming`, `phys_opt` and the directive are knobs the flow can add without changing the RTL |

**Axes** (what is measured for every point). All are *measured* in Vivado unless marked *exact* (code) or *estimate*.

| Axis | Source |
|---|---|
| LUT, FF, carry cells, DSP, BRAM tiles | `report_utilization`, post-route (and post-synthesis, to compare with the model's own definition) |
| Fmax | `1000 / (T - WNS)` at a tight out-of-context target T, so the tool works as hard as it can; the same T for every point of a fabric |
| WNS, WHS at the target | `report_timing_summary` |
| Latency in clocks, results per clock | *exact*, from the family's schedule and confirmed in simulation |
| Latency in ns, throughput in Msps | derived from the measured Fmax and the exact cycle counts |
| Accuracy | *exact*: maximum and RMS error against ideal sin/cos, in output LSBs, from the bit-exact model's sweep (every angle for W <= 16, a documented dense set above) |
| Power | `report_power` vectorless (12.5 % default toggle, confidence Low), at the common target clock; Vivado's model, not a board measurement; compared across points, never quoted as watts of a real workload |

**What "verified" means for a point.** Each point carries a record; the tiers are listed from cheapest to strongest, and a point says which it reached.

1. *Bit-exact against the model* (done in phase 0): the generated RTL simulated on the model's sweep, every output code equal to the model's, every result's latency equal to the schedule's. Exhaustive (all 2^W angles) for W <= 16, otherwise 2^17 evenly strided and seeded-random angles. The remaining distance to the real function is an *error bound*: the model's maximum error against ideal sin/cos, stated in LSBs, is a property of the numerics and is checked against the spec's accuracy limit.
2. *Second simulator*: Verilator against Icarus (HW_Design_Space_Agent does both; Verilator is not installed on this build PC, so phase 0 used Icarus only and says so).
3. *Formal*: SymbiYosys proofs at W=8 exist for the generated designs (properties on the handshake and the one-result-per-input contract); a full functional equivalence proof against the model is not tractable for W > 12 by SAT and needs either a bit-blasted equivalence check of the unrolled datapath at small width or a Lean proof for all widths (brief 125's tier). Phase 2.
4. *Implemented and timed*: Vivado out-of-context synthesis, place and route at the target, with the timing report read (phase 0).
5. *Post-implementation simulation*: write the routed netlist and simulate it against the same vectors, so the verification covers what Vivado built, not what the generator wrote. The 7-series simulation library and `glbl` have to be compiled for Icarus (or xsim used). Phase 1.
6. *Board*: not planned for this line; a chosen front point could be put on a board later.

The requirements and evidence of every kept point go into a v1 testplan (`docs/traceability_v1.md`) once the point list is stable, so a point is "verified" in the repository's own
sense: a performance requirement is verified only when a measured value is inside the bound. Phase 0 keeps its evidence in plain JSON and reports it; wiring a design folder and
testplan is phase 1 (see "Phases").

## How the two repositories connect

| Owns | HW_Design_Space_Agent | FPGA_Design_Agent (this repo) |
|---|---|---|
| The function and its model | the bit-exact model, the generator, the registry of families and knobs, the golden RTL | reads them, never forks them |
| Search | Optuna NSGA-II, the fleet, the LLM architect and its rule that the model produces no number | calls it, or replaces it with exhaustive enumeration while the space is small |
| Estimates | the analytical cost models and their calibration | runs them as predictions to be checked, and writes measured rows back in HW_DSE's measured-points schema |
| Measurements | its own earlier-release runs on xc7a35t | Vivado 2026.1 (the repository's pinned release), K26 and other parts, power, post-route, OOC, the heavy-slot discipline |
| Verification evidence | simulation against the model, gate-level of the open-source netlist | the requirement-to-evidence matrix (brief 116), formal and Lean tiers, post-implementation simulation |
| Reuse by the agent | none | the knowledge bank (family matrix) says what a family can and cannot do; a Pareto set per (function, part) becomes a reference the agent compares an implementation against |

In phase 0 the code reused is: `ArchConfig`, `generate`, `verify_rtl`, `accuracy`, `FpgaCostModel` (import only; nothing in HW_Design_Space_Agent was changed). The new code is
`flow/arith_pareto.py` (points, drivers, parsers, comparison, Pareto) and `results/137_arith_pareto/` (the records). Changes to propose to HW_Design_Space_Agent are in the phase 0
report: a measured-points schema that carries post-route, power and the Vivado release; a UltraScale+ calibration file; the target clock written into each row.

## Phases

| Phase | Scope | Decides |
|---|---|---|
| 0 (this brief) | CORDIC sin/cos, 13 points on the Artix-7 part of HW_Design_Space_Agent and 4 on the K26: verified by simulation, Vivado 2026.1 OOC post-route with timing, utilisation, power; cost-model prediction against measurement per axis; the front as a figure | whether the cost model is good enough to prune, and whether the full line is worth it |
| 1 | Post-implementation simulation of the front; a v1 testplan and design folder so every kept point is a traced, stale-checked requirement; refit the cost model on 2026.1 post-route data with a held-out set; widen the CORDIC grid to 60 to 100 points guided by where phase 0 showed the model wrong | an honest estimate of how many Vivado runs a full surface needs |
| 2 | A second function with the DSP and BRAM knobs (a multiplier-based or table-and-interpolate sin/cos, or a FIR or complex multiplier), formal or Lean checks of the arithmetic, a retiming and directive knob, the same comparison | whether the method generalises beyond a shift-add datapath |
| 3 | Families beyond Artix-7 (K26 UltraScale+, a Versal or Intel/Altera-style fabric via its own tool), a pruning search that spends Vivado runs only where the model is uncertain, a "Pareto atlas" page on the site with the matrix links | whether the atlas is a product (a public reference) or an internal tool |

Spend: a phase-0 point is one Vivado out-of-context run of a few minutes on one thread and about 2 to 3 GB; the whole phase 0 is under two hours of one heavy slot. The cost of a full
surface is a number phase 1 estimates.

## Risks to watch

* The generated RTL has no DSP or BRAM, so a "DSP against LUT" front needs a second function; the claim that the method covers the PPA trade-off is only half tested until then.
* The out-of-context result is the logic's own Fmax. Input and output delays, a real placement next to other logic and a congested device all move it; a front is a ranking aid, not a promise for a design in context.
* Vectorless power ranks activity-blind structures; it cannot tell a point that toggles rarely from one that toggles often.
* A cost model fitted to the same family of points it predicts will look better in-sample than out; phase 0 therefore uses points that are in neither calibration file.

## Owner directions (2026-11-21), planned here

Three directions arrived while phase 0 was running. Each is planned below; none changes the phase 0 measurement.

### 1. A library of characterised functions

The owner's aim: a large library of arithmetic functions, each characterised as phase 0 characterises CORDIC; FPGA arithmetic is the interest, and Lean and general verification are part of the appeal.

**Library format.** One folder per function, `library/<function>/` (in the meta-project's repository, see 3), each holding the same five things:

| File | Content |
|---|---|
| `spec.md` + `spec.yaml` | the mathematics (domain, range, fixed-point format as parameters); for an approximation, the error bound as a stated quantity (max abs and RMS in output LSBs, over what input set); the requirement ids a testplan will trace |
| `model/` | the bit-exact model (NumPy or pure Python), written from the spec alone, and the golden vectors it produces |
| `lean/` | where tractable, a Lean 4 statement and proof (see the table below); otherwise a note saying why not and what is checked instead |
| `impl/<variant>/` | each verified implementation: the RTL (readable source), the verification record (simulation tier, formal tier, Lean tier, each named), the structural netlist once frozen (see 2) |
| `surface/<fabric>/` | the measured Pareto surface: one row per variant per fabric with Vivado release, target clock, utilisation, WNS, power, latency, throughput, error; the figure; the cost-model comparison; the raw reports |

A function is **admitted** when its spec is reviewed by the owner (`spec_status: agreed`, the repository's existing rule that only a human sets it), its model and one implementation pass the simulation tier, and one fabric's surface exists. A *variant* is **verified** at the tier its record names; the library page shows the tier per variant, never a single "verified" flag.

**Where Lean applies.** Lean's role (brief 125): arithmetic identities and datapath algorithms whose claim is "for all widths", plus the spec-checking role (a theorem statement is a precise requirement a human reads). SymbiYosys stays for control and handshakes.

| Function | Lean statement | Status |
|---|---|---|
| Ripple and carry-chain adder (`a + b` in W bits, with carry out) | the bit-level adder equals modular addition, for all W; the carry chain of `ceil((W+1)/4)` CARRY4 stages computes the same carry | tractable (`bv_decide` or induction on W) |
| Constant and general multiplier (shift-add, Booth radix-4, Baugh-Wooley signed) | the recoding equals `a * b` for all W | tractable; Booth recoding proofs are standard |
| Multiply-accumulate with saturation or wrap | composition of the above plus the accumulator width bound: no overflow for N terms when `W_acc >= 2W + ceil(log2 N)` | tractable |
| Fixed-point rounding (truncate, round-half-up, round-half-even, saturate) | error bound `|round(x) - x| <= 2^-(f+1)` and the carry-in folding identity used by the CORDIC generator | tractable |
| Reciprocal or division by Newton-Raphson, restoring division | restoring division equals `Nat.div` for all W; Newton-Raphson needs an error recurrence, `e_{n+1} <= e_n^2` plus the table bound | division tractable; Newton-Raphson moderate |
| Square root (digit recurrence) | integer sqrt equals `Nat.sqrt` for all W | tractable |
| **CORDIC sin/cos** | the end-to-end error bound over all inputs (residual angle after N rotations <= `atan(2^-(N-1))`, plus accumulated rounding of 3N operations, plus gain compensation error) | **research**: each ingredient is classical, the composed fixed-point bound for all W, N is not in a library we know of; phase 0 records the exhaustive and dense-sweep error instead, which is a measured lower bound on the worst case, not a proof |
| Polynomial and table-interpolation sin/cos, exp, log | the polynomial error (minimax or Taylor remainder) is a real-analysis statement; the fixed-point evaluation error is a rounding-chain bound | research to moderate; Mathlib has Taylor remainders, the fixed-point layer is ours |
| FFT butterfly, complex multiplier, FIR | exact identities (the 3-multiplier complex product equals the 4-multiplier one) | tractable for the identities; filter response is out of scope |

**First functions to characterise (proposed order, 8).** Chosen so each adds a knob phase 0 lacks, and the first three are cheap to verify:

1. Adders: ripple, carry-chain (CARRY4/CARRY8), carry-select, carry-save compressor tree. Knob: LUT against carry chain against DSP48 `A:B+C`. Lean: tractable.
2. Multipliers: shift-add, Booth radix-4, LUT-only, DSP48E1/DSP48E2 with 0, 1, 2 and 3 pipeline registers. The DSP-against-LUT knob. Lean: tractable. Fmax limits from the course's Part 8 are the first checks of the measurement.
3. Multiply-accumulate (the Part 8 MAC variants). Lean: tractable. Reuses the course's measured OOC numbers as a cross-check.
4. Fixed-point rounding and saturation units (a small function; the carry-in folding is already in the CORDIC generator). Lean: tractable.
5. CORDIC sin/cos (phase 0) and CORDIC vectoring (atan2, magnitude). Lean: research.
6. Table-and-interpolate sin/cos (BRAM against LUT). Lean: moderate.
7. Reciprocal and division (restoring, radix-4, Newton-Raphson with DSP). Lean: division tractable.
8. Square root (digit recurrence, CORDIC hyperbolic). Lean: tractable.

Later: FFT butterfly and complex multiply, CIC and FIR, exp/log, ML-KEM modular arithmetic (the specialist-processors series already has measured mod-q units), Gray and CRC (the repository's Lean tier has the Gray lemma).

### 2. End point: a structural description

The owner's question is whether the end point of the investigations is a very low-level structural description. The proposal is a chain with an equivalence check at every link; the RTL remains the readable source and the structural form is the **frozen, characterised artefact**.

| Step | Artefact | Check against the step before | Tool | What it costs |
|---|---|---|---|---|
| 0 | Lean spec and theorem | (the reference) | Lean kernel | tractable per the table above; research for CORDIC |
| 1 | RTL (the generator's output or hand-written) | simulation against the model; Lean for the algorithm; for the RTL itself either a transcription check (brief 125's `transcription_tested`) or SAT equivalence at small width | Icarus/Verilator, Yosys + SymbiYosys | cheap |
| 2 | Structural netlist: `LUT6`, `CARRY4/8`, `DSP48E1/2`, `FDRE`, `RAMB` instances; optionally `RLOC`/`BEL`/`LOC` relative placement | sequential equivalence of netlist against the RTL (Yosys `equiv_*`, or `eqy`), plus the same simulation vectors on the netlist | Vivado `write_verilog`, Yosys with the Xilinx cell library, `eqy` | cheap for small pipelined cores where registers keep their names; harder where synthesis retimed or re-encoded state (an FSM): then a miter with a bounded depth and the simulation vectors, and the record says "bounded" |
| 3 | Placed-and-routed module (a checkpoint, a RapidWright relocatable module) | Vivado `report_route_status`, a formal-equivalence run by `write_verilog -mode funcsim` of the routed design simulated against the same vectors (phase 1) | Vivado, RapidWright (repository: `designs/b100_rapidwright`) | family-specific: it freezes one device family's primitives and routing; a UltraScale+ module is not an Artix-7 module |

What the structural form gives: a result that no longer depends on the synthesis tool's release (a Vivado upgrade cannot move the characterisation), exact reproducibility of area and (with relative placement) of Fmax, and the possibility of hand-tuned placement of a datapath. What it costs: it is per family (a 7-series netlist uses `CARRY4`, UltraScale+ `CARRY8` and different DSP and LUT-pair rules), harder to read and maintain, and its Fmax holds only when the placement is kept; in a design with other logic the router decides. The proposal is therefore: keep RTL as the source of truth, store the frozen structural netlist next to each *front* variant per family, and treat the placed-and-routed module as optional, for the few variants worth reusing.

Cheap demonstration in phase 0: the Vivado runs also write `netlist_synth.v` (post-synthesis, `write_verilog -mode funcsim`, primitive-level) per point. The report states whether the small pipelined point's netlist could be checked equivalent to the generated RTL with Yosys in the time available, or the check is left planned.

### 3. A meta-project above FPGA Guild

The proposal: the FPGA-arithmetic work is a **separate meta-project** that owns the things the design agent does not:

* the **functions**: specs, bit-exact models, Lean statements, the library of 1 above;
* the **search**: in code, as HW_Design_Space_Agent does it (the language model proposes and explains, never produces a number); enumeration while the space is small, Optuna NSGA-II or a model-guided pruning loop later;
* the **Pareto analysis**: fronts, surfaces, volume (area, latency, throughput, error, power), the cost model and its calibration, the atlas page;
* the **library** and its records.

and **calls FPGA Guild as a service** to turn a design point into evidence. HW_Design_Space_Agent is the natural start of this meta-project (it already has the functions, search and cost models, and no tool flow beyond its own Vivado scripts); the proposal is to add a service client to it, not to fork it.

**Call interface** (what the meta-project sends and gets). The service is a function from a design point and a request to a record:

```
request  = {
  function: "cordic_sincos", variant_params: {family, data_width, n_iter, ...},    # the meta-project owns the meaning
  sources: [path or generated text],  top: module, clock_port: "clk",                  # RTL it generated
  model: path, vectors: path | sweep spec, error_bound: {metric, bound, unit},        # what "correct" means
  fabric: {part, speed_grade}, tool: {vivado: "2026.1"},                                # what to build on
  target: {clock_ns, mode: "out_of_context"|"in_context"}, ooc_wrapper: optional,
  measures: [utilisation, timing, power_vectorless, structural_netlist],
  verify: [sim_vs_model, formal_bmc, equivalence_netlist],
  budget: {vivado_seconds, memory_gb}, tags: {brief, caller}
}
response = {
  status: ok | verify_failed | build_failed | timing_failed | refused(reason),
  verification: [{tier, simulator+version, vectors, mismatches, bound_checked, record_path, hashes}],
  implementation: {tool, version, part, clock_ns, luts, ffs, carry, dsp, bram, wns, tns, whs, fmax, power{total,dynamic,confidence}, seconds, peak_rss, thread_count},
  artefacts: {reports, checkpoint, netlist, structural_netlist},
  provenance: {source_hash, flow_commit, cache: hit|miss}
}
```

**What `flow/` offers today.**

| Need | Offered | Where |
|---|---|---|
| Memory-safe Vivado run with run record (wall time, peak RSS, threads, cache decision) | yes, for a *design folder* with `build.yaml`, on a board part | `flow/run_vivado.sh`, `flow/prepare.py`, `run.json`, `gates.json`, `flow/build_cache.py` |
| Heavy-slot discipline and thread count | yes, outside the flow (shell) | `_handoff/take_heavy_slot.sh --env` |
| Out-of-context synthesis and implementation of a module on a part | per-design scripts only (`ooc.tcl` in b87, b93, b100, b110, b119); no generic one | `designs/*/ooc/` |
| Gates on reports (setup, hold, CDC, reset checks) | yes, tuned for in-context board builds | `flow/gates.py`, `flow/checks/` |
| Simulation against a model, mutation tests, coverage | yes, cocotb + Icarus/Verilator, per design folder | `flow/cocotb_run.py`, `flow/verif_gates.py` |
| Requirement-to-evidence matrix | yes, per design folder | `flow/trace_v1.py` |
| Formal (SymbiYosys) and Lean evidence | yes | `flow/formal.sh`, `flow/lean_tier.py` |
| Knowledge bank (family matrix, Vivado option facts) | yes, private, pinned | `knowledge/PACKS.md` |

**What is missing** (the work a service needs): (a) a **generic OOC entry point**, `flow.ooc.run(sources, top, part, clock_ns, parameters)`, that replaces the five per-design `ooc.tcl` files and writes one JSON record (phase 0's `arith_pareto.py` Tcl and parsers are its seed); (b) **batching**: many points in one Vivado session (done in phase 0) with the cache keyed by source hash, part, clock and flow commit; (c) **power** in the standard record; (d) a **structural netlist export** and the equivalence step; (e) a **request/response schema** and a refusal path (no slot, no licence for the part, tool release mismatch) so a caller never gets a number without its provenance; (f) **non-board parts** and parts the Basic licence covers (K26 worked in phase 0; others are to be checked per part); (g) a **function-level verification hook**: the caller supplies a model and vectors, the service runs the sim and returns mismatches, so the design agent does not need to know the function; (h) a **queue** with the heavy-slot admission rules built in, since the meta-project would otherwise try to take slots itself; (i) an access rule: the design agent has an access gate (brief 94), and a client of the meta-project must pass it.

Order of work: (a), (b) and (c) are phase 1 and come straight out of phase 0's driver; (d) and (g) are phase 2; (e), (h) and (i) are written when the second function needs the service. Until the service exists, the meta-project calls `flow/arith_pareto.py`-style drivers directly and checks every number against the same record schema, so moving to the service changes the transport and not the records.

### Structural netlists on UltraScale+ come from Vivado, not Yosys (owner, 2026-11-21)

Yosys 0.70 maps carry logic to CARRY4, the 7-series primitive, even with `synth_xilinx -family xcup`: a 32-bit adder becomes 8 CARRY4 and 32 LUT2
for both `xc7` and `xcup` (planner's check, 2026-11-21; Yosys's `cells_sim.v` has a CARRY8 model but `arith_map.v` emits only CARRY4). The book
"FPGA Design for Low-Latency Trading: From RTL to Tick-to-Trade" makes the same point in its tip "Yosys speaks CARRY4" (section 2.3). So, on
UltraScale+ (K26 and later): the structural form of a library entry is taken from Vivado's synthesised or implemented netlist, or written by hand with
CARRY8 and checked; Yosys is used there only to prove equivalence (where the primitive choice does not matter), never for the structural netlist or
for resource and timing estimates. Brief 142 measures the other Yosys-versus-Vivado gaps on xcup (LUT6_2 packing, wide muxes, DSP48E2 features,
BRAM/URAM, SRLs, control sets) and whether Vivado retargets a CARRY4 netlist to CARRY8.

## Goal restated: entries of an FPGA IP library that the agent retrieves from (owner decision 24, 2026-11-21 16:08)

The product of this line of work is not a set of charts. It is **entries of an FPGA IP library** that FPGA Guild retrieves from when it plans a design and from which
it picks the Pareto point that fits the design's constraints. The owner's framing: fully verified RTL optimised for FPGA, produced *without knowing the larger design*, with a
packaged verification harness, characterised per device family. The measured CORDIC surface of phase 0 is the first surface of such an entry; everything in "A library of
characterised functions" above is the content of an entry. This section fixes the entry schema, the retrieval interface and the relation to the meta-project.

### (a) The entry schema

The repository already has the unit: `ip_lib/<entry>/` with `ip.yaml` (declared parameter space and contract; `flow/net/ipdoc.py` renders the README and checks it), `rtl/`, `faults.yaml`
(seeded faults), `char/` (measured costs) and a CHANGELOG (for example `ip_lib/adc_histogram`). An arithmetic entry **extends that format** rather than adding a second one; the new keys
are marked.

```
ip_lib/<function>/
  ip.yaml                  # as today: name, version, status, summary, top, rtl, interfaces, clocks, parameters, latency, throughput, guards, variants, resets, boundary, limits, constraints, licence
  spec.md / spec.yaml      # NEW  the function: maths, domain and range, fixed-point formats, error bound as a stated quantity, requirement ids
  contract.yaml            # NEW  the interface contract (below): written from the spec alone, without the larger design
  model/                   # NEW  bit-exact model and golden vectors (blind to the RTL)
  harness/                 # NEW  the packaged verification harness (below), rerunnable in a larger design
  rtl/ + variants/<v>/     # the readable RTL per variant
  verify/<v>.json          # NEW  per-variant verification record: tier reached (sim, second simulator, formal, Lean, netlist equivalence), vectors, bound, hashes
  surface/<family>/        # NEW  per device family: the measured Pareto surface (rows per variant: area, Fmax at a stated clock, WNS, latency clocks, throughput, error, vectorless power), release, raw reports, figure, cost-model comparison
  structural/<family>/<v>/ # NEW  frozen structural netlist of the best points (primitives, relative placement), with its equivalence record
  pnr/<family>/<v>/        # NEW  optional placed-and-routed block (RapidWright or checkpoint) for the few best points, family-bound
  integration.md           # NEW  integration guidance (below)
  faults.yaml, CHANGELOG.md
```

**The interface contract** (`contract.yaml`) says everything a user needs and nothing about the design it will sit in: the protocol per port (valid/ready, AXI-Stream with `tlast` meaning,
or a fixed-latency strobe pipeline), the number format and sign convention of every port, latency in clocks and initiation interval *per variant* (exact, confirmed by simulation, not
estimated), backpressure behaviour (is a stall allowed, does the pipeline drain or freeze, can a result be lost), reset (synchronous or asynchronous, what is reset and what is not, how
many clocks before the first valid result, what the outputs are during reset), clock (single clock, no CDC inside; maximum frequency per family from the surface, with the clock at which it was measured),
and the section **"what a user could guess wrong"** (the owner's documentation rule): for example in CORDIC, that outputs are Q1.(W-2) with the gain already compensated, that the angle input is a
fraction of a turn and wraps, that the pipelined variant has no stall input, that the iterative variant's `ready` goes low for N+3 clocks, that data registers are not reset so outputs are unspecified until
`valid_out`, that the error bound holds for the swept inputs and is a measured lower bound on the worst case, not a proof, unless a Lean tier is recorded.

**The packaged harness** (`harness/`): the model, the golden-vector generator and a bench that can be pointed at the entry *inside a larger design* (instance path as a parameter) and rerun
after integration. It contains: the model and its vectors; a cocotb or SystemVerilog bench with a protocol monitor on each port; the assertions and formal properties of the contract (handshake
legality, one result per accepted input, latency, no output on reset) as bind-able checkers, with their SymbiYosys jobs; the functional coverage bins (the contract's corner cases: format extremes, wrap
points, back-to-back inputs, stalls) and a `thresholds` record; the seeded faults (`faults.yaml`) that prove the bench catches wrong implementations; and a v1 testplan fragment (requirements to
evidence, `docs/traceability_v1.md`) that the larger design's testplan includes by reference, so the library's evidence shows in the design's matrix.

**Integration guidance** (`integration.md`): the port timing budget (the registered or combinational nature of each input and output, so the integrator knows what the block's measured Fmax
assumes: phase 0 measured out of context with no I/O delay, and says so); constraints to carry (clock period, `set_max_delay`/multicycle only where the contract allows, `RLOC` or pblock for
the structural variant, false paths never inside the block); an **in-context check** the agent must run after integrating (rerun the harness on the instance, then a timing check of the block's
paths in the full design against the surface's promise, with the failure modes listed: a path through a port the OOC run left unconstrained, a clock crossing at the boundary); and the
versions: the Vivado release and part the surface was measured on, with the rule that a different release or family is a different surface, not a number to carry over.

An entry is **retrievable** when its contract, model, harness, one variant's verify record and one surface exist, and **admitted** when the owner or the planner (on the owner's delegation, recorded as
such) has agreed the spec. A variant never carries a single "verified" flag; the library page shows the tier per variant.

### (b) The retrieval interface

How the agent finds an entry and chooses a point. The agent already retrieves *skills* from the frozen knowledge bank by hybrid BM25 and embedding search, returning names and one-line
descriptions, then loading one body or section (`agent/core/skill_index.py`, `agent/core/bank.py`). The library adds two steps beside that, because choosing a Pareto point is a query over
numbers, not over text.

1. **Find the entry** by text: each entry contributes a short card (name, one-line summary, function, interfaces, families measured, parameter ranges, tags such as `mac`, `dsp48`, `fixed-point`) to the same index, so
   "32-bit MAC with DSP" finds `mac` through the existing path and the agent sees the card before any body. Nothing new in the index; a new source of cards (`ip_lib/*/ip.yaml` and `contract.yaml` summaries).
2. **Choose a point** by a structured query over the entry's surface files, run by code, never by the language model:

```
query = { entry: "mac", family: "artix7"|"kintexu+"|..., fabric_part: "...", tool: "2026.1",
          constraints: { fmax_mhz_min: 300, dsp_max: 2, lut_max: ..., latency_clocks_max: ..., power_dynamic_max_mw: ..., error_lsb_max: ... },
          objective: ["min area", "min latency"], interface: {protocol: "valid_ready"|"axis", widths: {a: 32, b: 32, acc: 72}} }
reply = { points: [ {variant, parameters, measured: {...}, verify_tier, surface_record, structural: path|null, pnr: path|null, margin: {fmax_mhz: +12, dsp: 0}} ... ],
          front: [ids that no other feasible point beats], nothing_fits: {binding_constraints, nearest: id, shortfall}, extrapolation: [what the reply had to assume] }
```

The reply says which constraints bind and, if nothing fits, the nearest point and by how much; it never interpolates a number between measured points (it may flag that the cost model predicts a
parameter value between two measured ones and mark it *estimate*, with the model's measured error for that family from the comparison). A query on a family or release not measured is answered "not measured" plus the
nearest measured family and the cost model's estimate labelled as such. The reply is a record: the agent copies the chosen point's record into the design's testplan as the evidence for the requirement that the block
meets its Fmax and area, and adds the harness fragment. Worked example from the owner: `{entry: mac, widths 32x32, fmax_mhz_min: 300, dsp_max: 2}` on Artix-7 returns the DSP48E1 variants with M and P registers (the course's Part 8
measured limit: about 300 MHz with a dynamic OPMODE, so the entry must record whether OPMODE is static) and reports that the LUT-only variant misses the clock.

The retrieval code lives with the agent (`agent/core/`, next to the skill index) and reads only the entry's committed records; the surface files use the schema phase 0 defined (`measured.json`, `comparison.json`,
`verify.json`), so adding a function adds data, not code. The library's entries are untrusted data like skill text: the query tool parses them and interprets nothing.

### (c) Relation to the meta-project that calls FPGA Guild

The two directions are one loop, not two projects:

* **The meta-project produces entries.** It owns functions, search and Pareto analysis, and calls FPGA Guild *as a service* to implement, verify, implement-in-Vivado and close timing for each design point (the call interface above). What it writes back is an entry: contract, model,
  harness, verified variants, surfaces. The agent is the **producer's workhorse** here, and the entry is the product.
* **The agent consumes entries.** When it plans a design, it retrieves an entry, queries a Pareto point against the design's constraints, instantiates it, and reruns the entry's harness in context. The library is the **consumer's resource** there.
* The loop closes when an agent run exposes something the entry did not say (an in-context timing failure, a contract ambiguity, a guess that was wrong): that goes back as a defect or a new line in "what a user could guess wrong", and a new characterisation run
  goes through the meta-project. The service interface is therefore also what the *regeneration* of a surface uses, so a Vivado release change (a new surface) is a batch of service calls, not a manual job.
* Boundary: the meta-project never edits the design agent's flow and the design agent never edits the library entry it consumed; a change request crosses the boundary as a record. Entries live in `ip_lib/` of the design-agent repository (where the agent and CI already look,
  and where `flow/net/ipdoc.py` checks them), while the meta-project's search code, models and campaign records live in its own repository; the entry is the interface between them. Until that repository exists, the entries and their generator are in this repository and
  `HW_Design_Space_Agent`.

Order of work, added to the phases above: phase 1 produces the first full entry (CORDIC: contract, harness, verify records, surface, structural form for one point), because CORDIC is the case where everything but Lean exists; phase 2 produces the first
DSP-using entry (MAC, the owner's example) so the retrieval query has a real "DSP at most 2" constraint to answer; the retrieval tool is written in phase 2 against those two entries.
