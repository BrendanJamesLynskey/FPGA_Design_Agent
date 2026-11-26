# Brief 213: repair feedback (first failing check, failure ledger, fresh-stimulus regrade)

Status: complete; the report is [report.md](report.md) (also in _handoff/fpga_agent/reports). A/B: no detectable effect on stage-2 visits, pass rate, cost or wall time (n = 9 pairs); regrade report-only.
- [prereg.md](prereg.md): arms, designs, outcomes, power, stopping rules, written before the first scored run.
- [disagreement_classification.md](disagreement_classification.md): the 26 CVDP 215 runs where the agent's own check and the hidden tests disagree (diagnosis only; CVDP is not an evaluation).
- [sweep/regrade_sweep.jsonl](sweep/regrade_sweep.jsonl): the regrade over recorded accepted designs (applicability), by `sweep/regrade_sweep.py`.
- [report.md](report.md), [paired_analysis.txt](paired_analysis.txt), [ab_runs.csv](ab_runs.csv): the A/B.
- [designs/](designs): the three pilot specs. [runs/](runs): per-run records as they finish.
- Analysis tools: `tools/ab/` (adapter, paired numeric bootstrap; `ablate.py` and `table.py` copied from CVDP_RTL_Agent, MIT).

## Reproduce
`results/213_repair_feedback/run_ab.sh` runs `order.tsv` (needs the pinned Claude Code 2.1.321 in `_scratch_213/bin`, the knowledge repo at the pin in `agent/core/prompts_pin.json`, heavy slots); `tools/ab/adapter.py runs manifest.tsv > ab_runs.csv`; `tools/ab/paired_numeric.py ab_runs.csv --base control --arm treatment --col stage2_visits`. Sweep: `sweep/regrade_sweep.py`. Fixture tests: `agent/tests/test_213_repair_feedback.py`.

## Known gaps and limits
Exploratory bundle on 3 designs x 3 replicates (smallest detectable effect about 1.7 stage-2 visits); own-check verdicts only; R1 snapshot reported "Simulator shut down prematurely" in 3 of its 4 firings; the regrade was not applicable to any pilot design (benches use register calls); see [report.md](report.md).

## Records
`runs/<n>_<design>_k<k>_<arm>/`: summary.json, role_usage.jsonl, routing_events.jsonl, config.json, driver.log, meta.txt, RUN_ID.txt and the delivered design files (rtl, tests, verif, model.py, spec.yaml). `ab_runs.csv` and `paired_analysis.txt`: the analysis; `sweep/regrade_sweep.jsonl`: the regrade sweep.
