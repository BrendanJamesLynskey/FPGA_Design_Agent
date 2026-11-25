# Brief 215 pre-registration: public-benchmark baseline (CVDP non-agentic sample, VerilogEval v2)

Written 2026-11-25 12:52 (clock) by the brief 215 executor (Sonnet sub-agent), before any run that is scored. All rows are labelled
"public, contamination-exposed". Our hidden-test benchmark stays the primary score.

## Question

What fraction of public CVDP code-generation problems (no commercial tools, non-agentic file) does the FPGA agent's stages 0 to 2
(clarify, plan, RTL plus own simulation; no Vivado) solve when scored only by CVDP's own hidden tests, and how does that sit beside
published figures? No hypothesis is tested; this is a baseline with intervals.

## Pins

- CVDP harness: NVlabs/cvdp_benchmark at 8e894cf74414ab1eaea1e2b4e80a02f123df07b6 (Apache-2.0), run locally in Docker (image
  ghcr.io/brendanjameslynskey/cvdp-sim:8e894cf, built from that commit by the CVDP RTL Agent repo, already on this machine; tagged
  nvidia/cvdp-sim:v1.0.0; no pulls). Harness Python deps in a throw-away venv (not the repo venv).
- CVDP dataset: nvidia/cvdp-benchmark-dataset at 5b807d945f6a99aa645f7e43a64a2115e281b4bf, file
  cvdp_v1.1.0_nonagentic_code_generation_no_commercial.jsonl (302 problems: cid002 94, cid003 78, cid004 55, cid007 40, cid016 35).
  Licence: CC BY 4.0 (non-code) and Apache-2.0 (code); the problem files are fetched at run time and are not committed (ids and our outputs only).
- Claude Code 2.1.321 (copy in _scratch_215/bin/claude, SHA-256 426c3381...bf61f), auto-update off (DISABLE_AUTOUPDATER=1 in settings), checked before every launch.
- Knowledge bank: private repo at 6185830 (the pin in knowledge/PACKS.md). Agent code: branch b215-public-benchmarks from origin/main.
- Agent: python -m agent run spec.md --stop-after 2 --no-shell --verif-level V1 --harness claude_code --cc-model claude-sonnet-5-5
  --cc-effort medium --max-usd 3 --budget-scale 2 (every role Sonnet 5.5, plan-billed, no OpenRouter). Wall cap 60 minutes per run.
  V1 (not V3) because V3 adds a Verilator coverage run and a mutation run (heavy slot); this lowers the strength of the agent's own checking.

## Method

1. Adapter (tools/public_bench/cvdp_adapter.py): spec.md = a fixed preface (standalone module task, keep names, no board) + the
   problem's prompt + any provided files + the file path(s) to deliver. Provided files also go into the design's data/.
2. The agent's own bench never counts. After the run, the delivered file(s) are copied into the problem's output context and the CVDP
   harness scores them (golden mode: run_benchmark.py without -l, hidden cocotb tests in the sim image). A missing file counts as empty
   and fails. Pass = the harness reports the problem passed (all its tests). Nothing a model writes produces a score.
3. Calibration: 5 problems, one per category, seed 215 (drawn first, excluded from the sample). Recorded and reported separately; never pooled
   with the 50, because the adapter may change after seeing them.
4. Sample: 50 problems from the other 297, stratified by first category, seed 20261125 (python random.Random(seed).sample on the sorted
   id list per category): cid002 14, cid003 12, cid004 10, cid007 7, cid016 7 (proportional to 94:78:55:40:35, rounded). One run per problem.
5. Intervals: Wilson 95% per category and overall (n small: stated). Overall also reported as a stratum-weighted rate (weights = the
   category's share of the 302) with a stratified bootstrap 95% interval (10,000 resamples, seed 215).
6. VerilogEval v2 (156 Human problems): run in full only if the calibration's mean weekly usage per problem times 156 is under 5% of a
   week (weekly percent read from the plan's own usage page, 1% resolution, so the estimate is coarse). Otherwise not run, and the report says so
   with the estimate. VerilogEval is MIT licensed; its own testbenches score.
7. Stop rules: stop with BLOCKED at 60% weekly usage (checked before every launch, about every 30 minutes by the driver); one run at a time;
   launches only while load is under 6 and more than 12 GB is available. A run that ends without RTL is scored as a fail with its stop reason shown (not dropped); a run that
   cannot start (PREFLIGHT_FAIL, resources) is reported as NOT RUN and retried.
8. Not done: agentic split, comprehension file, commercial-tool files (need Xcelium), pass@k, repeated runs, other models, no repair rounds beyond the agent's own.
9. Cost: weekly-usage percentage deltas (coarse) plus the agent's own plan-cost estimate from each run's role_usage.jsonl (an estimate, not provider-reported); wall time.

## Amendments

1. 2026-11-25 13:04, before any scored run: up to two agent runs at once (not one), each preflight-checked for load under 6 and more than 12 GB available. Also: the adapter preface was changed after calibration attempt 1 to say the hidden testbench compiles only the named file(s), so submodules must be inside them (attempt 1 split a design over three files and the harness build step failed); calibration attempt 1 is kept as a record, not counted.
2. 2026-11-25 15:24, during the sample (19 of 50 done, load under 2): up to three agent runs at once, because the machine was idle; the same preflight (load under 6, more than 12 GB available) applies to every launch. No other change.
3. 2026-11-25 18:02, after the 50 runs finished and were scored once strictly (29 of 50): 3 runs (a 4th delivered no RTL at all) delivered the module as `rtl/<name>.sv` where the task names `rtl/<name>.v` (the flow writes SystemVerilog), so the strict rule scored them as an empty file. A second scoring, **post hoc and labelled as such**, lets the same-stem `.sv` file stand in for a named `.v` file (`cvdp_adapter.py collect --ext-map`; text unchanged). The pre-registered strict figure stays the headline; both are reported side by side.
4. 2026-11-25 18:02, also after the runs: a null control (an empty file for each of the 50) was scored with the same harness, to show the floor. VerilogEval decision (rule 6): the calibration's usage reading rose from 35% to 36% of the week for 5 problems (about 0.2% per problem, at 1% resolution and with other sessions running); times 156 is about 31%, far over 5%, so VerilogEval v2 is **not run** (no partial run was substituted).
5. 2026-11-25 19:17, owner decision: the headline is the same-stem count, 31 of 50 (62%, 95% Wilson 48% to 74%), counting a design written as rtl/x.sv where the task names rtl/x.v, because FPGA Force targets FPGA tools, which accept .sv, and the aim is a real working design. This scoring was chosen after the results were seen. The pre-registered strict score, 29 of 50 (58%, 44% to 71%), stays in the README beside it.
