# 209: KR260 pilot (agent-generated designs, tested on hardware)

Question: can the agent take a short written spec to a design that passes on the owner's KR260 first time, with no human or Claude hand-fixes?

## Headline

- **Hardware result: pending board visit.** No design has been on the board. The count "N of 6 passed on hardware first time" is filled in by the planner after the owner's run.
- **Reached a bitstream (all gates up to the programming approval): 7 of 18 runs.** p1 2 of 3, p2 3 of 3, p3 2 of 3, p4 0 of 3, p5 0 of 3, p6 0 of 3. **Run 1 (the "first time" run) reached a bitstream for p1, p2 and not for p3 (stopped at a lint gate) or p4 to p6.**
- **Designs ready for the board with no intervention: 3 of 6** (p1_clkmeter run 1, p2_bram_rom run 1, p3_crc_engine run 2; p3 run 2 is a second-run result, so by the "first time = run 1" rule only p1 and p2 are first-time ready).
- All 9 runs of p4, p5 and p6 failed the same way: the Designer's reply was cut off at the 16,000-token limit (6 or 7 times per run, about 130 s each), the cut-off tool call was dropped, `rtl/` was never written, and the run stopped with "stage 2 visited more than 6 times". This is a limit in the agent's settings (output length), recorded as a result and not setup noise. The fix is brief 224 (streaming, a larger max_tokens, file-by-file RTL). **A labelled second arm will re-run p4, p5 and p6 after it, and its results are never first-time results.**
- Cost: 79.71 USD real (from API token usage, Sonnet 5.5 list prices), over 18 runs plus the inconclusive run 0. Longest single run 7.46 USD. Cap rules (130 USD total, 20 USD one run) were never reached.
- Interventions: none during runs 1 to 3. Three setup faults before run 0 (access key, prompts checkout, temperature option) are logged in `pilots/209/interventions.yaml`; run 0 itself is classed inconclusive in the pre-registration addendum.

## Records

Agent: the pilot branch's `agent/` (209a merged, plus 209b); agent commit `cc6597b64bb3` for every run 1 to 3. Model: `anthropic_api` claude-sonnet-5-5 for every purpose, `--verif-level V2 --max-usd 12 --budget-scale 3.5 --board kr260 --review off --interview off`, pinned private prompts (knowledge commit 5e2eab87), real dollars from `model_calls.jsonl` (the `cost_usd` per call: input, output, cache read and cache write priced). Interview: off for every run, so the agent took its defaults; nothing was asked or answered by hand (asked 0, answered 0, defaulted: the open questions it chose). A run that reached stage 9 pauses there for the owner's approval to program the board; it is never approved, so those runs have no `summary.json` and no DOC step; the run records are built from `role_usage.jsonl`, `model_calls.jsonl` and the build outputs (`run_record.json`).

Where each record is: `pilots/209/<id>/run<k>/` (`run_record.json`, `summary.json` when the run ended, `role_usage.jsonl`, `model_calls.jsonl`, `agent_stdout.log`, `build/trace/trace.md` and `trace.json`, `build/verif/verif_gates.json`, `design/` without `build/`). Run 0 of p1 is in `pilots/209/p1_clkmeter/run0_inconclusive/`. The cost ledger is `pilots/209/cost_ledger.tsv`.

Gates column: V2 = the agent's verification level V2 (simulation against its own model with the seeded checks); BS = bitstream built; T = timing met after routing (WNS in ns at the board clocks); HW-ready = `bringup_ready` ok and the generated `hw_checks.py` passes against its own mock. Hardware columns are all **pending board visit** and are omitted from the table.

