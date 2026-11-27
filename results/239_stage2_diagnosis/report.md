# Brief 239: why simple pilot designs fail stage 2, and what fixed it

Executor Sonnet 5.5, 2026-11-26 to 2026-11-27. Branch `b239-stage2` (PR number in the hand-back). Pre-registration: [prereg.md](prereg.md), stamped before the first run.

## Result, nulls first

- **Stage-2 own pass: 9 of 9 after (Wilson 95% 0.70 to 1.00); before, brief 227 arm A with the same flags: 4 of 9; all 36 earlier runs pooled: 14 of 36.** The pre-registered line was 7 of 9 or more. One-sided Fisher: 0.015 against arm A, 0.001 against the pooled runs. n = 9, one model and harness, earlier runs on different code: this is a before and after, not a controlled A/B, and the fixes cannot be told apart by it.
- The independent spec-only bench: clean pass in 8 of 9; 1 `unresolved` (p1 r1: the bench guessed port names and a reset behaviour the request does not state, so triage judged the bench wrong twice). Before: it built in 0 of 7 runs where it fired (see below).
- There is **no independent check of built behaviour and no board run**: "own pass" is the project's own gates plus a model-written bench that shares the model family.
- Withdrawn: a sixth change (a primitive-name rule and a `sim/` folder) was added after the series and then reverted before merge (see below).

| | before (227 arm A) | after (239) |
|---|---|---|
| own pass | 4/9 | 9/9 |
| bench clean pass | 0/9 | 8/9 |
| mean stage-2 visits | 4.00 | 2.67 |
| repeated identical stage-2 lint findings (total) | 22 | 0 |
| mean plan-cost estimate (usd, not provider-reported) | 3.21 | 2.79 |

The after census ([after/census_table.md](after/census_table.md); its "227" column means series 239) has no FDA-CON-8, STD-CDC-01 or lint finding. What remains is real: 6 of 9 runs had failing own simulations at some visit (type a), which the repair loop then fixed.

Run ids (run folder: record under `arms/<tag>/`): p1 r1 20261126-212817-7233, p2 r1 20261126-222827-292b, p3 r1 20261126-235936-8daa, p1 r2 20261127-003722-2e47, p2 r2 20261127-005937-01f7, p3 r2 20261127-022640-a543, p1 r3 20261127-025448-77bd, p2 r3 20261127-032017-72eb, p3 r3 20261127-034545-4b23. Seven cells were run twice: their first attempt died with `PromptUnavailable` (a shared prompt checkout was deleted), an environment fault and not a design result (note in prereg.md; logs kept outside the repo). Baseline ids: `baseline_runs.csv`.

## Census (from records only)

Method: `census.py` reads each run's LangGraph checkpoints (36 runs: 213 all 18, 227 arms A and C 18), takes each distinct failing gate event and splits it into findings. Tables: [census_table.md](census_table.md) (gate, id, category, events, runs, repeats), [census_events.csv](census_events.csv), [console_logs.md](console_logs.md) (every gate log, including the Designer's own tool calls). Categories: a real design error, b rule the Designer is told of late or never, c rule that fires on correct work, d tool or harness fault, e what the agent cannot know at stage 2.

| Finding | Cat | Runs (213 / 227) | What it was |
|---|---|---|---|
| FDA-CON-8 | c | 20 (10 / 10) | the Clarifier lists the internal register bus (`direction: internal`) as ports; the rule asked the top to have them. 126 finding rows, repeated verbatim across visits |
| STD-CDC-01 | c | 21 (12 / 9) in gate events, 25 in any log | `architecture.yaml` names the supplied `data/jtag_bus.sv` as `inline_in`; the checker knew only rtl/ and shell/. It routed to stage 1, where it cannot be fixed: 7 stops "stage 1 visited more than 4 times" |
| Verilator UNUSEDSIGNAL in `data/jtag_bus.sv` | c, b | all 36 runs; 316 of 463 lint logs had only these | `tdo`, `cmd_s[45]` in a supplied read-only file. The Designer was never told `lint/waivers.yaml` exists ("no way to waive") |
| "rtl: did not run (no gates record)" | d | 36 | added to every failing stage-2 visit; alone (213 run 8) it was a Vivado build refused while another job held the PC (e) |
| simulate and V2 failing tests | a | 15 | own bench against own model: register-read mismatches, an off-by-one count, a bench timeout |
| clarify "compound requirement" | a | 36 | stage 0, sent back automatically |
| STD-RST-01 on `rtl/xilinx_sim_stubs.sv` | c, a | 11 (any log) | the Designer's stub of `xpm_cdc_async_rst` has an async reset; see "Withdrawn change" below |
| STD-CLK-01 on a wrapped MMCM | c? | 4 | a gap, not changed |

