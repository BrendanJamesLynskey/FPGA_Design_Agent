# Verification: V-stages on a simulator-portable stack (brief 04f)

UG949 (the UltraFast methodology, [methodology.md](methodology.md)) covers implementation, not verification. The
closest open equivalent of a staged verification sign-off is OpenTitan's (Apache-2.0): *development stages* and the
DV methodology's V0-V3 checklist (docs.opentitan.org, "Hardware Development Stages" and "Design Verification
Methodology" / "Checklists", read 2026-11-01). This repo adopts their structure, and replaces the parts that need
a paid simulator. The independent-checking rule of the house rules still applies: the agent's own testbench never
counts as a pass; the blind model, the formal checks and the hardware do.

## The stages

| Stage | OpenTitan | What it requires here | Exit checks (`flow/verif_gates.py`, raw numbers) |
|---|---|---|---|
| V0 plan | V0: testbench and testplan started | a testplan file, the blind model and the bench modules exist | files present |
| V1 testplan | V1: testplan written and reviewed; testbench connected to the model; smoke test passes | `verif/testplan.yaml` generated from `spec.yaml`; every spec statement traced to tests, assertions, cover points, bins or formal tasks (a DO-254 style traceability matrix); the bench compares against the blind model | spec items traced / total (must be all); no unresolved name; no requirement without a check |
| V2 tests complete | V2: directed and constrained-random tests written and passing; assertions in; FPV on control logic | every planned test passes on every seed; the constrained-random test ran; checkers are bound and no assertion fires; formal bounded proof and cover pass on the control logic | failing / missing tests; formal tasks not PASS |
| V3 coverage closed | V3: coverage closed with waivers, all seeds passing, no open bugs | functional bins and cover properties all hit; line and toggle coverage at stated thresholds; every waiver carries a reason; at least `seeds_min` seeds, all passing; the bench's mutation score at its threshold | each percentage against its threshold; unhit bins and cover properties listed |
| V-HW (ours) | none | the board bring-up against the model passes (`results/f0b/*_bringup.json`, `pass: true`, with its build stamp) | pass flag |

OpenTitan's V2S (security countermeasures) does not apply to these designs.

### Where the V-stages join the UltraFast stages

The agent's stage machine ([methodology.md](methodology.md)) has nine stages. V0 and V1 start when the spec is
signed off (stage 0) and the blind model is written; V2 and V3 sit **inside stage 2** (`rtl-design-creation`):
stage 2 now ends only when `verif_gates` reports V3 (replacing "every mutant fails the tests" with a measured
mutation score) as well as `flow/lint.sh` clean. **V-HW is stage 9** (`configuration-and-debug`): its exit check
is the bring-up gate. A V-stage failure loops back to stage 2 (RTL or bench) or stage 0 (the model and the RTL
disagree about the spec).

## The stack and why

The owner's simulator matrix (`SystemVerilog_Simulators`, `index.html`, `FEATURES`, columns Icarus 12 / Verilator
5.020 / xsim 2025.2 / Questa Starter; commit 485f024) decides it. Free tools only (owner decision).

| Need | Matrix says | Decision |
|---|---|---|
| Constrained random, covergroups | `rand`: only xsim runs it among the free tools; Questa Starter needs a paid licence. `cov`: Icarus no, Verilator 5.020 "Unsupported: covergroup", xsim partly; Questa Starter paid. xsim cannot run in CI. | **The bench is Python (cocotb).** Stimulus, constrained random (cocotb-coverage `crv`, BSD), the scoreboard against the blind model, and functional coverage (cocotb-coverage `CoverPoint`/`CoverCross`) all run unchanged in Icarus, Verilator and xsim. SystemVerilog classes, `randomize()` and covergroups are **not** used in the agent's benches. |
| Assertions | `sva`: Icarus "concurrent_assertion_item not supported"; Verilator and xsim run `\|=>` with `$past`. `seq`: Verilator 5.020 "Unsupported: ## in sequence". `pastact`: explicit-clock `$past` fails in Verilator. | **A subset both accept:** immediate assertions; concurrent `\|->` and `\|=>` with `$past` in the implicit-clock form inside `assert property (@(posedge clk) ...)`; no `##` sequences while CI is on Verilator 5.020. Written in a checker module attached by `bind`. |
| Formal | not in the matrix | SymbiYosys with open Yosys 0.33 and z3, on control logic only (bounded proofs and cover). |
| Code coverage | n/a | Verilator `--coverage-line --coverage-toggle --coverage-user` in CI; bin counts from `coverage.dat`. |

