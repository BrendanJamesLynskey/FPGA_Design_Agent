# Navigator stage map: results (brief 238)

Recorded 2026-11-26 on the build PC with the navigator code of this branch (`238-nav-anim`). What it is: the Live page of the navigator now draws a map of the agent's stages and moves it from the
run's own files (where the run is, the visit against its limit, the role that last reported, gate results, a route back, a wait), with a Replay of a finished run. Design note and routes:
[navigator/README.md](../../navigator/README.md), "Stage map". No agent was run and no Vivado: the runs shown are the recorded 213 run folders and one synthetic run written by `navigator/tests/demo_238.py`.

## Records

- `replay_10_p2_bram_rom_k3_control.webm`: a screen recording (about 1.2 MB) of Replay at 2x on 213 run `10_p2_bram_rom_k3_control`, which passes and routed back once (stage 2 to stage 1).
- `screenshots/working_<theme>_<width>.png`: a synthetic run in the trace mode, working at stage 2 with a Vivado build step open (spinner), a lint gate failure and an earlier route back; `visit_limit_*`: 213 run `2_p1_clkmeter_k3_treatment`, six
  failing `lint` visits of stage 2, stopped on its limit; `route_back_*`: run 10 at its end; `runs_<theme>_390.png` and `working_<theme>_390.png`: the whole Live page at 390 px with the new phone layout of tables (each row a card, every field kept) and the Navigator header with the FPGA Force mark; `reduced_motion_1280.png`: the same page with `prefers-reduced-motion`. Themes dark and light, widths 1280 and 390 px (the list layout).
- `shoot_report.json`: the headless checks: zero page errors, no request to another host, no horizontal overflow at 390 px; the replay showed a travelling token 8 times in 250 ms samples; with reduced motion no token and no node animation;
  the replay of the visit-limit run ended on its stop reason; the working run showed one spinner.
- Test fixtures: `navigator/tests/fixtures_238/` holds three 213 run folders cut down to the files the map reads (`config.json`, `role_usage.jsonl`, `routing_events.jsonl` and a few fields of `summary.json`).

## Reproduce

`FDA_PROMPTS_DIR=<pinned prompts> python -m pytest navigator/tests` (the stage-map tests are `navigator/tests/test_238_stagemap.py`). For the screenshots and the recording:
`python3 -m navigator.tests.demo_238 --port 8794 --workdir <tmp>`, then `NODE_PATH=<node_modules> node navigator/shoot_238.js <url with token> <dir>`. Add `--append` to the demo and `live-only` to the script to watch a live stage change (a token was seen to travel).

## Known gaps and limits

- The 213 run folders have no `trace.jsonl` or audit log, so their map uses the `role_usage` mode: the order of the visits, failing gates from the ledger rows, and whether a stage passed read from where the run went next. They carry no times, so Replay
  uses an even pace, not the real one. Run 10 records no failing gate, so its route back is labelled "failing gate not recorded: back to stage 1"; a gate flash was not seen in the recording for that reason (run 2's replay has them).
- The trace mode (live runs from brief 182 on) was exercised on a synthetic run and by unit tests, not on a real run in this brief. The slot-wait, permission and pause states are covered by unit tests, not by a screenshot.
- States the files cannot tell apart: an idle run that crashed, finished badly or is in one long silent step; a reviewer's retry and a gate failure (role_usage mode); a design-request route back and a gate route back (role_usage mode); the role mid-call (only the last role to report is known).
- The website's "A recorded run, replayed" section was not changed: its drawing is Python-generated static markup and the map is a browser script reading a live API, so sharing the code cleanly needs a separate piece of work (follow-up).
