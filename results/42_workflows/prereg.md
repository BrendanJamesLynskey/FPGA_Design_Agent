# Brief 42, harness engineering arms: pre-registration (written 2026-11-11, before any scored run)

Scope of this run: the addendum's harness arms H1 and H2 against the baseline A0 (round 1). Nothing else is scored here.

## Correction to the planner's audit (found while implementing H1)

`reports/h0_harness_audit_2026-11-11.md` read the middleware from the graph's nodes. `SummarizationMiddleware`,
`FilesystemMiddleware` and the prompt-caching middleware wrap model and tool calls and add no node, so the audit missed them.
`agent/tools/harness_audit.py` (committed, `PYTHONPATH=. python agent/tools/harness_audit.py`) reads the stack from the
`create_agent` call. With the `fda` profile the role agents have: `FilesystemMiddleware`, `_ParentNotifierMiddleware`,
`SummarizationMiddleware`, `PatchToolCallsMiddleware`, `AnthropicPromptCachingMiddleware` (does nothing for a non-Anthropic
model), `UnsupportedContentMiddleware`. So:

- Summarisation **is** on, but our chat model has no profile (`model.profile is None`), so deepagents' fixed fallback applies:
  trigger 170,000 tokens, keep the last 6 messages. An 80-turn repair visit averages about 80,000 prompt tokens a turn and
  never reaches it.
- deepagents' large-result offload is on at 20,000 tokens (80,000 characters). Our registry clips every tool result to
  20,000 characters first, so it never fires.
- Prompt caching is wired in, but only acts for an Anthropic model. H7 (not in this run) is therefore a model/provider question.

H1 is accordingly a **tuning** of two existing mechanisms (when to summarise, when to offload) plus our own offload, not an
addition from nothing. The baseline A0 is unchanged and keeps both defaults.

## Arms (each a flag; the baseline graph is untouched)

| Arm | Flag | What changes |
|---|---|---|
| A0 | none | today's graph, with the #115 `load_skill` fix and brief 45's gate fix (both on main c06a32c) |
| H1 | `--harness-arm H1` | rtl role: a flow tool's result over 6,000 characters is written in full to `build/tool_results/NNN_<tool>.json`; the model gets the small fields, the output's first and last 1,500 characters, and the path to `read_file`. Knowledge tools are not offloaded. All roles: `SummarizationMiddleware` with trigger 40,000 tokens (approximate count) and the last 10 messages kept, in place of 170,000 / 6. Implementation: `agent/graph/context.py`; chosen after reading deepagents 0.7.32 (`middleware/summarization.py`, `_message_eviction.py`, `filesystem.py`). |
| H2 | `--harness-arm H2` | `simulate` (a) refuses a bench with an unbounded event-waiting `while` loop before starting the simulator (`agent/core/cocotb_lint.py`; rules in its docstring; 0 of 80 committed benches flagged, test in `test_42_harness.py`); (b) runs under `flow/sim_watchdog.py` with a wall limit of 120 s + the declared `timeout_time` budget / 1e5 ns per second when every test declares one, else 4 x the last passing run + 120 s, else 600 s (180 to 900 s, doubled with coverage), instead of the usual 600 to 7200 s (1800 s without a baseline); (c) a timeout comes back as a structured `sim_hang` result naming the test, the last simulation time and whether time was still advancing. |

No registered tool, schema or description changes, so the golden requests (`agent/tests/fixtures/*golden*.json`) are not
regenerated: the unit tests that compare them pass unchanged. (Tool-set changes, the other arms, regenerate them in a separate commit.)

Not in this run, and why: H3 to H8 and A1 to A6 are not scored here. Round 2 (H4, H3, H5) and round 3 (H6 to H8) need the
same wall time per arm as round 1 (see Time); starting them is judged at the end of round 1 and stated in the report.
A2, A3 and A6 likewise: only after round 1, if time allows; otherwise listed as not run.

## Tasks, seeds, runs

- Development split and the brief 24 drills only (the drills sit outside every split). No `benchmark_private`, `eval1`, `_eval1`.
- **Round 1 tasks (4):** `t1_gray_stepper` (easy T1; passes possible), `d24_registered_outputs`, `t1_debounce_bank` (long timing
  parameters, the kind of bench that runs long), `d24_no_extra_latency` (the B1 drill whose bench hung three times). Four more are
  listed in the driver for an extension (`t1_bcd_updown`, `t2_i2c_scanner`, `t1_lfsr_dice`, `t1_sync_fifo_regs`); they run only
  if round 1 completes and time remains. The brief asked for about 8 tasks: this is cut to 4 **tasks, not seeds** (the brief's
  rule) because a run takes 25 to 60 minutes.
