# Brief 42 harness arms, round 1 (written by driver.py table)

Dev split and the two brief 24 drills, deepagents, every role on openai/gpt-6-luna, `--stop-after 2 --verif-level V1`, per-run cap USD 0.75, hard wall limit 5400 s. Score = the task's hidden bench on the run's rtl/. Cost and tokens are provider-reported. One row per run.

| Task | Seed | Arm | Run | Wall s | Hard limit | Stage-2 visits | Stage-2 gates | Hidden bench | Sim hangs | Tokens | Cost USD | Stop |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| t1_gray_stepper | 1 | A0 | 20261111-133042-b94d | 3230.4 |  | 4 | fail | fail 0/9 | 0 | 16490657 | 0.318617 | budget: run turns limit 300 reached (300) |
| t1_gray_stepper | 1 | H1 | 20261111-114827-883c | 2695.6 |  | 3 | pass | fail 0/9 | 0 | 7755869 | 0.22324 | done |
| t1_gray_stepper | 1 | H2 | 20261111-123329-0fc7 | 1443.1 |  | None | fail | fail 0/0 | 0 | 5042520 | 0.12435 | None |
| t1_gray_stepper | 1 | H2 | 20261111-143201-9301 | 3361.9 |  | 5 | fail | fail 0/9 | 0 | 13998755 | 0.296983 | budget: run turns limit 300 reached (300) |
| t1_gray_stepper | 1 | H9 | 20261111-125733-2f09 | 1983.3 |  | None | fail | fail 0/9 | None | 5195144 | 0.13418 | None |
| t1_gray_stepper | 1 | H9 | 20261111-143201-f218 | 3151.1 |  | 6 | fail | fail 0/0 | 0 | 9332423 | 0.241995 | budget: run turns limit 300 reached (300) |
| d24_registered_outputs | 1 | A0 | 20261111-130544-dead | 1655.9 |  | None | fail | pass 3/3 | 0 | 4073524 | 0.11514 | None |
| d24_registered_outputs | 1 | A0 | 20261111-152440-577f | 5400.1 | yes | None | fail | fail 0/3 | 1 | 9626105 | 0.243002 | None |
| d24_registered_outputs | 1 | H1 | 20261111-133325-8ead | 1077.6 |  | 1 | pass | pass 3/3 | 0 | 2712645 | 0.091547 | done |
| d24_registered_outputs | 1 | H2 | 20261111-114918-0e22 | 615.7 |  | 1 | pass | pass 3/3 | 0 | 1646856 | 0.052846 | done |
| d24_registered_outputs | 1 | H9 | 20261111-115938-23d6 | 3961.8 |  | 5 | fail | pass 3/3 | 0 | 11972430 | 0.321937 | budget: run turns limit 300 reached (300) |
| t1_debounce_bank | 1 | A0 | 20261111-152810-3e80 | 3099.0 |  | 6 | pass | fail 0/9 | 0 | 7844545 | 0.234328 | done |
| t1_debounce_bank | 1 | H1 | 20261111-161954-554a | 2815.8 |  | 6 | pass | fail 0/9 | 0 | 8289971 | 0.221426 | done |
| t1_debounce_bank | 1 | H2 | 20261111-165443-736c | 2300.9 |  | 7 | fail | fail 0/9 | 0 | 13699462 | 0.272975 | stage 2 visited more than 6 times |
| t1_debounce_bank | 1 | H9 | 20261111-135127-e4fa | 899.7 |  | 2 | pass | fail 0/9 | 0 | 2274998 | 0.064199 | done |
| d24_no_extra_latency | 1 | A0 | 20261111-170658-3b19 | 3006.4 |  | 6 | fail | pass 3/3 | 0 | 18724335 | 0.349752 | budget: run turns limit 300 reached (300) |
| d24_no_extra_latency | 1 | H1 | 20261111-173309-3965 | 1655.7 |  | 7 | fail | pass 3/3 | 0 | 5624916 | 0.166672 | stage 2 visited more than 6 times |
| d24_no_extra_latency | 1 | H2 | 20261111-175709-6742 | 1152.6 |  | 7 | fail | pass 3/3 | 0 | 3022706 | 0.101129 | stage 2 visited more than 6 times |
| d24_no_extra_latency | 1 | H9 | 20261111-180050-d6c4 | 1378.9 |  | 7 | fail | pass 3/3 | 0 | 4623216 | 0.119352 | stage 2 visited more than 6 times |
