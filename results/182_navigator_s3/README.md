# Navigator stage 3: results (brief 182)

Recorded 2026-11-23 on the build PC, with the navigator code of this branch (`b182-navigator-s3`). Design note and every route: [navigator/README.md](../../navigator/README.md), "Stage 3".

## What was recorded

Two real agent runs on one **development** course task (`benchmark/course/tasks/c9_median3x3`, a dev task in `benchmark/course/split_c9_c12.yaml`; no hidden spec, so the run is not scored),
Claude Code on the subscription, model `claude-sonnet-5-5` for every role, harness arm H1, `--review off`, no Vivado at all (the runs stop before synthesis). In each run, while the agent was working,
one **design request** was queued with `python -m agent request` and one **question** was asked with `python -m agent ask`.

| | demo_short (run 20261123-021425-d176) | demo_long (run 20261123-012726-9d71) |
|---|---|---|
| command | `agent run ... --stop-after 1` | `agent run ... --stop-after 2` |
| design request r001 (queued) | 02:15:01, "prefer a sorting network of compare-exchange cells over a rank-counting comparator array" | 01:28:13, the same text |
| applied | 02:15:05 at the end of stage 0 visit 1 (its gate failed, so the note went to the repeat of stage 0) | 01:28:32 at the end of stage 0 (passed): given to stage 1 (board-and-device-planning) |
| the agent's acknowledgement | `requests.jsonl`: `queued` then `done`, "given to stage 0 (clarify) as the owner's note"; `build/who_did_what.json`: owner row "mid-run request r001" | the same, "given to stage 1 ..." |
| the question | "What has the agent done so far, and is anything waiting on me?" answered from records R1-R6, cited R1 R2 R3 R4 R6; plan estimate $0.0090 | answered, cited R1 to R6; plan estimate $0.0119 |
| how the run ended | `stop: done`, stages visited 0, 0, 1, 1; wall 93.6 s of model time; plan estimate $0.38 | **stopped by me** (SIGTERM to its own process) in stage 2, third visit, while the Icarus simulation of the agent's own bench had run 15 minutes; no summary.json |

Files: `demo_*/requests.jsonl` (every event of each request), `qa.jsonl` (question, answer, records read and cited, model, plan-estimate cost), `who_did_what.json` (the user interventions beside the agent's own rows),
`trace_events.jsonl` (the `kind: "event"` rows of the run's trace: stage start and end, console pointers, request outcomes; no model or tool rows), `summary_extract.json` (stop reason, stages, the `user_requests` counts),
`status_final.txt` (`python -m agent status`), `console_steps.txt` (`python -m agent status --console`: the step list only), `request_cli.txt` and `ask_cli.txt` (the commands' output).

What the records show, and what they do not:
- The request waited for a safe point (4 s in the short run, 19 s in the long one), was acknowledged, applied and recorded with its reason. In the short run the model's own output (console step `002_clarify_clarify`)
  says it rewrote `spec.yaml` "to follow the owner's preference for a sorting network". That is one observation that the note reached the writer and was read; it is **not** evidence the request changed the design, because a median-of-nine
  design may well use a sorting network without being asked. The prompt delivery is proved by `agent/tests/test_182_requests.py` (the stage-1 Designer's prompt carries the note).
- The status sentence, the console and the question all worked on a live run. Costs are the plan's estimates (Claude Code on the subscription); the provider reports no dollar figure for these calls.
- A third run (Haiku, `20261123-012325-41eb`, not kept) ended at "stage 1 visited more than 4 times": a model-capability result about the task, not about the navigator; its request had been applied at the stage 0 boundary.
- **The tool console of the Claude Code arm was not observed live in these runs.** The agent's tools run in the arm's MCP server process, and the code that points that process at the run's `console/` directory
  (`FDA_RUN_DIR`) was added after demo_long started and after demo_short's tools had run (stages 0 and 1 use only file tools). It is covered by `agent/tests/test_182_console.py` (a tool run in the server leaves `console/<n>_<kind>.log` and a trace pointer). Container runs (the simulator)
  are streamed through the local runner they use; the one container run that was live in demo_long ran before that change and wrote its log at the end.
- Console files hold the model's streamed output and are **not committed** (they can quote the private prompts); only the step list is.

## Tests

`python -m pytest navigator/tests agent/tests/test_182_requests.py agent/tests/test_182_console.py`: see `full_tests.log` for the full agent and navigator suite at the last commit (`pytest -q`, `--ignore-glob='*_rtl.py'`).

## Screenshots

`screenshots/` holds the Live page of the short run at 1280 and 390 px, with the console drawer shut and open, and `shoot_report.json`: page errors, requests to any host but the navigator's own, horizontal overflow at 390 px, and
whether the shut drawer made any console request. Read them in the report's verification section.
