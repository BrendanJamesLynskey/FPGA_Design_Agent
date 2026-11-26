# Brief 213 pre-registration: repair feedback (R1 first failing check, R2 failure ledger, R3 fresh-stimulus regrade)

Written 2026-11-26 04:25:23 GMT (from `date`), before any scored agent run of this comparison. Changes after this point go in a dated addendum at the end, never in place.
Branch b213-repair-feedback. This is an **intervention on our own designs**, not a benchmark score: no CVDP problem is used as an evaluation (owner, 2026-11-25).
It changes three things at once (the three arms of the harness named below), so it is **exploratory** (brief 226 run-hygiene rule); the per-feature evidence
is how often each feature fired and what it showed, not a separate effect estimate.

## Arms (same agent commit, model, settings; only `--harness-arm` differs)
- **control**: `--harness-arm H1` (the CLI default: today's feedback: the raw simulator log tail, no ledger, no regrade).
- **treatment**: `--harness-arm H1,R1,R2,R3`.
- Common: `--harness claude_code --cc-model claude-sonnet-5-5 --cc-effort medium --stop-after 2 --verif-level V2 --board kr260 --review off --interview off --max-usd 12 --budget-scale 3.5`,
  Claude Code pinned at 2.1.321 (copy of the checked binary in `_scratch_213/bin`, auto-update off in `~/.claude/settings.json`), knowledge repo at the pin in
  `agent/core/prompts_pin.json` (5e2eab8), Icarus and Verilator as installed, cocotb 2.0.1.
- `--stop-after 2`: the interventions act on stage 2 (the repair loop); stages after it are out of scope of this comparison (constraints are brief 230's, stop diagnosis brief 234's).

## Designs and runs
- Three of the 209 pilot designs: p1_clkmeter, p2_bram_rom, p3_crc_engine, unchanged specs. **Chosen from a separate baseline** (the 209 pilot, API endpoint,
  unchanged agent): each reached a bitstream in at least 2 of 3 runs, so each sometimes passes. p4 to p6 are excluded: they were selected because they failed,
  and re-running a control on a failure-selected set regresses to the mean (226 section 4); their 224 loops (p6 "design standards", p5 constraints) are used only
  as ledger case studies, in the report, not in the comparison.
- **3 runs per design per arm: 18 runs.** Replicate k of a design in one arm is paired with replicate k in the other (design is the pairing factor).
- Run order: a seeded shuffle (`random.Random(213)`), recorded in `order.tsv`; run in that order, one at a time (the machine's slot rules; no concurrency
  between this comparison's runs).

## Outcomes (graded first)
1. **Primary: stage-2 visits to pass** (repair rounds at stage 2; a run that does not pass stage 2 counts the visit limit 6 plus one = 7).
2. Secondary: stage-2 pass (own gates), plan-estimated cost (USD) and wall time of the run, requirements evidenced at V2 (`verif_gates`), stop reason.
3. **Independent check: none available before the board visit** (the 209 host checks need the KR260 and are pending). So every pass here is an **own-check verdict**;
   the report gives the own verdict and marks the independent column "pending". The own verdict is not used to claim the designs are right.
   The regrade (R3) is the only independent signal in the treatment arm; it applies only where the bench drives the model through `step(inputs)` and the report says
   how many runs it applied to.
- Mechanism counts (treatment arm, from the run record's routing events): visits where R1 produced a digest, visits where the ledger was shown, regrade status per run.

## Power (stated in advance)
- The 209 baseline for these three designs gave stage-2 visits 2, 2, 3, 4, 2, 4, 6, 4, 3 (mean 3.3, SD 1.4). With 9 pairs and a per-pair difference SD near 1.7
  (two such runs), a 95% interval half-width is about 1.2 visits and the smallest effect detectable with 80% power at two-sided 0.05 is about **1.7 visits (about half the control
  mean)**. Smaller effects are not detectable; a null will be reported as **"no detectable effect", never "no effect"**.
- Pass rate is not informative here: the baseline passes stage 2 in 9 of 9; a pass-rate effect would need the treatment to break the agent (it can only show as a
  collapse). With 3 designs the smallest detectable change in a pass rate is far above 26 points (226 section 4: 6 designs at k = 3 give 23 to 26).
- So this comparison can show a **large** effect on repair rounds, or a **regression**. It cannot show a small gain. That is the honest ceiling of a 3-design A/B;
  a larger set (the 227 packages: 12 designs, 16 to 18 points on a pass rate) is the next step if the mechanism counts look worthwhile.

## Analysis
Paired bootstrap over the pairs (2000 draws, seed 0), exact sign test, per-design differences (`tools/ab/paired_numeric.py`; binary outcomes through the copied `tools/ab/ablate.py`).
Spread stated with every mean. No outcome is dropped after the fact; a run stopped by a plan limit, a rate limit, a refused slot or a CLI mismatch is recorded with its own
stop reason and **re-run**, never scored as a failure.

## Stopping rules
- Weekly usage at 75% (checked with `_handoff/usage_check.sh` at the start and about every 30 minutes): stop and report `BLOCKED:`.
- Per run: wall limit 3 hours; cost cap as above. One run above 20 USD plan estimate stops the series.
- Pace: one run at a time, each under `systemd-run --user --scope -p MemoryMax=7G nice -n 15` with a private `FDA_HEAVY_LOCK`, inside a slot from `take_heavy_slot.sh --env`.

## Regrade policy (decided from the sweep, stated here so the treatment arm is fixed)
The treatment arm runs the regrade at V2 in **report-only** mode (it never fails a gate), whatever the sweep shows; whether the default should block at any level is decided
from the sweep and written in the report, not applied to this comparison.
