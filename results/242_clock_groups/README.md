# 242: clock groups written by the flow from the declared clock relations


Code: [flow/known_constraints.py](../../flow/known_constraints.py) (`clock_relations`, `clock_group_plan`), docs: [docs/constraints_complete.md](../../docs/constraints_complete.md) (last section), tests `agent/tests/test_242_clock_groups.py`. Vivado 2026.1, xck26.

| File | What |
|---|---|
| `preregistration.md` | written before any agent run |
| `replay_p5/`, `replay_p5_start/` | 230's two p5 states (where run 1 stopped; the start of a constraints visit) plus an `architecture.yaml` written by hand for the replay (it states the domains, crossings and clock relations the interview and architect would give); `records/` of the final flow built to post-route |
| `records_v1_group_only*`, `records_v2_bound_all_pairs*` | the two earlier versions of the rule on the same states, kept: what each got wrong (below) |
| `false_positive_scan.py/.json` | the plan over the 33 committed designs, as committed and as a stress reading |
| `run_cell.sh`, `chain.sh`, `../../pilots/242/` | the agent-run scripts and each run's record (`run_record.json`, its design.xdc, architecture.yaml, flow-written known_post.xdc, gates.json, summary.json) |
| `replay_r2/`, `replay_r3/` | the designs of agent runs p5 r2 and r3 (copied), rebuilt to post-synthesis with the final rule |


## Records

### Replay of 224's p5 (the replay states of 230), Vivado 2026.1, xck26: four versions of the rule

| version | what the flow wrote for the pair of the FIFO | gates still failing |
|---|---|---|
| none (230's replay) | nothing | `post_synth_methodology_no_critical` (TIMING-6/7) |
| v1: `set_clock_groups -asynchronous` for every async pair (`records_v1_group_only*`) | 6 groups | methodology passes; **`post_synth_exceptions_clean`** (the groups override the XPM FIFO's and handshake's own `set_max_delay -datapath_only`: EXC-IGNORED, TIMING-24 x6), **`post_synth_cdc_structure_clean`** (U5), post-route `exceptions_clean` |
| v2: pairs that cross XPM gray / handshake / FIFO macros get a `set_max_delay -datapath_only` in both directions instead of a group (`records_v2_bound_all_pairs*`) | 1 bound pair, 5 groups | `exceptions_clean`: the reverse direction is entirely overridden by the macros' own rows, and groups on pairs that cross nothing are "Non-existent path" |
| v3: bound only the directions with a FIFO or hand-built crossing (`records_v3_bound_forward*`) | forward bound only | none on the replay; **but on two agent designs (p5 r2, r3) the forward bound was itself "Totally overridden" by the macros' rows** (their FIFO, handshake and single macros cover the whole direction): what a file reader cannot tell |
| v4 (final): both directions bounded, no group on a pair declared `no_crossings`, and `flow/exceptions_check.py` reports the flow's own clock-pair bound, when totally overridden by `FP`/`DPO` rows only, as information (`EXC-IGNORED-FLOW-PAIR-BOUND`, never when overridden by a clock group, never for a design's own line) | 2 bounds + 2 groups | **none** (replay_p5 through post-route; replay_p5_start, replay_r2, replay_r3 through post-synthesis); r2 and r3 keep `post_synth_resources_in_range`, the model's own predicted-resources range (it failed in the agent runs too) |

