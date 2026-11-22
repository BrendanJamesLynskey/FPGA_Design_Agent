# b82p7: the 4 h measured re-run of the UDP endpoint task with stage-2 time fixes (pre-registration)

Written 2026-11-21 on branch `b82p7-stage2-time`, committed before the first run. Development measurement, not a held-out evaluation.
Nothing here reads, lists or copies a held-out task.

## Why

82P6 (`../b82p6/results.md`) was 0 of 6 by the 4 h rule, but four runs held 10/10 hidden tests at the 3 h snapshot. Their own stage-2 gates never
passed, so none stopped on its own. `posthoc/time_table.md` (from the 82P6 records and run directories, `posthoc/time_table.py`) shows where the
240 minutes went, pooled over the six runs (19.6 h):

- **Icarus cross-check 29 % of all wall time** (gate calls of 17 to 30 minutes at *every* stage-2 visit that got past the Verilator run; nine
  1800 s time-outs, one of which ended A r1 on the visit limit while the same bench passed on Verilator in 7 minutes). Verilator gate runs 14 %.
- **Role time 33 %** (39 to 106 of 240 minutes per run), of which the roles' own `simulate` calls (9 to 80 minutes per run).
- **Waiting for the Vivado slot in the synthesis gate** in the three arm-B runs that reached it (47 to 112 minutes per run): the cap counter counted a
  40-hour-old shell whose command line named the Vivado path.
- A repeated wrong design ID that alternated between visits never counted as "persisting" (A r3), and a time-out stop had no assertion (A r1).

## Changes under test (frozen code commit recorded in `environment.txt`; branch `b82p7-stage2-time` on `b82p6-routing-4h`)

Each follows from the table. Unit tests: `agent/tests/test_82p7_stage2_time.py`, `flow/tests/test_82p7_vivado_count.py`.

1. **Icarus cross-check once, last** (`agent/graph/run.py: simulate_gate(cross_check=False)`, `icarus_cross_check`, `node_gate`). Stage 2 runs the bench
   on Verilator at every visit and runs Icarus only when every other stage-2 gate before synthesis has passed (lint, contract, the Verilator run, V2/V3
   verification, standards, constants, the spec-test bench). It still decides the gate: a failure is a simulation failure for the repair. What the
   cross-check protects (a second simulator catching behaviour only one shows, such as Icarus 12's stricter reading of SystemVerilog) is kept; only
   its place in the visit moves. When Icarus has no baseline for the design, its time limit is 6 x the Verilator baseline + 120 s (1800 s to 5400 s)
   instead of a fixed 1800 s (82P6 nine time-outs).
2. **A time-out has a diagnosing reason** (`tools.timeout_failure`): the simulate result carries the wall limit, the last simulation time in the log, the
   Verilator time of the same bench and the log tail (absolute paths stripped); the repair does not send the bench's owner the port-driving hint for it
   (`classify_sim` kind `timeout`).
3. **First fully clean evaluation is a clean stop.** The graph already ends with stop `done` at the first stage-2 evaluation whose gates all pass
   (`stop_after 2`); tests now pin this (no loop-back, no further visit, `clean_stop` true). Killed runs get a `summary.json`
   (`agent/graph/killed.py`, called by the driver after the kill): stop `budget`, cost so far, stage-2 visits, gate simulation seconds, last
   state.
4. **Routing persistence** (`run.mark_persisted`, evidence `const_id_seen`): a `CONST-ID-01` persists when the same wrong value was in **any** earlier
   stage-2 visit. Stop-reason assertion text (`repair.clean_assertion`) is the last failing line of the failing test, absolute paths reduced to the
   file name, no traceback.
5. **Vivado cap counter** (`flow/vivado_count.py`, `flow/hw.py`, `flow/run_vivado.sh`, `flow/checks/run_vivado_checks.sh`): counts processes whose argv[0] is the
   Vivado binary (`ps -ww`), tested with a fake waiting shell and a fake job.

## Design (as 82P6 except where stated)

- Task `v2_e_udp_endpoint` (L2); two arms, three runs each, **strictly one run at a time**, interleaved A r1, B r1, A r2, B r2, A r3, B r3. A = spec tests
  off; B = `--spec-tests`. Same command, model set (Sonnet `claude-sonnet-5-5` every role, Haiku oracle) and Claude Code CLI **2.1.321** (pinned real-file
  copy, SHA-256 in `environment.txt`, `DISABLE_AUTOUPDATER=1`, version checked before each launch).
- **Budget: 4 h hard wall limit per run** (owner, 2026-11-21: keep the 4 h; fix where the time goes). A run killed by it is a budget failure.
- Scoring as 82P6: hidden bench by `benchmark/tools/run_task.py` (Icarus) on the final `rtl/` (primary: 4 h rule) and on the last snapshot before 3 h
  (comparison with 82P3, 82P4). No LLM scores anything.
- Resources: heavy slot via `_handoff/take_heavy_slot.sh` with text starting "82P7:", peak 6G, `systemd-run --user --scope -p MemoryMax=8G`, `nice 10`,
  `FDA_VIVADO_MAX=1`; releases only a lock starting "82P7:". Launch waits for load under 6 and more than 12 GB available.
- **Usage stop rule (owner, 2026-11-21): no new launch at 97 % weekly usage (all models) or more** (`usage_check.sh` before each launch). A run in flight
  finishes. The week resets Monday 2026-11-23 01:00. Fable 0 %. Access-gate refusal: stop and report BLOCKED.
- An infrastructure failure (no model turn recorded) is "not run", evidenced, re-launched once, labelled. No change to agent, knowledge, prompts or
  benchmark during the six runs; bugs found are written down.

## Hypotheses (before the first run; n = 3 per arm decides little)

The null is stated first: **pooled pass rate no better than 1 of 6** (82P3 and 82P4 1/6, 82P6 0/6).

- **H1:** the Icarus cross-check takes under 10 % of pooled wall time (82P6: 29 %).
- **H2:** at most 2 of 6 runs are killed at 4 h (82P6: 4 of 6), and at least 2 of 6 end with a clean stop (stage 2 gates all pass; 82P6: 0 of 6).
- **H3:** pass rate (4 h rule) of at least 2 of 6 pooled, reported per arm and pooled with Wilson 95 % intervals next to 82P3, 82P4 and 82P6.
- **H4:** no synthesis gate call is refused by the Vivado cap while no real Vivado runs (82P6: 214 and 200 refused calls in two runs).

## Recorded per run

As 82P6 (arm, repeat, run id, hidden score at the end and at 3 h, stop reason with its diagnosis, wall, tokens, plan-cost estimate, stage-2 visits, own
gates, spec-test verdict, routing events, weekly usage before and after) plus `time_s` (gate Verilator, gate Icarus cross-check, Icarus calls and
time-outs, the roles' own simulation, synthesis gate calls), `clean_stop`, and `icarus_cross_check` routing events. Run archives and rendered prompts go to
the private knowledge repo (PR) with a public pointer; `leak_allow.txt` is not edited.

## Failure classes (fixed list, as 82P3 to 82P6)

spec reading, RTL, verification, closure (cannot occur at stop-after 2), tool, harness, budget; plus the events above, recorded as events.
