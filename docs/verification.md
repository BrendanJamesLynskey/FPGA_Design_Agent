# Verification: V-stages on a simulator-portable stack (brief 04f)

UG949 (the UltraFast methodology, [methodology.md](methodology.md)) covers implementation, not verification. The
closest open equivalent of a staged verification sign-off is OpenTitan's (Apache-2.0): *development stages* and the
DV methodology's V0-V3 checklist (docs.opentitan.org, "Hardware Development Stages" and "Design Verification
Methodology" / "Checklists", read 2026-11-01). This repo adopts their structure, and replaces the parts that need
a paid simulator. The independent-checking rule of the house rules still applies: the agent's own testbench never
counts as a pass; the hidden tests, the formal checks and the hardware do.

## The stages

| Stage | OpenTitan | What it requires here | Exit checks (`flow/verif_gates.py`, raw numbers) |
|---|---|---|---|
| V0 plan | V0: testbench and testplan started | a testplan file, the reference model and the bench modules exist | files present |
| V1 testplan | V1: testplan written and reviewed; testbench connected to the model; smoke test passes | `verif/testplan.yaml` generated from `spec.yaml`; every spec statement traced to tests, assertions, cover points, bins or formal tasks (a DO-254 style traceability matrix); the bench compares against the reference model | spec items traced / total (must be all); no unresolved name; no requirement without a check |
| V2 tests complete | V2: directed and constrained-random tests written and passing; assertions in; FPV on control logic | every planned test passes on every seed; the constrained-random test ran; checkers are bound and no assertion fires; formal bounded proof and cover pass on the control logic | failing / missing tests; formal tasks not PASS |
| V3 coverage closed | V3: coverage closed with waivers, all seeds passing, no open bugs | functional bins and cover properties all hit; line and toggle coverage at stated thresholds; every waiver carries a reason; at least `seeds_min` seeds, all passing; the bench's mutation score at its threshold | each percentage against its threshold; unhit bins and cover properties listed |
| V-HW (ours) | none | the board bring-up against the model passes (`results/f0b_2026_1/*_bringup.json`, `pass: true`, with its build stamp) | pass flag |

OpenTitan's V2S (security countermeasures) does not apply to these designs.

### Where the V-stages join the UltraFast stages

The agent's stage machine ([methodology.md](methodology.md)) has nine stages. V0 and V1 start when the spec is
signed off (stage 0) and the reference model is written; V2 and V3 sit **inside stage 2** (`rtl-design-creation`):
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
| `simulation` | a cocotb test (`module.test`) compared with the reference model | the test passed on every seed (`results.xml`) |
| `formal` | a SymbiYosys job in `verif/formal` | both its `bmc` and `cover` tasks `PASS` |
| `hardware` | a bring-up step or `step:case` (`uart_tests`, `uart_tests:test_x`, `ila_captures`) | that step passed in the bring-up JSON |
| `analysis` | a flow gate, `stage:gate` (`post_route:setup`, `post_synth:post_synth_resources_in_range`) | the gate in `gates.json` is true |

V2's formal check covers the formal tasks the testplan names (`formal:` of each requirement): each must have both its `bmc` and `cover` tasks `PASS`. A plan that names none (every formal method re-planned because SymbiYosys is absent, or no requirement uses it) passes the check; whether a requirement needs formal is decided by its `proof` list in `spec.yaml`, which V1 and the sign-off table enforce. When no `seed*/results.xml` exists the gate says so in one line (the directory read, the file expected, how `flow.cocotb_run.run(..., seed=N)` under `simulate` produces it) and shows the checks that depend on it as `not evaluated (no seeded results)`.

The clarify stage proposes a method per requirement; where it does not, the interview asks one question per
requirement with a default (`agent.graph.spec_schema.propose_proof`) and the reason for it. The Verifier then
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
5.020 / xsim / Questa Starter; commit 485f024) decides it. The matrix's xsim column was made on an earlier Vivado release and
has not been re-checked on 2026.1 as a whole; the covergroup row has ([results/24_fsm_2026_1/simprobe](../results/24_fsm_2026_1/simprobe/survey.txt)). Free tools only (owner decision).

| Need | Matrix says | Decision |
|---|---|---|
| Constrained random, covergroups | `rand`: only xsim runs it among the free tools; Questa Starter needs a paid licence. `cov`: Icarus no, Verilator 5.020 "Unsupported: covergroup", xsim partly; Questa Starter paid. xsim cannot run in CI. | **The bench is Python (cocotb).** Stimulus, constrained random (cocotb-coverage `crv`, BSD), the scoreboard against the reference model, and functional coverage (cocotb-coverage `CoverPoint`/`CoverCross`) all run unchanged in Icarus, Verilator and xsim. SystemVerilog classes, `randomize()` and covergroups are **not** used in the agent's benches. |
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
    --hw results/f0b_2026_1/t1_dimmer_counter_bringup.json --json results/04f/t1_verif_gates.json