| Design | Run | Outcome | V2 | BS | WNS ns | LUT / FF / BRAM / DSP | Tokens | USD | Trunc calls (rtl+tests) | Wall min | Interventions |
|---|---|---|---|---|---|---|---|---|---|---|---|
| p1_clkmeter | 1 | reached stage 9, paused for programming approval | pass | yes | 3.546 | 205 / 1026 / 0 / 0 | 5,946,665 | 3.07 | 0 (0+0) | 49 | 0 |
| p1_clkmeter | 2 | reached stage 9, paused for programming approval | pass | yes | 2.501 | 276 / 844 / 0 / 0 | 5,329,401 | 2.93 | 0 (0+0) | 43 | 0 |
| p1_clkmeter | 3 | stopped: stage 3 visited more than 4 times; last failing gate: post_synth:post_synth_methodology_no_crit | pass | no | - | - | 9,417,663 | 5.74 | 0 (0+0) | 61 | 0 |
| p2_bram_rom | 1 | reached stage 9, paused for programming approval | pass | yes | 2.698 | 274 / 608 / 2 / 0 | 9,053,882 | 5.90 | 0 (0+0) | 58 | 0 |
| p2_bram_rom | 2 | reached stage 9, paused for programming approval | pass | yes | 35.028 | 304 / 617 / 2 / 0 | 7,148,630 | 3.94 | 0 (0+0) | 50 | 0 |
| p2_bram_rom | 3 | reached stage 9, paused for programming approval | pass | yes | 27.409 | 323 / 627 / 2 / 0 | 8,599,374 | 7.46 | 0 (0+0) | 53 | 0 |
| p3_crc_engine | 1 | stopped: stage 2 visited more than 6 times; last failing gate: lint; owned by the rtl role; the same fai | pass | no | - | - | 5,505,794 | 2.95 | 0 (0+0) | 19 | 0 |
| p3_crc_engine | 2 | reached stage 9, paused for programming approval | pass | yes | 3.68 | 327 / 583 / 0 / 0 | 7,340,750 | 3.96 | 0 (0+0) | 48 | 0 |
| p3_crc_engine | 3 | reached stage 9, paused for programming approval | pass | yes | 3.29 | 431 / 613 / 0 / 0 | 7,327,885 | 3.67 | 0 (0+0) | 54 | 0 |
| p4_fir_dsp | 1 | stopped: stage 2 visited more than 6 times; last failing gate: lint, simulate, design standards, verific | fail | no | - | - | 3,716,428 | 4.39 | 6 (6+0) | 34 | 0 |
| p4_fir_dsp | 2 | stopped: stage 2 visited more than 6 times; last failing gate: lint, simulate, design standards, verific | fail | no | - | - | 3,909,150 | 3.97 | 6 (6+0) | 31 | 0 |
| p4_fir_dsp | 3 | stopped: stage 2 visited more than 6 times; last failing gate: lint, simulate, design standards, verific | fail | no | - | - | 2,875,323 | 3.57 | 7 (6+1) | 28 | 0 |
| p5_async_fifo | 1 | stopped: stage 2 visited more than 6 times; last failing gate: lint, simulate, design standards, verific | fail | no | - | - | 3,355,726 | 4.18 | 7 (6+1) | 33 | 0 |
| p5_async_fifo | 2 | stopped: stage 2 visited more than 6 times; last failing gate: lint, simulate, design standards, verific | fail | no | - | - | 3,505,818 | 4.52 | 7 (6+1) | 36 | 0 |
| p5_async_fifo | 3 | stopped: stage 2 visited more than 6 times; last failing gate: lint, simulate, design standards, verific | fail | no | - | - | 3,353,157 | 3.89 | 6 (6+0) | 28 | 0 |
| p6_glitchfree_mux | 1 | stopped: stage 2 visited more than 6 times; last failing gate: lint, simulate, design standards, verific | fail | no | - | - | 3,870,051 | 4.43 | 6 (6+0) | 35 | 0 |
| p6_glitchfree_mux | 2 | stopped: stage 2 visited more than 6 times; last failing gate: lint, simulate, design standards, verific | fail | no | - | - | 2,817,282 | 3.94 | 6 (6+0) | 34 | 0 |
| p6_glitchfree_mux | 3 | stopped: stage 2 visited more than 6 times; last failing gate: lint, simulate, design standards, verific | fail | no | - | - | 3,250,095 | 4.09 | 7 (6+1) | 34 | 0 |

