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

## Open (found by run 1, not fixed)

- `c14_int8_dot_requant` run 1: scored 0/6. The agent never asked for the register offsets, which only `hidden/spec.yaml` holds, and invented its own map. Candidate fixes for the planner: a clarify-stage instruction to ask for the register map when the request does not give it, and an oracle that answers a register-addressing question with the whole map. Not a task edit (the tier is frozen).

- Run 1's open item above is closed by the #45 row.

## Open (found by run 2, not fixed)

- `c14_int8_dot_requant` run 2: 5 of 6 tests pass; `test_ready_clears_on_go_and_regs` fails because the agent's top has a scalar port `LED0`, while the bench (and the board's master XDC) use the bus `LED`. The task text says "LED0 shows the ready flag" and the conventions say "ports named as in the board's master XDC"; the agent followed the first. Class: spec ambiguity plus a weak check (`check_constraints` accepted a port name that is not in the master XDC). Candidate harness fix for the planner: reject a top port whose name is not a master-XDC name (or a bus of one) in the constraints stage. Not applied: brief says stop on a new failure.
