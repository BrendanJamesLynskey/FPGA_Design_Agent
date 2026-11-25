# Brief 215: a public-benchmark baseline (CVDP code-generation sample)

What fraction of public CVDP code-generation problems does the FPGA agent's stages 0 to 2 (clarify, plan, RTL with its own simulation; no
Vivado, no board) solve when only CVDP's own hidden tests score it? One run of Claude Sonnet 5.5 (every role, Claude Code on the Max plan) on
a stratified sample of 50 of the 302 problems in CVDP's free non-agentic code-generation file. **Every row here is "public, contamination-exposed"
and a development figure.** Our hidden-test benchmark (`benchmark/`, `results/course/`) stays the primary score. Pre-registration:
[prereg.md](prereg.md) (written before the sample ran; four dated amendments at its end).

## Result, nulls first

- **Headline: 31 of 50 (62%, 95% Wilson 48% to 74%), counting a design written as rtl/x.sv where the task names rtl/x.v.** FPGA Force targets FPGA tools, which accept `.sv`, and the aim is a real, working design (owner decision, 2026-11-25 19:17). **This scoring was chosen after the results were seen.** Three runs wrote `rtl/<name>.sv` where the task names `rtl/<name>.v`; the same-stem `.sv` file stands in (text unchanged), and two of the three then pass.

Status: a one-off baseline. CVDP will not be used as an ongoing evaluation of FPGA Force. FPGA Force builds requirements with the user until they are unambiguous before building, which CVDP problems cannot represent, and many CVDP problems leave out facts their hidden tests check. CVDP problems may instead serve as a labelled test set for the agent's requirements reviewer.

- **Pre-registered strict score, kept beside it: 29 of 50 = 58%, 95% interval 44% to 71%** (Wilson); stratum-weighted 57% (44% to 71%, bootstrap). Strict scoring counts a file missing at the named path as empty. With n = 50 the intervals are about 27 points wide and overlap.
- **No category is established.** The per-category intervals (table below) all overlap. Code improvement (cid007) is 6 of 7 but **an empty file passes 2 of the 7 cid007
  problems** in this sample (null control: 2 of 50 pass, both cid007, `cvdp_copilot_scrambler_0018` and `cvdp_copilot_elevator_control_0033`); our run passes the first and fails the second. Without
  those two problems the strict figure is 28 of 48 = 58% (44% to 71%).
- **The agent's own check is a weak guide.** 35 of the 50 runs ended "done" (every stage 0 to 2 gate passed, including the agent's own bench); 16 of those 35 fail the hidden tests (19 pass).
  14 runs ended on the stage-2 visit limit (the repair loop did not converge to a passing gate set); 10 of those 14 pass the hidden tests anyway (the last RTL on disk is scored).
  One run stopped at stage 0 (a requirement the clarify stage rejected) and has no RTL: a fail. These counts are from [results_sample50.csv](results_sample50.csv).
- **The 5-problem calibration** (separate, not pooled): 4 of 5 pass ([results_calibration.csv](results_calibration.csv)). Its first attempt on one problem failed because the adapter did not say that
  the hidden testbench compiles only the named file (the agent split the design over three files); the adapter preface was fixed and the problem re-run (amendment 1).
- **VerilogEval v2 was not run**: calibration cost about 0.2% of a week per problem (1% resolution), so 156 problems is about 31%, over the 5% rule.

| category (first CVDP category) | n | strict pass | rate | 95% interval | with the .sv stand-in | rate | 95% interval |
|---|---|---|---|---|---|---|---|
| cid002 RTL code completion | 14 | 6 | 43% | 21% to 67% | 7 | 50% | 27% to 73% |
| cid003 spec to RTL | 12 | 7 | 58% | 32% to 81% | 8 | 67% | 39% to 86% |
| cid004 RTL modification | 10 | 7 | 70% | 40% to 89% | 7 | 70% | 40% to 89% |
| cid007 code improvement | 7 | 6 | 86% | 49% to 97% | 6 | 86% | 49% to 97% |
| cid016 bug fixing | 7 | 3 | 43% | 16% to 75% | 3 | 43% | 16% to 75% |
| all, pooled | 50 | 29 | 58% | 44% to 71% | 31 | 62% | 48% to 74% |

