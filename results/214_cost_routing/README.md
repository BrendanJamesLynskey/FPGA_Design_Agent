# Brief 214: cost routing by stage, escalation and k-way attempts

Status: complete for 13 of 18 planned runs; the report is [report.md](report.md). Result: no detectable effect on stage-2 visits, cost or pass rate (3 to 4 pairs); k-way cost more; the cheap tier did not repair lint failures; escalation did not fire in the stage-1 visit-limit loops (trigger bug found, reported). Defaults stay off.
- [prereg.md](prereg.md): arms, designs, outcomes, power, stopping rules, written before the first scored run.
- [order.tsv](order.tsv), [run_one.sh](run_one.sh), [run_ab.sh](run_ab.sh): the frozen run order and drivers. [analyse.py](analyse.py) builds [manifest.tsv](manifest.tsv) and [mechanism.md](mechanism.md).
- [ab_runs.csv](ab_runs.csv), [paired_analysis.txt](paired_analysis.txt): the paired analysis (`tools/ab/`).
- [runs/](runs): per-run records (summary.json, role_usage.jsonl, routing_events.jsonl, kway.jsonl, config.json, the delivered design files). [env_faults/](env_faults): two runs lost to a deleted knowledge checkout, re-run, not scored.
- [designs/](designs): the three pilot specs.

## Reproduce
`results/214_cost_routing/run_ab.sh [W T]` runs `order.tsv` (pinned Claude Code 2.1.321, knowledge repository at the pin in `agent/core/prompts_pin.json`, heavy slots); then `python3 results/214_cost_routing/analyse.py` and `tools/ab/adapter.py runs manifest.tsv > ab_runs.csv`. Fixture tests: `agent/tests/test_214_cost_routing.py`. Flags: `--routing on`, `--kway K` ([docs/role_models.md](../../docs/role_models.md#cost-routing-by-stage-and-k-way-attempts-brief-214)).

## Known gaps and limits
Own-check verdicts only; 3 designs, unbalanced arms (control 6, routing 3, routing_kway 4); sequential k-way attempts; plan-estimated cost on `claude_code`, no API spend; see [report.md](report.md).

## Records
`runs/<n>_<design>_k<k>_<arm>/`: summary.json, role_usage.jsonl, routing_events.jsonl, kway.jsonl (k-way arms), config.json, driver.log, meta.txt, RUN_ID.txt and the delivered design files. `ab_runs.csv`, `paired_analysis.txt`, `mechanism.md`: the analysis. `env_faults/`: the two re-run runs' logs.
