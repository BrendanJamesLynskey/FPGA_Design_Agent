# Brief 217: evidence-keyed repair memory, and the check suite over MCP

Status: built and replayed; the live A/B is not run because the replay's ceiling on the primary outcome is below its smallest detectable effect ([prereg.md](prereg.md) states the rule).
Item 0 fixed the R1 first-failing-check digest, which had said only "Simulator shut down prematurely" in brief 213's run 3. The repair memory (harness arm `R4`) writes a record when a repair
visit turns a failing gate into a pass and, on a later repair visit, hands the repairing role at most three records whose trigger equals the failure's evidence on gate, finding id and signature class.
The check suite is also served read-only over MCP. The report is `_handoff/fpga_agent/reports/217_repair_memory_report.md`.

## Records
- [prereg.md](prereg.md): the arm, the replay, the decision rule and the power line, written before any agent run of this brief.
- [item0_run3_digest.txt](item0_run3_digest.txt): the R1 digest rebuilt on brief 213's run 3 (the cause found: a clock started inside the first test only).
- [replay_evals.jsonl](replay_evals.jsonl): one line per stage-2 evaluation of 107 recorded runs (evidence keys, unkeyed components, the diff of the visit before it).
- [replay_analysis_run.txt](replay_analysis_run.txt) and [replay_analysis_design.txt](replay_analysis_design.txt): reach, recurring share and ceiling under leave-one-run-out and leave-one-design-out.
- [run_live.sh](run_live.sh): the driver for one demonstration run of the arm (not scored). It was **not run**: the heavy-slot queue was still closed to it after 50 minutes (2026-11-26 21:28 to 22:18 GMT), so the arm's end-to-end path is covered by the offline tests, including one through the real `node_gate` (`agent/tests/test_217_repair_memory.py`).
- Code: `agent/graph/repair_memory.py`, `tools/repair_memory/` (replay, seed), `agent/mcp_server/checks.py`, `flow/model_record.py` and `flow/divergence.py` (item 0). Tests: `agent/tests/test_217_*.py`.
- Knowledge bank: `repairs/` in the private repository (95 seeded records; its own pull request).

## Reproduce
`python tools/repair_memory/replay.py extract --out results/217_repair_memory/replay_evals.jsonl` (needs the recorded runs' `snap.git` under `~/Claude_sandbox/_worktrees/{213-repair-feedback,209-kr260-pilot,209a-pilot-ready,224-long-output,215-public-benchmarks}/runs`,
the OSS Verilator, and the access key in `.env`), then `python tools/repair_memory/replay.py analyse results/217_repair_memory/replay_evals.jsonl [--holdout design]`. Seeds for the knowledge bank:
`python tools/repair_memory/seed.py results/217_repair_memory/replay_evals.jsonl --out <bank>/repairs/records`. Live arm: `run_live.sh <design>` (pinned Claude Code, a heavy slot).

## Known gaps and limits
- The replay keys lint, standards, constants, report-gate and verification failures; a failed simulate is unkeyed (the snapshot holds no simulator output) and is counted, not matched. Lint was re-run on the snapshot; 54 lint evaluations could not be re-run (mostly the 215 benchmark designs).
- The ceiling is an upper bound: every matched recurring evaluation is counted as a saved visit. Where the files a matching record changed can be compared with the files the run's next repair changed, they overlap in about half the cases.
- A record's diff is the whole visit's change: when a visit cleared several keys, the diff is not attributed to one of them.
- The seeded records are `reviewed: false`. No effect of the arm on a live run is measured, and the arm has not run in a live agent run (the demonstration run was not made, see Records).