Final, p5 replay to post-route: WNS 3.03 ns, WHS 0.01 ns, 0 failing endpoints; the only red gate is `bitstream_present` (the replay stops at `route`). The rule was derived on this design, so the replay is not an independent test; r2 and r3 (two more models' designs of the same request, rebuilt to post-synthesis) are the confirmation, with the same design family.
What was learned (kept in `docs/constraints_complete.md`): a clock group on a pair crossed by XPM bus macros removes their bounds and fails the exceptions and structural CDC gates; a clock-pair bound over a direction the macros cover is "ignored" by Vivado, which is harmless, and is information in the check.

### Agent runs (Claude Code, plan-billed, stages 0 to 4; `preregistration.md` and three addenda)

| design, run | run id | rule in force | stage reached (stage-3 visits) | stop | flow wrote | model wrote | plan-cost estimate (usd) |
|---|---|---|---|---|---|---|---|
| p5 r1 | 20261127-062134-97a8 | explicit field only (flow wrote nothing) | 4 (3) | done, every gate passed | nothing | 1 clock group | 5.01 |
| p5 r2 | 20261127-071840-b6fa | v3-in-progress (bound in both directions) | 3 or later, killed at the 3300 s wrapper limit | no summary.json | 2 `set_max_delay -datapath_only` | 1 clock group | not recorded |
| p5 r3 | 20261127-081353-d5bb | v3-in-progress | 3 (5) | stage 3 visit limit: `post_synth_exceptions_clean`, **caused by the flow's own bound being ignored** | 1 `set_max_delay -datapath_only` | none | 4.88 |
| p6 r1 | 20261127-071840-a9f0 | n/a (never reached constraints) | 2 (0) | stage 2 visit limit: STD-ARCH-00 KeyError (a checker bug, fixed in this PR) | nothing | nothing | 4.18 |
| p6 r2 | 20261127-074741-be45 | n/a | 2 (0) | stage 2 visit limit: STD-CLK-01 (BUFGCE_DIV gates a clock) | nothing | 1 clock group | 6.17 |
| p6 r3 | 20261127-083052-c28f | n/a | 2 (0) | stage 2 visit limit: design standards | nothing | nothing | 4.82 |

Nulls first: **the pre-registered primary (methodology gate passed in the last gate call) was met by 1 of 3 p5 runs and by none of the p6 runs; the prediction (at least 2 of 3 p5, flow line written in at least one) failed.** No model ever wrote `clock_relations` (no prompt tells it the field exists and the interview was off), so the flow's contribution was the derived relation from the declared crossings;
in p5 r2 and r3 that contribution **failed the exceptions gate until the rule was corrected** (v4), which is the measurable harm and the lesson of this brief. The corrected rule was replayed on those two designs (post-synthesis: exceptions clean), not re-run as agent runs: the usage and wall budget stopped further runs. p6 stops in stage 2 on gates unrelated to clock groups (p6's clock mux is never declared in `clock_muxes`, and the flow never reached the constraints stage), so it does not exercise the feature.
n = 3 per design, one model, one harness: illustrative. Plan-cost estimates are not provider-reported. Weekly usage went from 84% to 86% over the six runs.

### False-positive scan (`false_positive_scan.json`)

The plan over the 33 committed designs with a build.yaml: **0 change as committed** (none declares `clock_relations` or `clock_muxes`, and a derived pair is used only where both clocks can be named: the GT designs' `TXUSRCLK2`/`RXUSRCLK2` cannot, so those are skipped). Under the stress reading (every declared crossing pair treated as async) no refusal for an unsynchronised crossing fires on any committed design; the only refusals are "cannot name the clock" on the GT designs (`designs/b56a_gth_serdes`, `designs/b96_kr260_10g` and its variants), which the `clock_object:` field of a domain answers.

## Reproduce

- Unit tests: `python -m pytest agent/tests/test_242_clock_groups.py`. Scan: `python3 results/242_clock_groups/false_positive_scan.py <out.json>`.
- Replay: `FDA_STOP_AFTER=route flow/run_vivado.sh results/242_clock_groups/replay_p5/p5_async_fifo base` under a heavy slot (`_handoff/take_heavy_slot.sh`), then read `build/base/gates.json`.
- Agent runs: `results/242_clock_groups/run_cell.sh <p5_async_fifo|p6_glitchfree_mux> <k>` (needs the pinned CLI in `_scratch_227/bin`, the prompts checkout `FDA_PROMPTS_DIR`, the worktree's `.env`), then `python3 pilots/242/record_one.py <design> <k>`.

## Known gaps and limits

- The model never writes `clock_relations`: the architect prompt (private knowledge bank) does not mention it. Follow-up: a knowledge-bank prompt line, or the interview on, so the field is stated rather than derived.
- The derived relation reads declarations and instances, not the netlist; a crossing not declared in `architecture.yaml` is not seen by it (STD-CDC-01 and the post-route structural check see it).
- `EXC-IGNORED-FLOW-PAIR-BOUND` identifies the flow's line by its position in `known_post.xdc` and its text; a design that edits that file by hand is not covered (the file is regenerated each build).
- The agent runs p5 r2 and r3 ran under an intermediate rule (the code changed while they ran, stated in the preregistration addenda); only the replays measure the final rule.
- Not covered: generated clocks (an MMCM's outputs are `related` and get no group; fabric-generated clocks cannot be named), exclusive clocks (`clock_muxes`, no design here declares one, so only the unit tests cover it).
