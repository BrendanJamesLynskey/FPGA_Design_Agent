# 239_stage2_diagnosis: why simple pilot designs failed stage 2, and the re-measure after the fixes

This folder holds brief 239's records. First, a census of every failing stage-2 gate event in the 36 earlier pilot runs (brief 213, and
brief 227 arms A and C), read from the runs' own checkpoints. Second, the verdict on the independent spec-only bench. Third, the 9-run
re-measure after the fixes (p1 clkmeter, p2 bram_rom, p3 crc_engine; 3 repeats each; stages 0 to 2; Claude Code harness; Sonnet 5.5),
pre-registered in `prereg.md` before the first run. The findings and the rule changes are in `report.md`.

## Records

| Path | What |
|---|---|
| `report.md` | the result, the census, the bench verdict, each rule change with its evidence, and the gaps |
| `prereg.md` | the pre-registration (stamped 2026-11-26 21:13 GMT), with a dated note on 7 cells re-run after an environment fault |
| `census.py`, `census_table.md`, `census_events.csv`, `last_blocker.csv`, `console_logs.md` | the census of the 36 earlier runs |
| `baseline_runs.csv` | the earlier runs used as the baseline |
| `arms/` | the 9 re-measure runs' records |
| `after/`, `after_runs.csv`, `comparison.txt`, `analyze.py` | the after census and the before/after comparison |
| `run_cell.sh`, `queue.sh` | how each cell was run (heavy slot, memory-capped scope, usage stop) |

## Reproduce

    python results/239_stage2_diagnosis/census.py
    bash results/239_stage2_diagnosis/queue.sh        # agent runs: plan-billed, needs the key file and a heavy slot
    python results/239_stage2_diagnosis/analyze.py

## Known gaps and limits

- n = 9 with one model and one harness. The baseline runs came from earlier code, so this is a before and after, not a controlled A/B.
- "Own pass" means the project's gates plus a model-written bench. Nothing here checks the built behaviour independently, and there is no board run.
- 7 of the 9 cells ran twice: the first attempts died at start-up because a shared prompt checkout was deleted. Only the second attempts count.
- A sixth change (primitive-name rule, `sim/` folder) was withdrawn before merge; see report.md, item 6.
- Brief 213's run folders are git-ignored, so its records are not on main.
