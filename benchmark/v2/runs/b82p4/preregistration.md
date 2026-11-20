# b82p4: re-run the 82P3 task set with the derived-constants exit gate and the unresolved-verdict rule (pre-registration)

Written 2026-11-19, on branch `b82p4-exit-constants`, committed before the first run. Development measurement, not a held-out
evaluation. Nothing here reads, lists or copies a held-out task.

## Why

82P3 (UDP endpoint, L2): 1 of 6 runs passed every hidden test; 4 of the 5 failures bound the shell DESIGN_ID to the endpoint ID word
0x55445031 where the spec's design ID "UEP1" is 0x55455031. Owner decisions 10 to 12 (2026-11-19): an unresolved spec-test verdict
is not a clean stop; wire the derived-constants check (HDL-ORC-01) into the stage exit gate instead of a constants checklist; keep the
L2 budget at 3 h and re-run with decision 11 first. Changes under test (this branch): stage 2 and stage 3 exit require the
`constants` gate (a blocking finding fails the stage and sends the RTL role the finding, with no Vivado time spent on that visit);
a run that ends with the spec-test verdict `unresolved` stops with `unresolved: ...`, not `done`.

## Design (identical to b82p3 except the code under test)

- Task: `v2_e_udp_endpoint` (L2, development split) only; hidden bench `benchmark/v2/tasks/v2_e_udp_endpoint/hidden` (10 tests).
- Two arms, three runs each, **strictly one run at a time**, interleaved A r1, B r1, A r2, B r2, A r3, B r3. **A** = `spec_tests` off;
  **B** = `--spec-tests` on. Seeds policy: the model calls take no seed (Claude Code headless has none, 82P3 used the same); a repeat is
  a fresh run of the same command; no run is dropped or repeated for a better result.
- Command (same flags as 82P3, which are aliases into the 108 model table; the resolved table and its hash are in each run's
  `config.json` and `summary.json`): `python -m agent run <spec> --name v2_e_udp_endpoint --board nexys_a7_100t --interview oracle
  --hidden-spec <hidden/spec.yaml> --harness claude_code --cc-model claude-sonnet-5-5 --cc-effort medium --oracle claude_code
  --oracle-cc-model claude-haiku-5-5 --review off --stop-after 2 --verif-level V2 --docs off [--spec-tests]`. Sonnet
  `claude-sonnet-5-5` for every role through `claude_code` (Max plan), Haiku oracle. Never Fable or Opus.
- Code: a detached worktree of this branch at the commit named in `environment.txt` (the driver refuses to start if HEAD differs or
  `agent/`, `flow/`, `shell/`, `benchmark/` is dirty). Claude Code CLI **2.1.321**, the 82P3 pinned real-file copy first on PATH
  (SHA-256 in `environment.txt`), `DISABLE_AUTOUPDATER=1`, version checked before each launch (mismatch: PREFLIGHT_FAIL, no record).
- Resources: each run takes a heavy slot through `_handoff/take_heavy_slot.sh` with text starting "82P4:" (stage 2 has a Vivado
  synthesis gate), under `systemd-run --user --scope -p MemoryMax=8G`, `nice 10`, `FDA_VIVADO_MAX=1`; releases only a lock starting
  "82P4:". Launch waits for load under 6 and more than 12 GB available. Hard wall limit **3 h** per run (as 82P3); a run killed by it is a
  failure of class "budget".
- Scoring: `benchmark/tools/run_task.py` unchanged, hidden tests only, Icarus, one score at a time under a light lock; the driver's
  `passed()` is 82P3's (all tests pass, tests > 0, not killed by the hard limit). No LLM scores anything. Cost is Claude Code's own
  plan-equivalent estimate, not a bill.

## Comparison (the only one claimed)

The generated `results.md` puts each 82P4 run beside its 82P3 counterpart (same arm and repeat): hidden tests passed, stop reason,
pass@1 per arm with Wilson 95% intervals. **n = 3 per arm decides little**; no arm difference or improvement rate is claimed, and
the null (no run passes, or no better than 82P3) is stated first if it occurs. Secondary, reported beside: own stage-2 gates clean,
clean stops, escapes, runs the constants gate blocked (and whether the next visit fixed the ID), the spec-test verdict, wall time,
tokens, cost. A run that stops `unresolved` is counted as unresolved, never as a clean stop or an escape.

## Stop rule and budget

- No new launch at 88% weekly usage (all models) or more (`usage_check.sh` before each launch; the driver stops itself); a run in flight
  finishes. Fable 0%. Access-gate refusal: stop and report BLOCKED. Total at most 6 runs.
- An infrastructure failure (no model turn recorded) is "not run", evidenced, re-launched once, labelled.
- No changes to agent, knowledge, prompts or benchmark during the 6 runs. Bugs found are written down.
- L2 budget stays 3 h (decision 12); if runs still time out, the report says so and the planner decides whether to raise it.

## Failure classes (fixed list, as 82P3)

spec reading, RTL, verification, closure (cannot occur at stop-after 2), tool, harness, budget; plus, new, **constants gate** (the
run was blocked by it) recorded as an event, not a failure class.
