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

## A proof method per requirement (brief 05d)

Adam Taylor's FPGA Horizons issue 5 article ("What Star Trek can teach us about using AI in FPGA design") asks that
every requirement say, up front, how it will be shown to hold. `spec.yaml` therefore has a `requirements:` list,
each entry `{id, text, proof}` with `proof` a non-empty list from four methods:

| Method | What discharges it | Evidence the sign-off reads |
|---|---|---|
| `simulation` | a cocotb test (`module.test`) compared with the blind model | the test passed on every seed (`results.xml`) |
| `formal` | a SymbiYosys job in `verif/formal` | both its `bmc` and `cover` tasks `PASS` |
| `hardware` | a bring-up step or `step:case` (`uart_tests`, `uart_tests:test_x`, `ila_captures`) | that step passed in the bring-up JSON |
| `analysis` | a flow gate, `stage:gate` (`post_route:setup`, `post_synth:post_synth_resources_in_range`) | the gate in `gates.json` is true |

V2's formal check covers the formal tasks the testplan names (`formal:` of each requirement): each must have both its `bmc` and `cover` tasks `PASS`. A plan that names none (every formal method re-planned because SymbiYosys is absent, or no requirement uses it) passes the check; whether a requirement needs formal is decided by its `proof` list in `spec.yaml`, which V1 and the sign-off table enforce. When no `seed*/results.xml` exists the gate says so in one line (the directory read, the file expected, how `flow.cocotb_run.run(..., seed=N)` under `simulate` produces it) and shows the checks that depend on it as `not evaluated (no seeded results)`.

The clarify stage proposes a method per requirement; where it does not, the interview asks one question per
requirement with a default (`agent.graph.spec_schema.propose_proof`) and the reason for it. The test writer then
adds a top-level `proof:` list to `verif/testplan.yaml`, `{requirement, method, artefact}`, giving every method of
every requirement at least one artefact. Two places enforce it:

- **V1** (`flow/verif_gates.py`) fails on `requirements_have_proof_method` (a requirement without a valid method),
  `proof_methods_discharged` (a method with no artefact in the testplan) and `proof_references_resolve` (a test or
  formal job that does not exist);
- **sign-off** (`SIGNOFF` in the same output, `traceability` table: requirement, method, artefact, result) fails
  unless every row is `pass`. A row is `pending` while its evidence source does not exist (no board result yet), and
  `pending` is not a pass. The graph runs it at the end of stage 9, after the bring-up. `--require-signoff` makes
  the command exit 1 on it.

T1's table is in `designs/t1_dimmer_counter/verif/testplan.yaml` (8 requirements, 16 rows). The review pages show it.

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

The canonical copy is `flow/v_macros.svh`. The agent seeds it into `verif/checkers/` of every new or resumed run (brief 05i); the roles cannot write it, and `gates(kind="verif")` warns if the copy differs. The V1 gate reads `A_*`/`C_*` names only from `V_SAME/V_NEXT/V_RST/V_COVER(name, ...)`; a name declared as plain SystemVerilog is reported as such.

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

## Preconditions of the V3 checks

A failed check carries a plain-words `why`. Several checks need evidence that only a particular run produces, and
say so when it is absent: `functional_bins_pct` needs at least one planned bin and a functional-coverage file
(`seed*/coverage*.yml`, exported by the bench to `$FDA_COV_OUT`); the cover-property, `line_pct` and `toggle_pct`
checks need `seed*/coverage*.dat`, which `simulate(sim="verilator", coverage=True)` records; `mutation_score_pct`
needs a mutation result (`build/verif/mutation.json`), which no agent tool produces yet and is reported as
`not measured`. A stage-2 run that the agent has no tool for stops at the level it can reach (`--verif-level`).

## Limits

- An assertion that never fires is not evidence it works: the cover properties show the antecedents are reachable
  and the mutation run shows the checkers kill mutants, but there is no per-assertion vacuity report.
- The functional bins are hit counts of events the bench caused; they say what was exercised, not what was checked.
  Checking is the model comparison and the assertions.
- Mutation testing of the agent's own benches (against RTL written elsewhere) is the check later benches will be
  measured with; the T1 numbers are in [results/04f](../results/04f/README.md).
