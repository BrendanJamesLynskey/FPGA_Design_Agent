# results/f1b

The F1B cheap-model screen, run with the CVDP RTL Agent's harness in GitHub Actions (agent image `aa7404c`; L and D
dispatched from `aa7404c`, G from `main` `d9e9ca4`). Read [REPORT.md](REPORT.md) first. `CVDP_DIR=<clone of CVDP_RTL_Agent> bash results/f1b/tables.sh`
remakes every table below from the CSVs here, with the CVDP tools at `aa7404c`.

| File | What |
|---|---|
| [PREREG.md](PREREG.md) | The pre-registration (committed before the first scored run) and its five dated deviations |
| [REPORT.md](REPORT.md) | Results, the pick under the pre-set rule, the Claude Code endpoint result, spend, gaps |
| [candidates.md](candidates.md) | OpenRouter's list on 2026-10-31 for the candidates, and the models that passed the filter |
| `runs/*.csv` | Scored runs, one `collect.py` row per problem (`L1`, `D1`–`D3`, `G1`–`G2`; the file name ends in the Actions run id) |
| `void/*.csv` | The four void GLM runs (PREREG deviations 1, 2, 3, 5), in no primary table |
| `luna_old/*.csv` | CVDP M3c and M3d arm-A runs (luna on older images), for the drift check only |
| [paired_eval86.md](paired_eval86.md) | Primary: each candidate − luna on this image, `ablate.py --level 0.975` |
| [drift_eval86.md](drift_eval86.md), [vs_luna_old_eval86.md](vs_luna_old_eval86.md) | Luna on this image against the six older runs; candidates against them |
| [sensitivity_D1D2_eval86.md](sensitivity_D1D2_eval86.md), [sensitivity_G123_eval86.md](sensitivity_G123_eval86.md) | DeepSeek without D3 (its 402 stops); GLM with its void G3; not pre-registered |
| `reliability_rows.csv`, [reliability.md](reliability.md) | Per problem-run reliability counts from the traces (`tools/reliability.py`), and the table remade from them |
| `reliability_rows_void.csv`, [reliability_void.md](reliability_void.md) | The same for the void GLM runs, descriptive only |
| `pick.txt` | The model the rule picks |
| `tables.sh` | Remakes the tables |

Spend: [../spend_ledger.csv](../spend_ledger.csv).