```

The portability check compiles the checkers and bind file with Icarus, every Verilator in `$PORT_VERILATORS`, slang
(pyslang) and xsim (skipped when Vivado is not sourced, as in CI), and fails on a deliberately non-portable
covergroup fixture (`flow/tests/fixtures/nonportable_covergroup.sv`, tested in `flow/tests/test_portability.py`).

## V3 floors the testplan cannot lower (brief 05n)

`flow/verif_floors.yaml` is a fixed file of the harness: functional bins 100%, cover properties 100%, line 90%, toggle 75%,
mutation score 70%, `seeds_min` 3 (each value carries a comment saying where it comes from). The gate uses
`max(floor, testplan value)`: a testplan may raise a threshold but a value below its floor is ignored, and the check's
`why` says so ("testplan asked 0%, the floor is 100%"). A waiver with a reason is still the only way to excuse a named bin or
cover property. A mutation score also counts only when enough mutants were evaluated (`mutation_min_evaluated`: 10, or every
candidate when fewer exist); otherwise the check says "not enough mutants evaluated: N of M (skipped K by the wall cap)".
`flow/mutate.py` scales its wall cap with the baseline (baseline x (sample + 2), between 1500 s and 2 h) and, when even 2 h is
too short, shrinks the sample (never below 10) instead of skipping mutants.

## Preconditions of the V3 checks

A failed check carries a plain-words `why`. Several checks need evidence that only a particular run produces, and
say so when it is absent: `functional_bins_pct` needs at least one planned bin and a functional-coverage file
(`seed*/coverage*.yml`, exported by the bench to `$FDA_COV_OUT`); the cover-property, `line_pct` and `toggle_pct`
checks need `seed*/coverage*.dat`, which the Verilator coverage run records; `mutation_score_pct`
needs a mutation result (`build/verif/mutation.json`). **The graph produces both itself (brief 05l).** At stage 2 with
level V3, once V0 to V2 pass, `node_gate` runs `simulate(sim="verilator", coverage=True)` (every seed the bench
runs) and then the `mutate` step, and gates again; the result files are the ones the gates read. The same sources
are not run twice (a hash of rtl/, tests/, verif/, model.py and spec.yaml). A step that cannot run (the heavy lock
stays busy past the wait, no Verilator 5.036+, the bench fails under Verilator) is recorded in
`build/verif/v3_evidence.json`, and the gate says so in the `why` of the check it leaves `not measured`. The tests
role is given no `simulate` or `mutate`: its repair texts say what the evidence showed (unhit cover properties by
name, line and toggle gaps as file:line, surviving mutants as file, line and change) and what it can do about it (add
or extend tests, add `V_COVER` points, tighten checks). `mutate` stays a registered tool (owner and MCP use) but no
role is offered it; `agent/tests/test_05l.py` fails if any text names a tool the role to whom it is addressed lacks.

### The `mutate` tool (`flow/mutate.py --generic`)

It runs the design's own `tests/test_*_rtl.py` (Icarus, the bench's own seeds) against mutated copies of `rtl/`:
the design's `verif/mutants.yaml` when it has one, else operator mutants generated from the RTL (`==`/`!=`,
`&&`/`||`, `+`/`-`, `<`/`>=`, `>`/`<=`, a removed `!`, a flipped 1-bit constant), sampled with a recorded RNG seed.
The unmutated RTL must pass first, or nothing is written. Caps (defaults): 20 mutants, 1500 s wall time in all, a
per-mutant timeout of 4 times the baseline run (30 to 600 s). A mutant is killed only when its run fails. Invalid
mutants (the copy does not compile) are excluded; timed-out mutants count as not killed; mutants the wall-time cap
left unrun are listed as skipped and excluded. `score_pct` is killed / (killed + survived + timed out). An equivalent
mutant (no visible behaviour change) shows as a survivor, so a score below 100 is not always a weak bench. The result
lists each survivor in words (file, line, the change); `gates(kind=verif)` repeats up to five in the failing check's
reason. The tool takes the machine's heavy-job lock (`$FDA_HEAVY_LOCK`) under a memory cap, and answers `busy, retry`
when it is held. 

### The CDC checks (brief 16)

A design with a clock-domain crossing (an `ASYNC_REG` register, an XPM CDC macro, or several clock domains in
`architecture.yaml`) gets two more V3 checks, because `report_cdc` alone passes a bus crossed bit by bit, two
synchronisers whose outputs are combined, and a pulse into a level synchroniser (CDC rig 11b):

- `cdc_structure_clean`: the post-synthesis structural check (`flow/cdc_paths.tcl` + `flow/cdc_structure.py`, read from the
  flow's `gates.json`, gate `post_synth_cdc_structure_clean`). Every asynchronous path in the netlist is classified; a
  CDC-6 Warning row is safe only on an XPM Gray/handshake/FIFO instance, or a hand-built bus, that carries its
  `Max Delay Datapath Only` exception.
- `cdc_injection_clean`: `flow/cdc_inject_run.py` runs the design's own `tests/test_*_rtl.py` plain and with 4 seeds of
  synchroniser-delay injection; a test that passes plain and fails injected fails the gate. A missing report fails the check.

The fixtures that prove both are in `flow/tests/fixtures/cdc_mutants/` (rig mutants M1-M8, M10 and correct variants C1-C12);
the table is `results/16_cdc_gate_2026_1/mutant_table.md` (re-measured on Vivado 2026.1, identical).

## Independent spec-only tests (brief 08f, `eval-2`)

Every escape so far shares one cause: the agent's tests are written in the same context as the design, so they repeat its
misreading (c10 DDS run 1, tiny CNN: the model, the RTL and the bench agreed, and every internal gate passed). With
`--spec-tests` (off by default; `eval-1` behaviour is unchanged) a second reader is added after V2/V3
(`agent/graph/spectest.py`):

1. **Spec-test role**, one headless Claude Code call of its own (Sonnet, no tools, no design directory). It is given only
   `spec.md`, the interview (`resolved_questions` of `spec.yaml`; an answer the requester did not give is labelled NOT
   CONFIRMED and must not be tested), the board pack (`board.yaml`, master-XDC port names), the task's `data/` files and, for a
   shell design, the shell protocol and UART bus model. It never sees the RTL, `model.py`, the agent's tests or the rest of
   `spec.yaml`. It returns `spectest/spec_ref.py` (its own model) and `spectest/spec_bench.py` (a cocotb bench).
2. **Gate.** When V2/V3 pass, the harness writes the pytest entry itself and runs the bench against the RTL (Icarus, results
   from `results.xml`). A pass is recorded. A failure goes to a **triage** call that sees the spec, the interview and both benches
   (never the RTL) and answers `design_wrong` (the failing check goes to the RTL role as a `[spec test]` repair; Vivado is
   skipped that visit) or `bench_wrong` (the spec-test role repairs its bench once, then the bench runs again; bench_wrong a
   second time is `unresolved`). An unreadable verdict counts as bench_wrong: a design is never failed on a guess.
   `--spectest-max-loops` (default 2) limits design_wrong round trips per run; past it the result is `unresolved` and does not
   block. Any infrastructure fault is `error` and does not block.
3. **Record.** `build/spectest/state.json` (fired, passed, caught_bug, bench_repaired, verdict counters), copied into the run
   summary and into the course run record by `tools/run_record.py` as `spec_test`.
4. **Unchanged paths.** `agent/tests/test_08f_golden_requests.py` compares hashes of every other request path (prompts,
   conventions, checklists, per-role plans, Claude Code argv and MCP arguments, oracle prompt, role map, tool registry) with the
   values taken at the `eval-1` tag.

**Offline replay** (`tools/spectest_replay.py`, results in [results/08f](../results/08f/)): the role run against saved final
designs, once each, no RTL repair. Of the two escapes the brief names, it caught one: the tiny CNN (the bench decoded the weights
as signed bytes and the design answered `B` for pictures 0 and 7). The c10 design had not been kept, so it was rebuilt from the
reference RTL with the DATA word packed as two sign-extended halves; the role's bench decoded `[11:0]`/`[27:16]` only and
passed it, because the register map the requester gave does not say that the other bits read 0 (the hidden bench asserts it).
No correct design failed (0 of 4). Of five escapes in all, one was caught. The bench repair fired twice, both for the role's own
mistakes (a PTR count, a wrong port name). Full table: `reports/08f_eval2_build_report.md`.

## Limits

- An assertion that never fires is not evidence it works: the cover properties show the antecedents are reachable
  and the mutation run shows the checkers kill mutants, but there is no per-assertion vacuity report.
- The functional bins are hit counts of events the bench caused; they say what was exercised, not what was checked.
  Checking is the model comparison and the assertions.
- Mutation testing of the agent's own benches (against RTL written elsewhere) is the check later benches will be
  measured with; the T1 numbers are in [results/04f](../results/04f/README.md).