p1 run 0 (inconclusive, infrastructure fault: the agent's cost accounting for `anthropic_api` cut stage 1 at 8 calls per visit; before 209b): 3.12 USD upper bound, 1,296,101 tokens, not counted, kept in `run0_inconclusive/`.

## Mean and spread per design

mean (min to max) over the three runs; resources and WNS over the runs that built.

| Design | Reached bitstream | USD | Wall min | LUT | FF | WNS ns |
|---|---|---|---|---|---|---|
| p1_clkmeter | 2 of 3 | 3.92 (2.93 to 5.74) | 51 (43 to 61) | 240 (205 to 276) | 935 (844 to 1026) | 3.02 (2.50 to 3.55) |
| p2_bram_rom | 3 of 3 | 5.77 (3.94 to 7.46) | 54 (50 to 58) | 300 (274 to 323) | 617 (608 to 627) | 21.71 (2.70 to 35.03) |
| p3_crc_engine | 2 of 3 | 3.52 (2.95 to 3.96) | 40 (19 to 54) | 379 (327 to 431) | 598 (583 to 613) | 3.49 (3.29 to 3.68) |
| p4_fir_dsp | 0 of 3 | 3.98 (3.57 to 4.39) | 31 (28 to 34) | - | - | - |
| p5_async_fifo | 0 of 3 | 4.19 (3.89 to 4.52) | 33 (28 to 36) | - | - | - |
| p6_glitchfree_mux | 0 of 3 | 4.15 (3.94 to 4.43) | 34 (34 to 35) | - | - | - |

Wall time is from the heavy slot being taken to the run ending (the Vivado builds are inside it). Fmax is not stated: the pilot specs set no clock for p1 to p3 beyond the board clocks, and WNS is the slack at those constraints; p4's 250 MHz gate was never reached.

## What each design reached, and the generated bring-up checks

| Design | Run chosen for the board | Why | Generated `hw_checks.py` vs its own mock | Pilot host check vs the same mock |
|---|---|---|---|---|
| p1_clkmeter | run 1 (`20261125-051203-b327`) | first of the three to reach a bitstream | 10 checks, 0 failed | PASS |
| p2_bram_rom | run 1 (`20261125-074644-0dfa`) | first of the three to reach a bitstream | 11 checks, 0 failed | PASS |
| p3_crc_engine | run 2 (`20261125-104806-b7dd`) | first of the three to reach a bitstream | 8 checks, 0 failed | PASS |
| p4_fir_dsp | none | no run reached a bitstream | - | - |
| p5_async_fifo | none | no run reached a bitstream | - | - |
| p6_glitchfree_mux | none | no run reached a bitstream | - | - |

The mock is the agent's own model of the spec (written by the agent, from the same spec), so a pass says the agent's two artefacts agree with each other and with my host check's register map; it does not say the RTL works on the board. Build ids (USR_ACCESS) for the board stages: p1 `eb240c30`, p2 `e7d71fdc`, p3 `4c7b1ce0` (in `pilots/209/<id>/stamp.txt`; the board script reads the build in place from the run directory in `board_run.txt`, because the build stamp covers paths and a copied design cannot be programmed).

## Requirements: how each was verified

Full tables per design (requirement, method, result) for the three chosen runs are in [requirements.md](requirements.md); every run's `build/trace/trace.md` is next to its record. Summary of the chosen runs (method results are counted per requirement and method):
- p1_clkmeter run 1: 29 requirements; method results {'pass': 38, 'pending': 10}. Simulation methods pass; the **hardware rows are pending the board visit** (they stay `pending` until the owner's run). V3 (mutation score), the sign-off stage and V-HW are not passed in any run: the pilot ran V2 on purpose, V3 is a known agent gap.
- p2_bram_rom run 1: 33 requirements; method results {'pass': 40, 'pending': 15}. Simulation methods pass; the **hardware rows are pending the board visit** (they stay `pending` until the owner's run). V3 (mutation score), the sign-off stage and V-HW are not passed in any run: the pilot ran V2 on purpose, V3 is a known agent gap.
- p3_crc_engine run 2: 25 requirements; method results {'pass': 33, 'pending': 10}. Simulation methods pass; the **hardware rows are pending the board visit** (they stay `pending` until the owner's run). V3 (mutation score), the sign-off stage and V-HW are not passed in any run: the pilot ran V2 on purpose, V3 is a known agent gap.
- p4, p5, p6: the traceability matrix was built from the plan (39 to 44, 35 to 39 and 25 to 29 requirements across the runs) with every method pending, since no RTL existed.

## Reproduce

- Host-check dry runs, no board: `python -m pytest pilots/209/tests` (22 tests: each check passes a correct mock and fails nine seeded faults).
- The agent runs: `pilots/209/run_agent.sh <id> <k>` (one run) or `pilots/209/run_all.sh` (all 18), then `pilots/209/record_one.sh`. They need the owner's `.env` access key, the pinned private prompts (`FDA_KNOWLEDGE`), Vivado 2025.2, a heavy slot, and the model API key.
- Board stages (owner, with the planner's command at the visit): `pilots/209/run_pilot_board.sh <stage> YES`. Only p1, p2 and p3 have a board stage.
- Pre-registered criteria, frozen before the first run: `pilots/209/<id>/preregistration.md` (with dated addenda).

## Known gaps and limits

- **Output-length limit (p4, p5, p6).** See above; brief 224 is the fix, a labelled second arm re-runs those three, never counted as first time.
- **p1 run 3 and p3 run 1 failures are agent failures**, recorded in the retrospectives below; nothing was changed between runs.
- **V3 not tested.** `--verif-level V2` was pre-registered because V3 stalled the toy design at stage 2 on mutation score in 209a.
- **No `summary.json`/DOC step for runs that reached stage 9.** They pause for an approval to program that the pilot never gives (no board commands by the executor).
- **Hardware pending.** Pre-registered criteria are in each `preregistration.md`; the C3 clock reading (p1) goes into `boards/kr260/board.yaml` only after the run, by the planner.
- **Host checks and the agent's mocks agree (7 of 7 built runs) but the mocks are the agent's.** The three board stages test the real thing.
- **Register map was in the spec.** The agent was handed `jtag_bus.sv` as data and the register map in the spec, the common map (ID, BUILD, SCRATCH) from brief 209a, so these runs measure the agent on a specified bus, not on bus design.
- **Interview off.** The agent took its defaults; some defaults may have filled gaps the spec left, none by hand.
- **Costs are real dollars from token usage at list prices**; the agent's own `cost_usd` and the run caps (12 USD, budget scale 3.5) were never hit.
- **Single draws.** Three runs per design is a spread, not a rate.

## Retrospectives of failed runs

Format: stage, root cause, the agent change that would have prevented it. Fixes are proposed follow-up briefs, not made here.

### p4, p5, p6, all runs (9 runs): truncated Designer replies
- Stage: 2 (rtl-design-creation). Evidence: `model_calls.jsonl` of each run: 6 or 7 calls with `stop_reason: max_tokens` (16,000 completion tokens, 95 to 136 s each), all by the `rtl` role, plus one `tests` call in four runs (p4 run 3, p5 runs 1 and 2, p6 run 3); no `rtl/` directory exists in any of the 9 designs; each run ended "stage 2 visited more than 6 times".
- Root cause: the Designer writes whole files in one tool call; for these designs (DSP FIR, async FIFO with PRBS and counters, clock mux) one reply is longer than 16,000 tokens, so the reply is cut mid tool call, the call is dropped, and the model repeats the attempt, using the visit.
- Change that would have prevented it: brief 224: streaming output, a larger `max_tokens`, and RTL written file by file. The 209b change that records truncated calls made this visible. A labelled second arm re-runs p4, p5 and p6 after 224; those results are not first-time results.

### p1_clkmeter run 3: stage 3 (constraints)
- Root cause: the design.xdc placed the GT reference-clock buffer with `set_property LOC IBUFDS_GTE4_X1Y6 [get_cells { u_ibufds_gt }]`; Vivado answered "'IBUFDS_GTE4_X1Y6' is not a valid site name", and the post-synth exceptions and methodology gates failed on it on all 4 constraints visits (each ended `stage_budget` after 30 turns). Run 1 of the same spec constrained the buffer by its package pins (Y6/Y5) only and passed.
- Change that would have prevented it: derive the GT refclk site from the board file (`gt.sfp.refclk` and the `gt_plan` tool) and check that the XDC LOC names exist before the build (a pre-synthesis site check), or send the failing LOC message back with the board's valid sites.

### p3_crc_engine run 1: stage 2 (rtl-design-creation, lint)
- Root cause: the two lint warnings were in the supplied `data/jtag_bus.sv`, which must stay unchanged. The agent had a reasoned waiver in `lint/waivers.yaml`, but its raw lint call did not apply the waiver file, so it saw the same failure on 5 consecutive visits and spent the visit limit; its last message says it expected the stage gate to apply the waiver but did not run it. (Runs 2 and 3 of the same spec passed.)
- Change that would have prevented it: make the Designer's `lint` tool apply `lint/waivers.yaml` (or say so in its result), and treat "the same failure on N visits owned by rtl with no change" as a prompt to run the stage gate rather than the raw tool.

## Proposed follow-up briefs

1. 224 (exists): long output: streaming, larger max_tokens, file-by-file RTL; then the labelled second arm for p4 to p6.
2. GT refclk site from the board file plus an XDC LOC existence check before synthesis (p1 run 3).
3. `lint` tool applies the design's waiver file to supplied files (p3 run 1).
4. Run summary for runs paused at the programming approval: write `summary.json` and the DOC step at the pause, so a paused run has the same record as a finished one.
5. V3 mutation score on supplied bus files (209a's known gap): exclude data/ files from mutation targets.