The checker's property source is one macro file (`verif/checkers/v_macros.svh`) with three readers:
Verilator and xsim read concurrent assertions; Yosys 0.33 cannot read `assert property (@(posedge clk) ...)` (it
stops with `unexpected '@'`), so under `-DFORMAL` the same property is emitted as an immediate assertion in an
`always` block; Icarus compiles the checker to nothing. Checkers whose properties are over ports only
(`debounce_checker`, `scan_checker`) are used by the formal wrappers; `counter_checker` needs internal signals and
is bound in simulation.

### What a newer Verilator changes (re-tested, 5.048)

Verilator 5.048 (Ubuntu questing `.deb`, extracted rootless; `source ~/.local/opt/verilator-5048/env.sh`):

- `##1` sequences run (`a ##1 b |-> 0` fired in simulation). 5.020: "Unsupported: ## in sequence".
- `rand` plus `constraint` plus `randomize()` runs, **only if `z3` is on `PATH`** (otherwise "Unable to communicate
  with SAT solver"). 5.020 warned `CONSTRAINTIGN` and ignored the constraint.
- Covergroups parse but are **ignored**: `COVERIGN: Ignoring unsupported: coverpoint`. Nothing is collected, so
  functional coverage still has to come from the Python bench. 5.020 rejected them outright.
- cocotb 2 needs Verilator 5.036 or newer, so **the cocotb bench cannot run on the apt Verilator 5.020**. The
  bench runs under Verilator 5.048 and under Icarus. The matrix has a fifth column for the cells re-run
  (branch `verilator-5048-retest` of `SystemVerilog_Simulators`).

Even with `##` and `randomize()` available, the decisions above stand: the bench stays in Python because
covergroups remain unsupported in every free tool but xsim, and one bench must run everywhere.

## Files

```
designs/<d>/verif/testplan.yaml        requirements -> tests / assertions / cover_props / bins / formal; thresholds; waivers
designs/<d>/verif/checkers/            v_macros.svh, *_checker.sv, t1_bind.sv
designs/<d>/verif/formal/              *.sby and their wrappers
designs/<d>/verif/portability.yaml     file sets for flow/portability.py
designs/<d>/verif/mutants.yaml         the mutation set for flow/mutate.py
designs/<d>/tests/t1_verif.py, t1_cov.py, test_t1_verif_rtl.py     V2 tests, coverage bins, pytest entry
flow/verif_gates.py  flow/portability.py  flow/mutate.py  flow/formal.sh
```

Run order for a design (T1 shown):

```
SIM=verilator T1_SEEDS=1,2,3 pytest designs/t1_dimmer_counter/tests/test_t1_verif_rtl.py   # Verilator 5.036+; checkers bound; code coverage
SIM=icarus    T1_SEEDS=1,2,3 pytest designs/t1_dimmer_counter/tests/test_t1_verif_rtl.py   # the same bench, Icarus
flow/formal.sh designs/t1_dimmer_counter
python3 flow/portability.py designs/t1_dimmer_counter/verif/portability.yaml
python3 flow/mutate.py designs/t1_dimmer_counter --json results/04f/mutation_t1.json   # local; about 30 minutes
python3 flow/verif_gates.py designs/t1_dimmer_counter --also build/verif/icarus --mutation results/04f/mutation_t1.json \
    --hw results/f0b/t1_dimmer_counter_bringup.json --json results/04f/t1_verif_gates.json
```

The portability check compiles the checkers and bind file with Icarus, every Verilator in `$PORT_VERILATORS`, slang
(pyslang) and xsim (skipped when Vivado is not sourced, as in CI), and fails on a deliberately non-portable
covergroup fixture (`flow/tests/fixtures/nonportable_covergroup.sv`, tested in `flow/tests/test_portability.py`).

## Limits

- An assertion that never fires is not evidence it works: the cover properties show the antecedents are reachable
  and the mutation run shows the checkers kill mutants, but there is no per-assertion vacuity report.
- The functional bins are hit counts of events the bench caused; they say what was exercised, not what was checked.
  Checking is the model comparison and the assertions.
- Mutation testing of the agent's own benches (against RTL written elsewhere) is the check later benches will be
  measured with; the T1 numbers are in [results/04f](../results/04f/README.md).