More cuts (null control excluded, calibration) are in [summary_tables.md](summary_tables.md). Per-problem rows: [results_sample50.csv](results_sample50.csv).

## Published figures beside ours

Not like for like: other systems report mean pass@1 over several runs, on their own subsets and agents, mostly self-reported. Ours is one run per problem, 50 problems, stages 0 to 2 only,
no repair beyond the agent's own loop, no retries. None of the rows below was re-run by us.

| system | figure | what it was run on | source | self-reported? |
|---|---|---|---|---|
| this brief (FPGA agent, Sonnet 5.5, stages 0-2) | 58% strict, 62% variant (n = 50) | 50 of the 302 non-agentic, no-commercial code-generation problems | this folder | n/a |
| ChipCraftBrain | 94.7% mean pass@1 (286/302, 3 runs) | the 302-problem non-agentic subset spanning five categories (we believe the same file) | arXiv 2604.19856, abstract read 2026-11-25 | yes, single author, no code seen |
| CVDP paper | no model above 34% pass@1 on code generation (June 2025 models) | all code-generation problems, agentic and non-agentic | arXiv 2506.14074, abstract read 2026-11-25 | the benchmark authors |
| ACE-RTL | up to +41.02% pass rate over 14 baselines | CVDP (no absolute figure on the abstract page) | arXiv 2602.10218, abstract read 2026-11-25 | yes |
| ACE-RTL on a vendor blog | 97.1% mean over nine categories (Nemotron 3 Ultra) | CVDP | NVIDIA blog, Jul 2026, as quoted in `research/211_related_agents_landscape.md` (blog not re-read) | vendor numbers |
| our earlier CVDP RTL Agent (a different agent) | Claude Code on the Max plan: Opus 5.5 73.3%, Sonnet 5.5 69.8% | the 86 development problems of the free **agentic** split | `CVDP_RTL_Agent/docs/reports/claude_code_ladder.md` (README summary read) | ours |

The gap to the 94.7% and 97.1% rows is large. Reasons we can name without testing them: our stages 0 to 2 are built for board designs and write a standalone module through that machinery; V1 verification only;
one sample; the flow's own simulate and design-standards gates left 14 runs unfinished at the stage-2 visit limit (simulate gate 11, simulate and standards 2, standards 1; no run hit the 60-minute wall cap). We have not measured how much each contributes.

## Cost and time

- **Cost (provider-reported): none.** Claude Code on the plan reports no cost. The agent's own estimate from token counts is in each run's `role_usage.jsonl` (`plan_cost_estimate_usd`): the 50 runs sum to $60.81
  (mean $1.22, largest $2.84), 50.2 million tokens; the 5 calibration runs $6.67. These are estimates, not billing.
- **Weekly usage (plan meter, whole account, 1% resolution): 35% before the calibration, 36% before the sample, 42% after it.** Other sessions (the KR260 pilot, brief 210) ran in the same period,
  so about 6 points for the 50 runs is an upper bound for this brief, not a measurement of it.
- **Wall time:** the sample ran 3 at a time from 13:35 to 17:51 on 2026-11-25 (4 h 16 min elapsed); summed per-run wall 32,748 s = 9.1 h (mean 655 s, longest 1,030 s); calibration 3,355 s summed.
  Scoring 50 problems in the CVDP sim image takes a few minutes with 3 threads.

## Records

- [prereg.md](prereg.md): method, pins, amendments. [sample50_ids.txt](sample50_ids.txt), [calib_ids.txt](calib_ids.txt): the problem ids (the problem texts are not committed).
- [results_sample50.csv](results_sample50.csv), [results_calibration.csv](results_calibration.csv): one row per problem (category, strict and variant result, stop reason, stage-2 visits, wall, cost estimate, tokens, weekly readings).
- [records/sample50/](records/sample50/), [records/calibration/](records/calibration/), [records/calibration_attempt1/](records/calibration_attempt1/): per run `rtl/` (the delivered files, our output), `role_usage.jsonl` (per role and visit),
  `summary.json` (a whitelisted subset of the run summary: the full one carries private prompt text), `driver.log` (dated launch, exit and usage lines).
- [scores/](scores/): the harness's pass or fail per problem (strict, extension-mapped, null control, calibration). [harness/](harness/): the CVDP harness `report.json` for each scoring run.
- Code: [tools/public_bench/](../../tools/public_bench/): `cvdp_adapter.py` (sample, prepare, collect, score), `run_one.sh`, `queue.sh`, `records.py`, `summarise.py`.

