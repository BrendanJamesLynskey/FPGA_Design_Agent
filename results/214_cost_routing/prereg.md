# Brief 214 pre-registration: cost routing by stage, escalation, and k-way attempts

Written 2026-11-26 21:08:44 GMT (from `date`), before any scored run of this comparison. Changes after this point go in a dated addendum at the end, never in place.
Branch b214-cost-routing, code commit e58abe87 (agent/models/routing.py). This is an **intervention on our own designs**, not a benchmark score; no CVDP problem is used.

## Arms (same agent commit, model, settings; only the flags differ)
- **control**: `--harness-arm H1` (today's behaviour; every model call on Sonnet 5.5 medium).
- **routing**: `--harness-arm H1 --routing on`. Changes two things together (the table's cheap tier for a lint or design-standards repair, and escalation to
  the strong tier after the same failure on two visits), so it is **exploratory**; the per-feature evidence is the mechanism counts below.
- **routing_kway**: `--harness-arm H1 --routing on --kway 3`. Adds a third thing (k = 3 attempts on the third stage-2 visit); exploratory for the same reason.
- Common: `--harness claude_code --cc-model claude-sonnet-5-5 --cc-effort medium --stop-after 2 --verif-level V2 --board kr260 --review off --interview off --max-usd 12 --budget-scale 3.5`,
  Claude Code pinned at 2.1.321 (the binary and sha256 of brief 213's pin), knowledge repository at the pin (5e2eab8), Icarus and Verilator as installed. Provider: the Max plan
  (`claude_code`); cost is the plan estimate from provider-reported usage, never a model's number. No `anthropic_api` spend. Cheap tier = claude-haiku-5-5 low; strong = claude-opus-5-5 medium (Max plan only).

## Items and runs
- p1_clkmeter, p2_bram_rom, p3_crc_engine, the 213 pilot designs, unchanged specs. **Chosen because they sometimes pass** (a separate baseline: 213's control arm passed
  stage 2 in 4 of 9 runs, and the 209 pilot reached a bitstream in at least 2 of 3 runs each), never because they failed. p4 to p6 (selected for failing) are not re-run as controls
  (226 section 4: regression to the mean); their 224 loops stay ledger case studies.
- **2 replicates per design per arm: 18 runs** (3 designs x 2 x 3 arms). Order: a seeded shuffle (`random.Random(214)`) of the 18 cells, frozen in `order.tsv`; run in that
  order, one run at a time. The brief's "3 of the 11 development tasks" are not used: the budget (below) allows one set of 18 runs, and the pilot designs are the ones with a
  separate baseline.

## Outcomes (graded first; pass rate is secondary)
1. **Primary: stage-2 visits to pass** (a run that does not pass counts the visit limit 6 plus one = 7). Paired on (design, replicate) against control.
2. Secondary: plan-estimated cost in USD of the run (and **cost per passed design** = total cost of an arm / own passes), wall time, stage reached, repair rounds at stage 2, own stage-2 pass.
3. **Independent check: none before the board visit.** Every pass is an own-check verdict, labelled so; the regrade is not applicable to any pilot design (brief 213), so a k-way
   selection here rests on own gates only and is labelled `own_gates_only` in `kway.jsonl`.
4. **Mechanism counts** (the main evidence for the new features): escalated calls and what the next gate showed after each (same failure, changed failure, pass); calls and cost per tier;
   k-way rounds, candidates, their spread (gates passed, findings) and whether the kept candidate differed from candidate 1.

## Power (stated in advance)
- 6 paired runs per comparison. From brief 213's control (stage-2 visits mean 5.4, SD of paired differences about 2.2), the smallest effect detectable with 80% power at two-sided 0.05 is about
  **3 visits (more than half the control mean)**. On a pass rate with 3 designs at 2 runs the smallest detectable difference is above 50 points (226 section 4: 6 designs at 3 runs give 23 to 26).
  So this can show a **very large** effect or a regression, nothing smaller; a null will read **"no detectable effect", never "no effect"**, and defaults are recommended from the mechanism counts
  and the cost per passed design with that ceiling stated. A larger set (the 227 packages, 12 designs, 16 to 18 points) is the next step if the mechanism counts look worthwhile.

## Analysis
Paired bootstrap over pairs (2000 draws, seed 0), exact sign test, per-design differences (`tools/ab/paired_numeric.py`; binary outcomes through `tools/ab/ablate.py`), through `tools/ab/adapter.py`.
Spread with every mean. No outcome is dropped after the fact. A run stopped by a plan limit, a rate limit, a refused slot or a CLI mismatch is recorded with its own stop reason and **re-run**, never scored as a failure.

## Stopping rules
- Weekly usage: the brief says 75%; the caller of this brief set **92%** (weekly, all models; checked with `_handoff/usage_check.sh` before every run and about every 30 minutes): stop, record, hand back. The series started at 73%.
- Per run: wall limit 3 hours; `--max-usd 12`. Total cost against the brief's 25 USD cap applies to `anthropic_api` only; this series spends none.
- Pace: one run at a time (or two when `take_heavy_slot.sh` admits a second), each under `systemd-run --user --scope -p MemoryMax=7G nice -n 15` inside a slot from `take_heavy_slot.sh --env`.
- Never Opus or Fable through OpenRouter; Opus appears only as the strong tier on `claude_code`.
