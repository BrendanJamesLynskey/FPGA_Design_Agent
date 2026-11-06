# Course tier: improvements log (brief 07a2)

Each fix: the run that exposed it, the PR, the re-run result.

| Fix | Exposed by | PR | Re-run |
|---|---|---|---|
| Task `data/` files reach agent runs and the Vivado build | 07a1 report (three tasks have data) | #43 (07a2-prep) | not exercised by `c14_int8_dot_requant` (no data); unit tests only |
| `no_shell` honoured by agent-side build, lint, simulation, mutation | 07a1 report | #43 | unit tests only (no UART-subject task run yet) |
| Dependency-ordered SystemVerilog compile | 07a1 report | #43 | unit tests; the smoke design had no package |
| Oracle register-map answers (rendered map, white-space-tolerant quote check) | 07a1 report | #43 | smoke run 1: the oracle was asked about shell addressing, answered "partly specified"; see open item |
| `--oracle claude_code` (no OpenRouter), `FDA_HEAVY_LOCK` passed to the mutation tool | smoke run 1 set-up | #43 | smoke run 1 used both |

## Open (found by run 1, not fixed)

- `c14_int8_dot_requant` run 1: scored 0/6. The agent never asked for the register offsets, which only `hidden/spec.yaml` holds, and invented its own map. Candidate fixes for the planner: a clarify-stage instruction to ask for the register map when the request does not give it, and an oracle that answers a register-addressing question with the whole map. Not a task edit (the tier is frozen).
