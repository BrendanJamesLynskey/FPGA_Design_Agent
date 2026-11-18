# b82p3: re-measure the UDP endpoint (L2) with the 82P2 fixes, one worker, spec_tests off vs on (pre-registration)

Written 2026-11-17 12:23 (Europe/London), on branch `b82p3-udp` (base main `c4cd5f05`), committed before the first run.
Development measurement, not a held-out evaluation. Nothing here reads, lists or copies a held-out task.

## Why

82P2's L2 result (0 of 3) measured our tooling (a busy Vivado slot, a refused placeholder file), not the agent. 82P2 fixed both
(write-time refusal of rtl files named like shell files; a build waits up to 45 min for a busy Vivado slot). There is no real L2
baseline yet. Owner, 2026-11-17: scorer kept frozen (`run_task.py` unchanged); re-measure with one worker.

## Design

- Task: `v2_e_udp_endpoint` (L2, development split) only. Hidden bench `benchmark/v2/tasks/v2_e_udp_endpoint/hidden` (10 tests).
- Two arms, three runs each, **strictly one run at a time** (one worker), interleaved: A r1, B r1, A r2, B r2, A r3, B r3.
  - **A**: `spec_tests` off (as 82P2).
  - **B**: `--spec-tests` on: an independent test bench the agent writes from the spec alone (role model Sonnet `claude-sonnet-5-5`,
    default 2 design_wrong round trips), which must also pass after V2. It targets the spec misreadings 82P2 found.
- Everything else identical in both arms: `python -m agent run <spec> --name v2_e_udp_endpoint --board nexys_a7_100t --interview oracle
  --hidden-spec <hidden/spec.yaml> --harness claude_code --cc-model claude-sonnet-5-5 --cc-effort medium --oracle claude_code
  --oracle-cc-model claude-haiku-5-5 --review off --stop-after 2 --verif-level V2 --docs off [--spec-tests]`. Profile `single`,
  Sonnet for every role, Haiku oracle answering from `hidden/spec.yaml` (never visible to the agent; the agent's tools are MCP tools only).
- Code: a detached worktree of main `c4cd5f05` (the armed access gate; includes the 82P2 fixes). The driver refuses to start a run if
  HEAD differs or `agent/`, `flow/`, `shell/` or `benchmark/` is dirty. Access key read from the code tree's git-ignored `.env` into
  the run's environment (never printed); the copy is deleted when the brief ends.
- Claude Code CLI **2.1.321**, a real-file copy first on PATH (SHA-256 in `environment.txt`), `DISABLE_AUTOUPDATER=1`; version checked
  before each launch (mismatch: PREFLIGHT_FAIL, no record, stop flag). Knowledge bank as checked out (`environment.txt`).
- Scope: stages 0 to 2 (`--stop-after 2`), V2, docs off, as 82P2, so closure is not measured. Stage 2 includes a **Vivado synthesis
  gate**, so each run takes a heavy slot through `_handoff/take_heavy_slot.sh` with a text starting "82P3:" (waits while none is free),
  and releases only a lock whose text starts "82P3:". Run under `systemd-run --user --scope -p MemoryMax=8G`, `nice 10` (the Vivado child is
  inside the scope; 82P2's 5G is raised to 8G only to leave room for the synthesis gate; same in both arms). Launch waits for load under 6
  and more than 12 GB available. Other sessions' Vivado jobs may share the PC; the 82P2 fix makes a build wait up to 45 min for a busy slot.
- Limits: the agent's own `RUN_LIMITS` unchanged; hard wall limit **3 h** per run (driver); a run killed by it is a failure of class "budget".
- Scoring: `benchmark/tools/run_task.py` unchanged (frozen), hidden tests only, Icarus, one score at a time under a light lock.
  No LLM scores anything; the agent's own and the spec-test bench never count.

## Primary metric

**PASS (per run) = every test of the hidden acceptance bench passes** on the run's `rtl/`. A run with no RTL, a build failure under the bench, a
partial pass, or a hard-limit kill is a failure. **pass@1 per arm = k/3**, with a Wilson 95% interval; n = 3 per arm decides little and the
report says so. No test of arm difference is claimed. Secondary (reported beside, never replacing): hidden tests passed of total; the agent's
own stage-2 gates clean; escapes (gates clean, hidden fail); in arm B whether the spec-test bench fired, passed, and caught a bug; plan-equivalent
cost (Claude Code's own reported usage per run, summed from `summary.json`; not a bill); wall time, turns, stage-2 visits.

## Stop rule and budget

- No new launch if weekly usage (all models) is 88% or more (`usage_check.sh` before each launch; the driver stops itself); a run in flight finishes.
  Fable 0%. A refusal by the access gate: stop and report BLOCKED.
- Budget per run: 3 h wall (hard), plus the agent's own cost caps. Total at most 6 runs; none dropped, none repeated for a better result.
- An **infrastructure failure** (no model turn recorded: CLI version block, OOM kill of the scope before the first turn) is reported "not run" with
  evidence and re-launched once, labelled. A run that reached a model turn and then fails is a failure, whatever the reason.
- No changes to agent, knowledge, prompts or benchmark during the 6 runs. Bugs found are written down. Retrospective fixes (cheap tooling ones) come
  after all 6 runs, each with a ledger line and a post-hoc re-score kept apart from these numbers.

## Failure classes (fixed list)

spec reading, RTL, verification (the agent's tests or gates), closure (cannot occur at stop-after 2), tool, harness, budget. Assigned after reading
the run's logs and the failing hidden test; the report quotes the evidence.
