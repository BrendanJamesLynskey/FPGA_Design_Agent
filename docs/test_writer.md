# The Verifier, the turn trace and the QoR gate (brief 05g, F2 part 7)

Plain code throughout: the stage machine, the gates and the budgets stay deterministic. No memory, self-check or
spec-vector feature was added (the CVDP nulls stand).

## Diagnosis: why the Verifier failed (from the run records)

| Failure | Cause | Evidence | Fix |
|---|---|---|---|
| luna run `20261103-004742-f7ba`, stage 9: "no tests/test_*_hw.py" four times, then the 300-turn stop | **ran out of turns, twice the role never got a turn.** The stage-9 Designer ran first and used the whole 30-turn stage budget (checkpoint detail: "stage turns limit 30 reached" at visits 1 and 2); the budget error left `node_work`, so the tests role was skipped. In visit 3 it got turns (its `gates`/`search_docs` calls are the last audit rows) and the run limit (300) ended it before it wrote anything. | checkpoints.sqlite detail per visit; `build/audit.jsonl` has no stage-9 `write_file` | `ROLE_TURN_RESERVE` holds 15 turns of the stage and run budgets back while the stage-9 Designer runs; a role that ends on its budget no longer ends the visit; stage 9 limit 30 -> 45 (the Designer keeps 30) |
| same run: the role was also pointed at `shell.host.fpga_shell` it could not read | **a tool refused it.** The Designer asked for `@shell/host/fpga_shell.py` four times (path-jail: not in the read-only view); the tests role had no shell view at all and, under Deep Agents, no file tool for it. The stage-9 prompt tells it to import `FpgaShell`. | audit rows 234, 284, 326 | tests role: read-only view of `@shell/PROTOCOL.md`, `host/protocol.py`, `host/fpga_shell.py` (not the shell RTL, not the design RTL); the same files are seeded in its prompt as `shell_ref/...` so both harnesses have them |
| 05f cvdp run 1 `0d63`: last gate V0 `testplan_present` | **the arm's repair visit deleted the role's own output.** `run_subagent_cc` collected "files of an earlier attempt" for every tests-role call and dropped the ones not rewritten; Deep Agents guards this with `not repair`, the arm did not. The last repair wrote only `verif/formal/*` and removed `tests/` and `verif/testplan.yaml`. | final tree: `tests/` empty, `verif/` only `formal/`; trace seq: repair writes 4 formal files | `tests_before` only when `not repair` |
| 05f cvdp run 2 `9b4d`: V1 `proof_methods_discharged` REQ-03, REQ-04 `formal` | **the artefact was never produced, and the role could not produce it.** The same deletion made the next visit a fresh one; the tests role has no `formal` tool, SymbiYosys was not on the agent's PATH, the Designer's formal writes were refused (`verif/` is the tests role's), and the prompt gave no way out. No `proof:` entry for the two requirements existed. | final testplan has no formal entries; `verif/formal` absent | tests role gets the `formal` tool and a checklist: write the job and run it, or (when `sby` is absent) `replan:` the method with a reason; `verif_gates` accepts only that, never an unevidenced proof |

Not the cause in any of the three: the prompt did ask for the testplan (it is in `PROMPTS["tests"]`), and the files
were written where the gates look. Two smaller defects went with them: `load_skill(["verification-stages"])` (the
sections the prompts name) returned nothing because those sections live in the procedures layer, and `list_files tests`
was refused for the tests role.

## What changed

- **Turn budgets and trace.** `agent/graph/run.py`: `run_role`, `ROLE_TURN_RESERVE` (`{2: {model: 35, tests: 25}, 9: {rtl: 15}}`),
  `Meter.reserved` / `turns_left()`; stage 2 limit 60 -> 80, stage 9 30 -> 45. `role_usage.jsonl` gains `visit`,
  `turns_allowed`, `ended` (done / stage_budget / run_budget / blocked / error), `tools`, `refused`, `files_written`;
  `summary.json` gains `turn_trace`, so the next failure shows which role had how many turns and what stopped it.
- **Stage-entry checklist** (`tests_checklist`): the exact files each gate reads (`tests/test_<name>_rtl.py`, the bench
  modules, `verif/testplan.yaml` with its `proof:` list, the formal job or the re-plan, the stage-9 `tests/test_<name>_hw.py`
  and `hw_checks.py`), added to the tests role's prompt for both harnesses.
- **Formal.** The tests role has the `formal` tool; it says plainly when `sby` is absent. Testplan `replan:`
  `[{requirement, method: formal, replaced_by: simulation|analysis|hardware, artefact, why}]` discharges a formal method
  only when SymbiYosys is not installed, needs a reason and an artefact that resolves, and the sign-off table judges it by
  the replacement's evidence (the row says "re-planned from formal").
- **Knowledge use.** The bank was reachable (sibling checkout `FPGA_Design_Agent_Knowledge`, `FDA_KNOWLEDGE` overrides; the
  Claude Code arm's tool server resolves the same path). `load_skill` now returns procedures-layer sections when asked for
  them without `procedures`, and the audit records the skill paths returned, the sections that returned nothing and the
  fallback; `knowledge_use` adds `empty_calls`, `sections_empty`, `procedures_fallback` and the `search_docs` hit ids;
  `summary.json` has `knowledge_bank` (path name, how chosen, loaded, HEAD). Nothing forces a skill to be loaded.

## The QoR gate

On Vivado 2026.1's free Basic tier this gate is absent, not passed ([methodology](methodology.md#qor-on-basic)). This section describes the
gate where the report runs; no 2026.1 QoR figures exist, so none are quoted.

`post_route_qor_assessment` (score >= 4 in `qor_assessment_route.rpt`) is the gate, in the `post_route` stage.
`post_synth_qor_assessment` is a recorded warning (`stages.post_synth.warnings`, top-level `warnings`, the review page's
"Warnings" table), not a gate. Reason: on an earlier Vivado release, on small designs the post-synthesis predicted-congestion
item scored below the routed score (benchmark 06a); this cannot be re-checked on the 2026.1 Basic tier.

## Live checks (T1, oracle, review off, V1; records in `results/f2/`)

- luna `single`: null at stage 2 (Designer; lint then simulate). Not a Verifier failure: V0 and V1 passed.
- `cvdp` profile: **stage 2 passed at visit 2** (05f: 0 of 2). The Verifier's visit-1 failure (formal methods named as bench
  tests, no SymbiYosys) was repaired in 2 turns by a `replan:` with reasons, and its other files survived the repair. Null at
  stage 3 (`post_synth_no_unconstrained_endpoints`, the stage-3 writer's `design.xdc`), outside this brief.
- Stage 9, by resuming the recorded luna run from the end of stage 8: the tests role now gets its turns (visit 1: reserved 15,
  used them on `gates` only; visit 2: wrote `hw_checks.py` and `tests/test_*_hw.py`), `bringup_ready` is READY and the run stops at
  "awaiting approval before programming". The board was not touched.
- Found, not fixed live: a cocotb bench that keeps the spec's `DEBOUNCE_CYCLES = 2,000,000` ran for minutes of wall time per
  simulate (the tool's own limit is 30 minutes). The checklist now says to override long timing parameters through `parameters=`; this
  line has unit tests but no live run behind it.