Of the 22 runs that did not own-pass, all 22 met at least one of the first three rules; the findings of the last stop were only those rules in 13, partly in 6, and in 3 not at all ([last_blocker.csv](last_blocker.csv)). The real errors (type a) are the minority and the repair loop handles them; the first three rules were pure loss (22 repeated lint findings in arm A alone).

Limits: the 36 runs span code versions (brief 231's lint policy landed mid-way), 213's run folder is gitignored (`results/213_repair_feedback/runs/` is not on main; I read the worktree), and the census sees only what the checkpoints keep (lint detail is truncated to the tail).

## The independent bench

All 7 "bench judged wrong" runs of 227 were the same fault: the bench's build (`agent/graph/spectest.py`, the entry file the harness writes) compiled the shell and `rtl/*.sv` but not the supplied `data/` sources, so iverilog stopped with `Unknown module type: jtag_bus`. `built` was false in the first bench run of all 7, zero checks ever ran, triage said `bench_wrong` twice (true only in the sense that the bench never reached a check), and two bench rewrites could not fix a harness gap. So: neither the design nor the bench's content was wrong; the harness was. The bench was right in none of the 7 and judged the design in none; in the other 11 runs it never fired. In 213 it was off. After fix 4 the bench built in 9 of 9 and passed in 8; its one remaining verdict is a genuine content problem (the bench guessed unstated ports). The bench is therefore not wrong more often than right once it builds, but 9 runs are too few to rate it.

## Rule and code changes, for the owner

1. **FDA-CON-8 skips `direction: internal` ports** (`agent/core/constraints.py`). Evidence: 20 runs.
2. **STD-CDC-01 accepts `inline_in` naming a module of the design's `data/`** (`flow/standards_check.py`); an unknown name still fails. Evidence: 21 to 25 runs, 7 stage-1 stops.
3. **Policy change (approved by the planner, 2026-11-27): UNUSEDSIGNAL, UNUSEDPARAM and DECLFILENAME are not raised for files under the design's `data/`** (`agent/core/tools.py` `stub_waiver_vlt`, `flow/lint_ruleset.py`), the same three codes brief 231 already waives for `sim_stubs` files. Errors in those files and every other rule still fail, and the design's own files are linted as before. Evidence: the supplied file is read-only and byte-identical, so no Designer edit can clear these warnings; they were present in all 36 runs and were all the lint findings in 316 of 463 lint logs.
4. **The independent bench builds the `data/` .sv and .v sources** (`agent/graph/spectest.py`). Evidence: 7 of 7 bench verdicts.
5. **The Designer is shown what the stage-2 gates check before it writes RTL** (`agent/graph/run.py` `stage2_rules_note`, built from `flow/hdl_rules.yaml`: rule ids, Verilator codes, one-line fixes, FDA-CON-8/9, the `lint/waivers.yaml` format). Code, not a private prompt, so no knowledge-bank PR; new golden `b239_request_golden.json`, one new request path.
6. **Withdrawn before merge (planner, 2026-11-27).** A rule refusing modules named like AMD primitives in synthesis sources, with stand-ins moved to a `sim/` folder, was added after the series. It was reverted because (a) reading every `sim/*.sv` broke the b96 10G design's tests in CI (b96 keeps alternative models and benches in `sim/`: duplicate `gth_wiz` and `tb_core` modules), and (b) the house convention (`agent/graph/run.py`) already puts these stand-ins in `rtl/xilinx_sim_stubs.sv` between `ifndef SYNTHESIS`, so synthesis does not see them. Follow-up: an advisory check for a primitive-named module that is *not* guarded by `ifndef SYNTHESIS`, and STD-RST-01 skipping guarded stubs.

## Known gaps and follow-ups

- STD-CLK-01 on an MMCM wrapped in a submodule (4 runs): left alone, by decision.
- 6 of 9 after-runs still failed their own simulation at some visit; that is the next thing to look at, with the model-versus-RTL mismatch classes in `after/census_table.md`.
- KB PR #109 (brief 217) repair records keyed on FDA-CON-8, STD-CDC-01 and supplied-file lint warnings should be regenerated after this merges (`tools/repair_memory`); not done here.
- 213's run records are gitignored and not on main.
- Course impact: none (no new measured fact about a vendor tool). Device families: none; the findings are about our own gates.
