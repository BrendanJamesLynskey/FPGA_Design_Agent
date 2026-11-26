# Brief 213: repair feedback (first failing check, failure ledger, fresh-stimulus regrade)

Status: code, tests and pre-registration done; the 18-run A/B (`order.tsv`, `run_ab.sh`) is running; its table is not yet here.
- [prereg.md](prereg.md): arms, designs, outcomes, power, stopping rules, written before the first scored run.
- [disagreement_classification.md](disagreement_classification.md): the 26 CVDP 215 runs where the agent's own check and the hidden tests disagree (diagnosis only; CVDP is not an evaluation).
- [sweep/regrade_sweep.jsonl](sweep/regrade_sweep.jsonl): the regrade over recorded accepted designs (applicability), by `sweep/regrade_sweep.py`.
- [designs/](designs): the three pilot specs. [runs/](runs): per-run records as they finish.
- Analysis tools: `tools/ab/` (adapter, paired numeric bootstrap; `ablate.py` and `table.py` copied from CVDP_RTL_Agent, MIT).