- **Seeds:** 3 per task and arm. The agent has no seed flag; a "seed" is the repeat index (the model samples at temperature 0.2).
- **Runs:** 4 tasks x 3 seeds x 3 arms = 36. Blocks are (seed, task), seed-major, so a partial result has every task at the
  same repeat count. The three arms of a block run one after another with the order rotated block by block (pairing).
- **Configuration of every run:** `python -m agent run <spec.md> --stop-after 2 --verif-level V1 --max-usd 0.75 --model
  openai/gpt-6-luna`, deepagents harness, every role on luna through OpenRouter (`data_collection: deny`), interview off,
  review off, board nexys_a7_100t. Stage 2 ends before synthesis: **no Vivado**, so the rule change of 2026-11-11 about
  overlapping Vivado implementation runs does not apply; sim-only runs take a slot with the text "no Vivado" and, if both
  slots are free, two workers run at once. Knowledge bank: `FPGA_Design_Agent_Knowledge` at 283afd9, the pin in
  `knowledge/PACKS.md`.
- **Frozen code:** the arms are committed first; runs execute from a separate worktree at that commit (`FROZEN_SHA`); the driver
  refuses to start a run if the tree's HEAD differs or `agent/` or `flow/` is dirty (PREFLIGHT_FAIL, no record, driver stops).
  Claude Code is not used, so the CLI pin of `eval_run_checklist.md` does not apply; the other pins (venv, Icarus, sim image,
  deepagents) are recorded in `environment.txt`. Scoring has its own light lock (`score.lock`), one score at a time.
- **Hard limits per run:** 5,400 s wall (the driver kills its own run's process group, then removes any `fda-<pid>-*` sandbox
  container whose agent process is gone), the agent's own cap USD 0.75, 300 turns (the run limit), stage 2 at most 6 visits.
  A run ended by the wall limit is recorded as censored (its summary is not written, so tokens and cost are lost; it is charged
  the 0.75 ceiling against the cap).

## Metrics (all recorded in `runs.jsonl`; nothing is estimated by a model)

