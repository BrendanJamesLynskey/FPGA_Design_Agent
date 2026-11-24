# b82p6: the 4 h measured re-run of the UDP endpoint task, with the three repair-routing changes (pre-registration)

Written 2026-11-20 on branch `b82p6-routing-4h`, committed before the first run. Development measurement, not a held-out evaluation.
Nothing here reads, lists or copies a held-out task. Owner decisions 19 and 20 (`owner_decisions_2026-11-19.md`).

## Why

82P3 and 82P4 (UDP endpoint, L2, 3 h limit) both ended 1 of 6. 82P5 found why the B arm's stage-2 simulation did not converge in 82P4
(a bench that built packets with a one-byte register number while model and RTL kept the spec's two bytes) and that the repair loop never
handed the bench's owner the evidence, and that a wrong design-ID word copied into spec.yaml, the model and the bench cannot be fixed by
the RTL role alone. This brief builds the three changes the owner approved (P1, P3, the clarify-exit constants check with owner routing;
not P2) and measures the agent with them on the same task, with the budget raised to 4 h (decision 19).

## Changes under test (frozen code commit `55cb0fa7`; this branch, one commit on top of origin/main `ddc62aa5`)

1. **P1** (`agent/graph/repair.py: stage2_owners`): while the stage-2 simulation fails, the V2 consequence checks (`failing_tests`,
   `planned_tests_missing`, `constrained_random_test_ran`, `assertions_bound_zero_failures`) count as covered by that failure and do not make
   the bench's owner (the Verifier, role `tests`) an owner; and from the first repeat of a failure signature the Verifier always gets the existing
   repeat hint ("the same failure survived a repair of the RTL ... check that the bench drives the ports as the spec says") with the failing
   assertion text, whatever else it already owns. No prompt text changed (the existing hint is reused).
2. **P3** (`repair.stop_diagnosis`, `run.node_work`, `run.summary`): a stage that runs out of visits stops with a diagnosing reason that keeps
   the prefix `stage N visited more than L times` and adds the last failing gate(s), the owning role(s), the last failing assertion and the
   number of consecutive visits with the same failure signature; `summary.json` carries the structure as `stop_detail` and the RTL role's last
   final message (first 300 and last 1700 characters when longer than 2000) as `last_rtl_message`.
3. **Clarify-exit constants check** (`flow/derived_constants.py: spec_yaml_findings`, `run.node_gate` stage 0): at the clarify exit spec.yaml's
   `parameters.DESIGN_ID` is compared with the design ID derived from the spec's quoted string (`CONST-ID-03`, blocking) and a `clocks` entry on
   the board's oscillator port with the board file's period (`CONST-CLK-02`, blocking); a finding fails the clarify exit (the `spec_signed` gate)
   with the message. **Owner routing**: a `CONST-ID-01` that is still there at the next stage-2 visit (`persisted`) is routed to the owner of each artefact
   that holds the wrong value as a design ID (heuristic: a line that writes the value and names a design ID): the Modeller and the Verifier get a
   text naming only their own file (the Modeller never sees the RTL), the RTL role keeps the finding, and a wrong value held by spec.yaml sends the
   run back to the clarify stage (stage 0).

Tests: `agent/tests/test_82p6_repair_routing.py` (planted cases; replay of the recorded 82P4 B r2 / B r3 stage-2 failures from
`agent/tests/fixtures/b82p6_replay_evidence.json`); replays on the private archives in `posthoc/replay_*.txt` (the 82P5 planted run's spec.yaml
fails the clarify exit; stop reasons on the recorded visit-limit stops). The scorer, the pass rule, the task and the held-out material are unchanged.

## What else differs from the 82P4 runs (code and environment)

82P4 ran frozen code `61f4ec98` (origin/main `283c2cfc` plus the 82P4 branch). Since then origin/main gained, in this order: `0ff92242` 107
(deterministic mode: model-call tape, `--deterministic`; default off, touches `agent/models/resolver.py` and `agent/graph/run.py`), `8ae9c9e7`
96F, `757303eb`/`253d73c6`/`36614d4a`/`835c36d0` (96D/96E/96F board and eye-scan work, `flow/eyescan`, not the agent graph), `031dd994` the
82P4 merge, `ddc62aa5` 82P5 (records only). The knowledge-bank checkout is origin/main at the time of freezing (`environment.txt`); its prompts manifest hash is
the pin's (the run refuses otherwise). So the code differs from 82P4 by the three changes **and** by 107's default-off wiring; any effect is not
attributable to the three changes alone.

## Design

- Task: `v2_e_udp_endpoint` (L2, development split) only; hidden bench `benchmark/v2/tasks/v2_e_udp_endpoint/hidden` (10 tests).
- Two arms, three runs each, **strictly one run at a time**, interleaved A r1, B r1, A r2, B r2, A r3, B r3. **A** = `spec_tests` off;
  **B** = `--spec-tests` on. Same seeds policy as 82P3/82P4 (no seed for model calls; a repeat is a fresh run; no run is dropped or repeated for a
  better result).
- Command (same flags as 82P3/82P4): `python -m agent run <spec> --name v2_e_udp_endpoint --board nexys_a7_100t --interview oracle --hidden-spec
  <hidden/spec.yaml> --harness claude_code --cc-model claude-sonnet-5-5 --cc-effort medium --oracle claude_code --oracle-cc-model claude-haiku-5-5
  --review off --stop-after 2 --verif-level V2 --docs off [--spec-tests]`. Sonnet `claude-sonnet-5-5` for every role through `claude_code` (Max plan,
  the 108 model table; resolved table and hash are in each run's `config.json`), Haiku oracle. Never Fable or Opus.
- Code: a detached worktree (`_worktrees/82p6-frozen`) at the frozen commit; the driver refuses to start if HEAD differs or `agent/`, `flow/`,
  `shell/`, `benchmark/` is dirty. Claude Code CLI **2.1.321**, the pinned real-file copy first on PATH (SHA-256 in `environment.txt`),
  `DISABLE_AUTOUPDATER=1` (checked before the first run), version checked before each launch (mismatch: PREFLIGHT_FAIL, no record, stop).
  Other tools pinned as in 82P4 (Icarus 12.0 for the hidden bench, Vivado 2025.2 for the stage-2 synthesis gate, the same venv); no apt, pip or Docker pull during the runs.
- Resources: each run takes a heavy slot through `_handoff/take_heavy_slot.sh` with text starting "82P6:" (stage 2 has a Vivado synthesis gate, not
  implementation), peak 6G, under `systemd-run --user --scope -p MemoryMax=8G`, `nice 10`, `FDA_VIVADO_MAX=1`; releases only a lock starting "82P6:".
  Launch waits for load under 6 and more than 12 GB available. Scoring has its own light lock and one score at a time.
- **Budget: 4 h hard wall limit per run** (owner decision 19; 82P3 and 82P4 used 3 h). A run killed by it is a failure of class "budget".
- Scoring: `benchmark/tools/run_task.py` unchanged, hidden tests only, Icarus. No LLM scores anything. Cost is Claude Code's own plan-equivalent
  estimate, not a bill.

## Two scorings of every run (fixed in advance)

1. **Primary (4 h rule):** pass = every hidden test passes on the final `rtl/` and the run was not killed by the 4 h limit (82P3/82P4's `passed()`
   with the new limit).
2. **Comparison with 82P3/82P4 (3 h mark):** every run is **also scored on its last snapshot before 3 h** (run start + 3 h: the newest `snap.git`
   commit at or before the mark, its `rtl/` scored by the same bench; a run that ended on its own before 3 h is scored as it ended). The
   **3 h rule** pass is the old rule exactly: the run ended on its own within 3 h with every hidden test passing (the old runs were killed at 3 h).
   The 3 h snapshot score (n of 10) is reported beside it.

## Hypotheses (stated before the runs; no claim is expected to be proven at n = 3 per arm)

- **H1:** fewer stage-2 visit-limit stops than 82P4's 5 of 6 (counted over all six runs, and 3 h rule vs 4 h rule).
- **H2:** more B-arm runs reach the spec-test bench (82P4: B r1 only, 1 of 3).
- **H3:** pass rate no worse than 1 of 6 (82P3 and 82P4); reported as pass@1 per arm and pooled with Wilson 95% intervals, next to 82P3 and 82P4.
  The null (no better than 1 of 6) is stated first if it occurs. n = 3 per arm decides little; no arm difference or improvement is claimed.

## Recorded per run

Arm, repeat, run id, hidden score at the end and at the 3 h mark, stop reason (the diagnosing one, `stop_detail`) and the RTL role's last
message (private archive only), wall minutes, tokens, plan-cost estimate, stage-2 visits, own stage-2 gates, spec-test verdict, and whether each change
fired from `routing_events.jsonl` in the run directory: P1 consequence checks covered, P1 hint sent, clarify-exit check result (a line per
evaluation), owner-routing events (`const_id_routed_to_holder`, `const_id_routed_to_spec_yaml_owner`); weekly usage before and after each
run (`usage_check.sh`). Rendered prompts and run archives go to the private KB `results_private/` with a public pointer (as 82P4/82P5); `leak_allow.txt` is not edited.

## Stop rule and budget

- No new launch at 88% weekly usage (all models) or more (`usage_check.sh` before each launch; the driver stops itself); a run in flight
  finishes. Fable 0%. Access-gate refusal: stop and report BLOCKED. Total at most 6 runs.
- An infrastructure failure (no model turn recorded) is "not run", evidenced, re-launched once, labelled.
- No changes to agent, knowledge, prompts or benchmark during the 6 runs. Bugs found are written down.

## Failure classes (fixed list, as 82P3/82P4)

spec reading, RTL, verification, closure (cannot occur at stop-after 2), tool, harness, budget; plus the events above, recorded as events, not failure classes.
