# results/p0: open-weight base screen

Brief P0 (04g) screened two open-weight code models as bases for later fine-tuning, by running each once through
the CVDP RTL Agent's harness on the 86 M3b problems in GitHub Actions through OpenRouter. The result is inconclusive: every run
was stopped by the per-run spend guard, so no base is recommended. Read [REPORT.md](REPORT.md) first.

## Records

| File | What |
|---|---|
| [PREREG.md](PREREG.md) | The pre-registration, written before the first scored run, with its dated deviations, the candidates, licences and the memory-fit estimates |
| [REPORT.md](REPORT.md) | The outcome, the runs, spend and its reconciliation, method notes and gaps |
| [SUMMARY.md](SUMMARY.md) | The descriptive table made from the CSVs by `summarise.py` |
| `runs/*.csv` | One `collect.py` row per problem for each of the three runs (all void: guard-truncated) |
| `summarise.py` | Makes SUMMARY.md from the CSVs |

## Reproduce

- The summary table from the committed CSVs (no model, no tools): `python3 results/p0/summarise.py`.
- The runs were dispatched in GitHub Actions on the CVDP RTL Agent at the commit named in REPORT.md and paid through OpenRouter (`data_collection: deny`). They are not repeatable exactly, and the dispatch commands are not recorded in this folder.

## Known gaps and limits

- Every run is void under the pre-registered guard rule (`run_budget_exhausted` on 42 to 65 of 86 problems), so the pass counts are descriptive only and no paired comparison with the reference model was made.
- One run per candidate, and only one candidate pair; a valid screen needs larger guards than the brief's cap allowed.
- The sweep does not record quantisation, so the served precision is unknown.
- Reliability measures were not computed and the traces are not committed.
- Memory-fit figures in the pre-registration are arithmetic estimates, not measurements.
