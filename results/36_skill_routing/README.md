# 36_skill_routing: skill retrieval and a small end-to-end routing test

This folder holds the pre-registered measurements of brief 36 (skill routing for the agent): retrieval of the labelled
skills over 12 development tasks by ten ways of ranking them, and a small end-to-end test of 3 tasks with skill routing
off against the router. Only development-split tasks were used, against a catalogue of 157 skills for the Nexys A7-100T.

## Records

| File | What |
|---|---|
| `PREREG.md` | the pre-registration, written before any measurement: arms, metrics, comparisons, the end-to-end design |
| `labels.yaml` | the 12 labelled development tasks and which skills each needs |
| `measure.py` | retrieval and context measurement (PREREG sections 1 and 2) |
| `retrieval.json`, `retrieval.md` | recall@3, @6, @10 and MRR per arm and per task; arms marked * were added after the pre-registered arms were read |
| `e2e.py`, `e2e_runs.jsonl`, `e2e.md` | the end-to-end driver, its run records and the table it writes |
| `scores/<run>.json` | the hidden-bench score of each of the six end-to-end runs |

## Reproduce

    FDA_KNOWLEDGE=<bank> PYTHONPATH=<fastembed dir> python3 results/36_skill_routing/measure.py [--with-model]
    python3 results/36_skill_routing/e2e.py run
    python3 results/36_skill_routing/e2e.py table

`measure.py` needs the private knowledge bank with its vectors and fastembed, so it cannot be rerun from the public
repository alone; it is deterministic except arm R2 (`--with-model`, one paid model call per task). `e2e.py run` makes paid
agent runs (each role on `openai/gpt-6-luna` through OpenRouter, up to USD 0.60 a run, one at a time under a heavy slot; no
Vivado) and is not repeatable to the same result; `e2e.py table` rebuilds `e2e.md` from `e2e_runs.jsonl`.

## Known gaps and limits

- No ranked arm beat the arm in use today on recall@6 (see `retrieval.md`); the post-hoc arms (*) were chosen after reading the pre-registered arms and are biased.
- Twelve tasks: no difference is called significant; the per-task rows are the evidence.
- The end-to-end test is 3 pairs of one run each, not the 3 seeds per task and arm that `PREREG.md` planned. No run in either arm passed its hidden bench, so it shows that the path works, not a difference between arms.
- The router arm's roles hardly used the new tools (one `skill_index` call and three `load_skill(name=...)` calls in three runs); token totals are dominated by long repair visits and say nothing about the shortlist's own cost.
- Two `t1_debounce_bank` runs were scored after the run (`e2e.py adopt`) because the first driver's scorer had two bugs; the runs themselves were not repeated.
- Classifier cost and run costs are provider-reported; the vectors were computed on one PC and the bank is private.