Per run: hidden-bench result (pass, and tests passed of tests: `benchmark/tools/run_task.py` on the run's `rtl/`; no LLM scores);
stage-2 gates passed; stage-2 visits (repair visits = visits - 1); tokens and cost (provider-reported `summary.json`); wall time;
turns; simulate calls, **hangs** (a `simulate` that ended by a timeout or the watchdog: audit log `result_summary` contains
"timed out after" or "simulation hung"), simulate seconds, bench refusals under H2, offloaded results under H1.

**Primary metric per arm:** H1: tokens per run (and cost). H2: wall time per run and hangs. **Safety metric for both:** hidden-bench
tests passed as a fraction of the task's tests, and pass count: an arm that lowers it is not adopted whatever it saves.

## Analysis (fixed now)

- Pairing is within a block (same task and repeat index); the unit is the block. Per block: arm minus A0 for tokens, cost, wall time,
  tests-passed fraction; for pass and stage-2 gates the counts of blocks where only the arm / only A0 passed (discordant pairs).
- Intervals: percentile bootstrap (10,000 resamples of blocks, seed 20261111) of the **median** paired difference for tokens,
  cost and wall time, and of the mean for the tests-passed fraction. With at most 12 blocks an interval is wide; only a large effect
  (a median change of 40 % or more of A0's median) can be told from noise, and the report says so for every row.
- Censored runs (hard limit): counted as 5,400 s wall; tokens and cost are missing, so those blocks are left out of the token and cost
  comparisons and listed.
- Nulls are stated first. A pass-rate difference of one or two blocks is not a result.
- **Adopt rule (stated before the data):** adopt an arm as default only if its primary metric improves by at least 30 % in the
  paired median with a bootstrap interval that excludes 0, **and** the tests-passed fraction does not fall (its mean paired
  difference interval does not lie below 0) **and** pass discordant pairs are not worse than A0's by more than one. Otherwise: keep
  as an option (a hint of an effect), or drop (no effect or harm). A single hang avoided is an example, not a rate.

## Cost and time estimate

- From brief 36 (the same model, `--stop-after 2`, V1, the same kind of task): six luna runs cost USD 0.098 to 0.340, mean 0.233
  (`results/spend_ledger.csv`), 3.9 to 16.9 million tokens a run, 25 to 60 minutes each.
- Round 1: 36 runs x 0.233 = about **USD 8.4**; the ceiling if every run reached its USD 0.75 cap is 27.0. Both are under the
  brief's USD 60. Cost will not bind; **time does**: 36 runs x about 45 minutes = 27 hours for one worker, about 14 hours with two.
- Stop rule: stop launching runs when (1) the USD 60 cap would be passed (the driver counts censored runs at the 0.75 ceiling),
  (2) 70 % of the 5-hour usage window is reached (the agent runs use the OpenRouter key, not the plan, so this is about this session's
  own work), (3) a PREFLIGHT_FAIL or a stop file, or (4) this session runs out of time; whatever blocks are complete are reported,
  with the count of blocks and arms, and a block with a missing arm is left out of the paired analysis, never filled in.
- Spend is logged per run in `results/spend_ledger.csv` (brief `42_harness`).
- OpenRouter models only luna (never Fable or Opus through OpenRouter); the usage check runs at the start and the end.

## Known risks stated in advance

- Runs of one arm are not independent of load on the machine (two workers, other sessions): wall time is the noisiest metric.
- H2's static check can refuse a bench the baseline would have run (a false alarm). It is counted (`refused_unbounded`) and is a cost
  of the arm, not hidden.
- H2's 180 to 900 s wall limit can cut a long, legitimate simulation (a coverage run); such a run shows as a hang, and the report
  separates hangs that were true hangs (log tail) from long runs.
- H1's summariser is the same model, so it adds model calls (counted in tokens and cost) and can drop a fact the role needed.
- luna's pass rate on these tasks was 0 of 6 in brief 36: pass counts may be zero in every arm, in which case the tests-passed
  fraction and the stage-2 gates carry the comparison and the report says the pass-rate comparison has no information.

## Amendment 1 (2026-11-11, before any scored run): arm H9, typed report digests (owner idea, brief addendum "Arm H9")

Stated before any H9 run; no scored run of any arm had started when this was written, so the code freeze below replaces the
one named above (the arms H1 and H2 are unchanged; only H9 and its golden regeneration were added).

| Arm | Flag | What changes |
|---|---|---|
| H9 | `--harness-arm H9` | New registered tool `report_digest(name, variant, level, focus)` (`agent/core/report_digest.py`, deterministic, no model; levels summary / standard / detail; focus = path index, rule ID, clock pair or test name; always ends with the report's path). It reuses the gate parsers in `flow/gates.py` (timing summary, utilisation, power, DRC and methodology rule tables, CDC) and has regular-expression digesters for simulation output, lint, `vivado.log`, with a head/tail fallback. With the arm on, a role that may call `report` is also offered `report_digest`, and a **large** (over 4,000 characters) result of `build`, `gates`, `simulate` or `lint` is replaced by the `summary` digest plus the small structured fields (for `gates`: pass, first failed stage, failed gate names) plus the path of the full result (`build/tool_results/NNN_<tool>.json`; named only for the rtl role, the only role whose file tools can read it). |

- **Tests:** per report type, fixtures are the real Vivado reports of the flow's good and seeded-fault builds
  (`flow/tests/data`); a seeded fault (negative WNS, critical methodology and DRC rules, unsafe CDC crossings) appears at `summary`
  level; numbers equal the gate parsers' (`agent/tests/test_42_harness.py`, H9 section).
- **Golden requests:** the tool registry gained a tool, so `tool_registry` differs; the golden (`b42_request_golden.json`) and the MCP
  schema snapshot (schema 1.8.0) are regenerated in their own commit, and only `tool_registry` differs from the brief 36 golden.
  With H9 off no role is offered the tool; the baseline's prompts, plans and per-role tool lists are unchanged.
- **What round 1 can and cannot show for H9:** scored runs stop after stage 2, where no Vivado report exists and `report` is not a
  stage-2 tool, so `report_digest` itself is not called and the Vivado digesters are exercised only by the fixture tests. Round 1 measures
  the part that does act in stage 2: typed summary digests of large `simulate`, `lint` and `gates` results against H1's generic
  head-and-tail offload and summarisation (the comparison the addendum asks for). A stage-3-and-later run would be needed to measure
  the Vivado digests; it is not in this run.
- **Primary metric:** tokens per run (and cost); safety metric: tests passed fraction. Same adopt rule as H1.
- **Round 1 is now 4 arms:** 4 tasks x 3 seeds x 4 arms = 48 runs, about USD 11.2 at the brief-36 mean of 0.233 a run (ceiling
  USD 36.0 at the 0.75 cap), inside USD 60; no task is cut for cost. Time is the binding limit: 48 runs x about 45 minutes is 36
  hours for one worker, 18 with two. Blocks stay seed-major (all four tasks at repeat 1 first), so a run stopped for time has equal
  repeats for every task; if only one or two repeats complete, the report says that only a very large effect could be seen.

## Amendment 2 (2026-11-11, planner correction of the H0 audit; recorded for H1 and H7)

The planner's correction agrees with the section "Correction to the planner's audit" above, which was committed before any run
and was verified from `deepagents/graph.py`'s middleware assembly and the `create_agent` call (`agent/tools/harness_audit.py`),
not from graph nodes. For the record of what H1 is measured against:

- **A0's baseline for H1 is summarisation at about 170,000 tokens** (fixed fallback because `FdaChatModel` reports no context size),
  large-result eviction at 20,000 tokens (never reached behind the 20,000-character clip), and Anthropic-only prompt caching
  (no effect on OpenRouter models).
- **H1 sets the thresholds deliberately**: summarisation trigger 40,000 tokens with 10 messages kept, and our own offload at
  6,000 characters for the rtl role. It does **not** give `FdaChatModel` a real per-model context size (a fraction-based trigger);
  that variant is not in this run.
- **H7 (prompt caching) is not run here.** It needs an OpenRouter caching path for the model in use; luna's provider behaviour was
  not checked, so no claim is made.

## Amendment 3 (2026-11-11 about 14:00, after 7 recorded runs; before any further run): infrastructure failures and a retry

**What happened.** 3 of the first 7 recorded runs ended with rc 1 and a `json.decoder.JSONDecodeError: Expecting ':' delimiter` at a
character position of 132,528 or more, inside the `model` node of the graph (the blind model writer): `t1_gray_stepper` H2,
`t1_gray_stepper` H9 and `d24_registered_outputs` A0, so the baseline is hit as often as the arms. **Cause, as far as the logs
show:** the driver kept only the last 800 characters of each run's output, so the full traceback was not kept; what is known is the
exception, the node, and that the document being parsed was 130,000 characters or more, which no legitimate tool call or response
here is. It is therefore a malformed or padded provider response (the body, or a tool call's `arguments` string); the model client
parses both with `json.loads`. This is not confirmed to the caller line. Not an arm effect.

**Handling (fixed now, applied equally to all arms):**

1. A run that ends with rc != 0, no summary and `JSONDecodeError` in its output is an **infrastructure failure**
   (`infra_failure` in `runs.jsonl`). It is not an arm failure: it is listed in the analysis, left out of every paired comparison, and
   its slot is **re-run**, up to 3 attempts per (task, repeat, arm); a slot with 3 infrastructure failures is reported as not run.
   The three runs above are marked this way. Their tokens and cost are the lower bound recovered from the finished role visits'
   `role_usage.jsonl`; their ledger rows carry the 0.75 ceiling already charged (conservative, left as is).
2. `OpenRouterClient` (`agent/graph/llm.py`) asks for the response again, up to 2 extra times, when the body or a tool call's
   `arguments` fails to parse, and prints `FDA_MALFORMED attempt N: ...`. This changes **no request**, so no golden hash changes; it
   only matters when a response is malformed. It is in the new frozen code for every arm from now on. Runs recorded before it
   (valid ones) ran under the previous commit; the retry cannot have changed a run that never saw a malformed response, and the
   per-run record names the code commit (`code`). The driver now keeps the last 2,500 characters of every failed run's output and counts
   `FDA_MALFORMED` lines per run (`malformed_retries`), so the next occurrence can be traced.
3. Re-running a failed slot is allowed to change which of the arm's repeats is run later than its block-mates; the pairing is by
   (task, repeat), so the block is complete only when all four arms have a valid run.

## Amendment 4 (2026-11-11, environment, owner rule "Exempt sim-only runs"; does not touch the arms)

Sim-only agent runs (no Vivado, no Verilator build of a large design) no longer take a heavy slot. Both of this brief's slot
locks were released at 13:53 (owner-checked case release). The driver takes none; before each run it waits until the 1-minute load is
under 6 and more than 12 GiB is available. Workers run as before under `systemd-run --user --scope -p MemoryMax=6G` (scope names
`b42-w1`, `b42-w2`, created by this session). Workers are restarted for amendment 3 with repeat 1 only (`--seeds 1`) and per-run
claims; repeats 2 and 3 are not run in this session for lack of time (see the report), stated here and not changed later.

## Amendment 5 (2026-11-11 16:05, data repair, no change to arms or analysis)

Two workers restarted in the same second (14:32:01) after amendment 3, and each took the lexically first new run directory as its
own, so the record of `t1_gray_stepper` H9 repeat 1 pointed at the H2 run's directory (`...-9301`) and carried a lower bound of its
tokens and cost. The record was re-derived from the correct run directory (`...-f218`) with `repair_records.py` (kept in the
folder; the record is tagged `repaired`); the H2 record was correct. `run_id` uniqueness and a match of each run's `config.json`
(task, arm) with its record were then checked for every record, and are checked again before the final analysis. The driver is not
changed: the collision needs a same-second start, and workers are not restarted again.

## Amendment 6 (2026-11-11 evening, planner decision: repeats 2 and 3 of round 1; driver fix; the two 0-of-0 scores)

- **Repeats 2 and 3 are run now**: the same 4 tasks and A0/H1/H2/H9, seeds 2 and 3, the same frozen code (a64be93), prereg,
  analysis and adopt rule; amendment 4's time cut is lifted for round 1 only. Round 2 and 3 arms stay unrun. Cost estimate: 32 runs x
  about 0.23 = about USD 7 at the repeat-1 mean (repeat 1: 0.19 mean over valid runs), ceiling 24; inside the cap. luna only; the
  malformed-response retry stays in. Sim-only rule: no slot; the driver waits while load is 6 or more or under 12 GiB is free.
- **Driver fix (no effect on the arms):** a new run directory is taken as a run's only if its `config.json` names this task and this
  exact arm and no record already has it (amendment 5's collision cannot recur). `built: false` is recorded in the score.
- **The two 0-of-0 hidden-bench scores** (`t1_gray_stepper`, runs ...-f218 H9 valid and ...-0fc7 H2 infrastructure-failed) are not a scoring
  bug. The scorer's own record says `built: false`: the agent's RTL does not elaborate under the bench's Icarus build (`Unresolved
  net/uwire UART_RXD_OUT cannot have multiple drivers`: the design drives the port the test shell's `uart_tx` also drives), reproduced by
  hand with `iverilog` on both designs. They stay counted as fails (a design that does not build in the bench's simulator failed), now
  recorded as `built: false` and reported separately from 0 of N tests passing.

## Amendment 7 (2026-11-12, after the independent review of PR #130; no run was repeated and no number changed)

- **The adopt rule's wording is ambiguous for H1 and H9.** The registered text is "Primary metric per arm: H1: tokens per run (and cost)"
  and "adopt an arm as default only if its primary metric improves by at least 30 % in the paired median with a bootstrap interval that
  excludes 0 ...". It was not fixed in advance whether "(and cost)" means cost also, or cost instead. `analysis.md` now quotes the rule
  and reports both readings (T: tokens, or tokens and cost together; C: tokens or cost). H1 fails on tokens (-65.6 %, interval includes 0)
  and passes on cost (-32.8 %, interval excludes 0), so it meets the rule under reading C and not under reading T. No reading is
  preferred after the fact, and nothing is adopted.
- **The sign tests are post hoc**: not pre-registered, not corrected for the 9 arm-by-metric tests (tokens, cost, wall time for three arms;
  Bonferroni 0.05 / 9 = 0.0056). They are labelled so in `analysis.md`; none passes that correction.
- **The decision to run repeats 2 and 3 followed sight of repeat 1's results** (amendment 6 lifts amendment 4's time cut). It restores the
  originally registered three repeats and changes neither the analysis nor the rule.
- **Amendment 5:** the repaired H9 record's `rc` is 1 although its summary says it stopped at the 300-turn limit; the repair dropped its
  `error` field, so the cause of the non-zero exit is not recorded. It is not a malformed-response failure (the worker log shows none), so
  it stays valid.
- **Amendment 4's wording** "no Verilator build of a large design" narrows the owner's exemption ("no Verilator build"). The agent's
  `simulate` builds small Verilator models in these runs; whether that counts as sim-only is for the owner to confirm.
- **Fixes made after the runs (code the runs did not use):** the run-directory race is closed by a launch lock (any task, arm or seed);
  H9's compaction note no longer points at `report_digest` where no role can call it (all of stage 2); `repair_records.py` skips
  infrastructure records; `build_error` keeps the compiler's first error. The retry still drops the usage of a discarded response, so
  cost is slightly undercounted (mostly A0); it is noted in `analysis.md`, not changed.