## Reproduce

Pins: CVDP harness `NVlabs/cvdp_benchmark` at `8e894cf74414ab1eaea1e2b4e80a02f123df07b6` (Apache-2.0); dataset `nvidia/cvdp-benchmark-dataset` at `5b807d945f6a99aa645f7e43a64a2115e281b4bf`, file
`cvdp_v1.1.0_nonagentic_code_generation_no_commercial.jsonl` (CC BY 4.0 for non-code, Apache-2.0 for code; not redistributed here); simulation image built from that harness commit (`nvidia/cvdp-sim:v1.0.0`);
Claude Code 2.1.321 (SHA-256 `426c33815ca6645a772f722fbff10dbf2cbdb124a8aeab733c1365dbf8bbf61f`, auto-update off); knowledge repo at `6185830`; agent code this branch.

1. Fetch the harness at the pin into a scratch folder, make a throw-away venv with its `requirements.txt`, copy `.env.example` to `.env` and add `OSS_SIM_IMAGE=nvidia/cvdp-sim:v1.0.0`; fetch the dataset file.
2. Sample: `python3 tools/public_bench/cvdp_adapter.py sample --data <file> --seed 215 --per-category cid002=1,cid003=1,cid004=1,cid007=1,cid016=1 > calib_ids.txt`, then
   `... sample --seed 20261125 --per-category cid002=14,cid003=12,cid004=10,cid007=7,cid016=7 --exclude calib_ids.txt > sample50_ids.txt` (they equal the committed id files).
3. Run: `CVDP_DATA=<file> tools/public_bench/run_one.sh <problem id> <tag>` per problem (it prepares the spec, checks version, usage, load and memory, and runs
   `python -m agent run <spec.md> --stop-after 2 --no-shell --verif-level V1 --harness claude_code --cc-model claude-sonnet-5-5 --cc-effort medium --max-usd 3 --budget-scale 2 --name <tag>`); `queue.sh` runs a list. Needs the repo `.env` access key.
4. Score: `cvdp_adapter.py collect --data <file> --out ds.jsonl --run <id>=<design dir> ...` (add `--ext-map` for the variant), then `cvdp_adapter.py score --harness <cvdp dir> --python <venv python> --dataset ds.jsonl --work <dir>`.
   A rescoring of the variant gave identical results. Tables: `tools/public_bench/summarise.py` and `records.py`.

## Known gaps and limits

- **Contamination.** CVDP is public; Sonnet 5.5 may have seen the problems. The knowledge bank is documentation-derived and was not built from CVDP, but its generic layer comes from a pack written for the earlier CVDP project
  (which, per that project's notes, shares cocotb boilerplate with the benchmark); we have not audited the overlap. Every figure here is development-grade for that reason.
- **Small sample, one run each.** 50 problems, one run per problem, no repeated runs: an interval of about plus or minus 13 points overall and 20 to 30 per category. Run-to-run variation was not measured.
- **Adapter choices matter.** The spec preface (standalone module, keep names, single file) is ours; a different preface could move the rate. The calibration showed one preface effect. The `.v` against `.sv` naming effect is 2 problems.
- **Verification level V1**, not the default V3 (V3 needs a Verilator coverage run and a mutation run, which need a heavy slot). Stages 0 to 2 only: no synthesis, no hardware, none of the flow's later gates.
- **Hidden tests are CVDP's, with known issues.** The null control shows 2 of 7 cid007 problems pass with an empty file; we have not checked whether other problems accept wrong designs, or reject right ones (the earlier CVDP project found problems whose hidden tests read names the task never gives).
- **Costs are estimates** (no provider-reported cost on the plan); the weekly meter is account-wide and coarse.
- **Not run:** VerilogEval v2 (cost rule), the agentic and comprehension files, the files that need Cadence Xcelium, other models, pass@k. The sample covers five categories: it says nothing about verification-writing categories.
- **No claim about the agent's board flow**: the stage machine was used for standalone modules with the shell and board parts switched off (`--no-shell`); it still wrote board-planning files that the scoring ignores.

## Course impact

None: no new measured fact about the flow, and held-out benchmark details never go in the course.
