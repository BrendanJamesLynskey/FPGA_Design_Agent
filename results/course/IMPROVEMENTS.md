# Course tier: improvements log (brief 07a2)

Each fix: the run that exposed it, the PR, the re-run result.

| Fix | Exposed by | PR | Re-run |
|---|---|---|---|
| Task `data/` files reach agent runs and the Vivado build | 07a1 report (three tasks have data) | #43 (07a2-prep) | not exercised by `c14_int8_dot_requant` (no data); unit tests only |
| `no_shell` honoured by agent-side build, lint, simulation, mutation | 07a1 report | #43 | unit tests only (no UART-subject task run yet) |
| Dependency-ordered SystemVerilog compile | 07a1 report | #43 | unit tests; the smoke design had no package |
| Oracle register-map answers (rendered map, white-space-tolerant quote check) | 07a1 report | #43 | smoke run 1: the oracle was asked about shell addressing, answered "partly specified"; see open item |
| `--oracle claude_code` (no OpenRouter), `FDA_HEAVY_LOCK` passed to the mutation tool | smoke run 1 set-up | #43 | smoke run 1 used both |
| Clarify stage asks for the register map when the request names registers or the test shell without offsets (prompt + clarify gate: no map question, or an answered map missing from `registers.map`, fails the gate); the oracle answers a register-addressing question with the whole map, one register per line | run 1 (`c14_int8_dot_requant`, 0/6: invented map) | #45 (a197745) | run 2: the agent asked for the map, got all 11 registers, every register read passes; 5 of 6 tests pass; new failure, see below |
| Top-level port names must be master-XDC names or buses of them (FDA-CON-7 in `check_constraints`; `LED0` is told to be `LED[0]` of bus `LED`; `JA1`, `QSPI_DQ0`, `ACL_INT1` stay valid) | run 2 (`c14_int8_dot_requant`, 5/6: scalar `LED0`) | #47 | run 3: the agent's design.xdc and top use bus `LED`; the RTL it left passes 6/6 under `run_task.py`; but the run stopped at stage 2 (its own cocotb bench would not import); new failure, see below |
| Simulate keeps the first exception of the simulator log (root cause) at the head of the failure summary; every Python file under `tests/` is imported before simulating and an import error comes back as `kind: import_error`; the run summary counts the questions of every clarify visit (the second visit no longer replaces the first); the tests prompt names the CoverPoint parent rule; Knowledge skill `cocotb-coverage-usage` | run 3 (`c14_int8_dot_requant`: bench import error hidden behind a follow-on error; `questions.asked` 0 with 5 answered) | #49; Knowledge #19 (a8ba042) | run 4: bench imported, dotted CoverPoint names, summary counted 6 questions; run got further (simulate pass, mutation 17 of 17, synth gates pass), RTL 6/6, but stopped at stage 2 on the V3 cover-property gate; new failure, see below |

## Open (found by run 1, not fixed)

- `c14_int8_dot_requant` run 1: scored 0/6. The agent never asked for the register offsets, which only `hidden/spec.yaml` holds, and invented its own map. Candidate fixes for the planner: a clarify-stage instruction to ask for the register map when the request does not give it, and an oracle that answers a register-addressing question with the whole map. Not a task edit (the tier is frozen).

- Run 1's open item above is closed by the #45 row.

## Open (found by run 2, not fixed)

- `c14_int8_dot_requant` run 2: 5 of 6 tests pass; `test_ready_clears_on_go_and_regs` fails because the agent's top has a scalar port `LED0`, while the bench (and the board's master XDC) use the bus `LED`. The task text says "LED0 shows the ready flag" and the conventions say "ports named as in the board's master XDC"; the agent followed the first. Class: spec ambiguity plus a weak check (`check_constraints` accepted a port name that is not in the master XDC). Candidate harness fix for the planner: reject a top port whose name is not a master-XDC name (or a bus of one) in the constraints stage. Not applied: brief says stop on a new failure.

- Run 2's open item above is closed by the #47 row.

## Open (found by run 3, not fixed)

- `c14_int8_dot_requant` run 3: stopped at stage 2 ("visited more than 4 times"); no Vivado run, no QoR. The tests role wrote `tests/c14_bench.py` with module-level `@CoverPoint(...)` decorators; cocotb_coverage raised `CoverPoint must have a parent` at import, and cocotb then failed with a follow-on `AttributeError: ... '_running_test'`. All nine `simulate` calls failed at 0 ns. The `[first failure]` block in the simulate tool's output elides the frames holding the root-cause line, so the agent chased the follow-on error for six loops. Class: model error (cocotb_coverage misuse) plus a harness gap (failure summary hides the root cause). The RTL it wrote scores 6/6 under `run_task.py`. Candidate fixes for the planner: keep the first `Exception:` line of a collection-time import error in the summary; a KB note on CoverPoint naming; an import check of `tests/` before simulating. Not applied: brief says stop on a new failure.

- Run 3's open item above is closed by the #49 row.

## Open (found by run 4, not fixed)

- `c14_int8_dot_requant` run 4: stopped at stage 2 ("visited more than 4 times"); only the post-synthesis stage ran in Vivado, so no placed QoR. V3 `cover_properties_pct` was 0.0: the agent's `tests/test_c14_int8_dot_requant_rtl.py` builds its sources from `SHELL_RTL` and `rtl/*.sv` only, so the bound checker with the `V_COVER` points is never compiled into the Verilator coverage run. The reference test of the T1 design adds `verif/checkers/*.sv` when `SIM=verilator`; nothing in the tests-role prompt or the verification-stages skills says so. Each Icarus `simulate` also took about 6 minutes. Class: harness gap (missing convention) plus model error. The RTL scores 6/6 under `run_task.py`. Candidate fix for the planner: state in the tests-role conventions and the v2 skill that the Verilator run must add the checker files (bind file last). Not applied: brief says stop on a new failure.
