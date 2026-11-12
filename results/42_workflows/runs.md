# Brief 42 harness arms, round 1 (written by driver.py table)

Dev split and the two brief 24 drills, deepagents, every role on openai/gpt-6-luna, `--stop-after 2 --verif-level V1`, per-run cap USD 0.75, hard wall limit 5400 s. Score = the task's hidden bench on the run's rtl/. Cost and tokens are provider-reported. One row per run.

| Task | Seed | Arm | Run | Wall s | Hard limit | Stage-2 visits | Stage-2 gates | Hidden bench | Sim hangs | Tokens | Cost USD | Stop |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| t1_gray_stepper | 1 | A0 | 20261111-133042-b94d | 3230.4 |  | 4 | fail | fail 0/9 | 0 | 16490657 | 0.318617 | budget: run turns limit 300 reached (300) |
| t1_gray_stepper | 1 | H1 | 20261111-114827-883c | 2695.6 |  | 3 | pass | fail 0/9 | 0 | 7755869 | 0.22324 | done |
| t1_gray_stepper | 1 | H2 | 20261111-123329-0fc7 | 1443.1 |  | None | fail | fail 0/0 | 0 | 5042520 | 0.12435 | None |
| t1_gray_stepper | 1 | H2 | 20261111-143201-9301 | 3361.9 |  | 5 | fail | fail 0/9 | 0 | 13998755 | 0.296983 | budget: run turns limit 300 reached (300) |
| t1_gray_stepper | 1 | H9 | 20261111-125733-2f09 | 1983.3 |  | None | fail | fail 0/9 | 0 | 5195144 | 0.13418 | None |
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
| t1_gray_stepper | 2 | A0 | 20261111-194038-37df | 1465.7 |  | 7 | fail | fail 0/9 | 0 | 6080585 | 0.148143 | stage 2 visited more than 6 times |
| t1_gray_stepper | 2 | H1 | 20261111-194821-dd59 | 1973.3 |  | 7 | fail | fail 0/9 | 0 | 7400363 | 0.208352 | stage 2 visited more than 6 times |
| t1_gray_stepper | 2 | H2 | 20261111-185423-e3c6 | 3230.8 |  | 5 | fail | fail 0/9 | 0 | 15168360 | 0.309792 | budget: run turns limit 300 reached (300) |
| t1_gray_stepper | 2 | H9 | 20261111-185443-2b3a | 2747.6 |  | 5 | fail | fail 0/9 | 0 | 13112430 | 0.290518 | budget: run turns limit 300 reached (300) |
| d24_registered_outputs | 2 | A0 | 20261111-202122-50db | 1206.6 |  | 2 | pass | pass 3/3 | 0 | 2890214 | 0.08857 | done |
| d24_registered_outputs | 2 | H1 | 20261111-202200-c6c2 | 907.3 |  | 1 | pass | pass 3/3 | 0 | 3005895 | 0.086695 | done |
| d24_registered_outputs | 2 | H2 | 20261111-203711-4600 | 766.5 |  | 1 | pass | pass 3/3 | 0 | 2793135 | 0.081959 | done |
| d24_registered_outputs | 2 | H9 | 20261111-200510-9030 | 1005.0 |  | 1 | pass | pass 3/3 | 0 | 3134259 | 0.080277 | done |
| t1_debounce_bank | 2 | A0 | 20261111-204133-2d74 | 2815.7 |  | 6 | fail | fail 0/0 | 0 | 11936706 | 0.263134 | budget: run turns limit 300 reached (300) |
| t1_debounce_bank | 2 | H1 | 20261111-205002-51be | 1069.1 |  | 3 | pass | fail 0/9 | 0 | 3222022 | 0.101993 | done |
| t1_debounce_bank | 2 | H2 | 20261111-210759-ed95 | 5400.1 | yes | None | fail | fail 0/9 | 4 | 3130979 | 0.080773 | None |
| t1_debounce_bank | 2 | H9 | 20261111-212829-e3be | 3732.8 |  | 5 | fail | fail 0/9 | 0 | 12571844 | 0.333479 | budget: run turns limit 300 reached (300) |
| d24_no_extra_latency | 2 | A0 | 20261111-231913-4d9a | 2422.8 |  | 6 | fail | pass 3/3 | 0 | 13286935 | 0.301874 | budget: run turns limit 300 reached (300) |
| d24_no_extra_latency | 2 | H1 | 20261111-223047-9fd7 | 1955.0 |  | 7 | fail | fail 2/3 | 0 | 4669047 | 0.149826 | stage 2 visited more than 6 times |
| d24_no_extra_latency | 2 | H2 | 20261111-223804-f3ff | 2463.7 |  | 4 | fail | pass 3/3 | 0 | 19692045 | 0.354074 | budget: run turns limit 300 reached (300) |
| d24_no_extra_latency | 2 | H9 | 20261111-230326-deba | 2649.8 |  | 5 | fail | pass 3/3 | 0 | 13146728 | 0.253123 | budget: run turns limit 300 reached (300) |
| t1_gray_stepper | 3 | A0 | 20261111-235940-3307 | 2718.9 |  | 5 | fail | fail 0/9 | 0 | 17209300 | 0.349279 | budget: run turns limit 300 reached (300) |
| t1_gray_stepper | 3 | H1 | 20261112-003418-29b0 | 2393.3 |  | 7 | fail | fail 0/9 | 0 | 6638127 | 0.186349 | stage 2 visited more than 6 times |
| t1_gray_stepper | 3 | H2 | 20261112-004507-eb88 | 4085.2 |  | 4 | fail | fail 0/9 | 0 | 18957198 | 0.361545 | budget: run turns limit 300 reached (300) |
| t1_gray_stepper | 3 | H9 | 20261111-234743-6329 | 2590.5 |  | 6 | fail | fail 1/9 | 0 | 11416968 | 0.267051 | budget: run turns limit 300 reached (300) |
| d24_registered_outputs | 3 | A0 | 20261112-011521-f9cb | 2554.2 |  | 6 | fail | pass 3/3 | 0 | 20798083 | 0.374783 | budget: run turns limit 300 reached (300) |
| d24_registered_outputs | 3 | H1 | 20261112-015322-80a5 | 3162.8 |  | 4 | fail | pass 3/3 | 0 | 8646553 | 0.247438 | budget: run turns limit 300 reached (300) |
| d24_registered_outputs | 3 | H2 | 20261112-015801-2e09 | 2446.0 |  | 6 | fail | pass 3/3 | 0 | 17722097 | 0.331002 | budget: run turns limit 300 reached (300) |
| d24_registered_outputs | 3 | H9 | 20261112-024353-23a9 | 1513.5 |  | 7 | fail | pass 3/3 | 0 | 5303219 | 0.148758 | stage 2 visited more than 6 times |
| t1_debounce_bank | 3 | A0 | 20261112-034506-c533 | 2108.1 |  | 6 | fail | fail 0/9 | 0 | 8099307 | 0.212788 | budget: run turns limit 300 reached (300) |
| t1_debounce_bank | 3 | H1 | 20261112-024710-7ec6 | 1289.2 |  | 7 | fail | fail 0/9 | 0 | 3771408 | 0.113857 | stage 2 visited more than 6 times |
| t1_debounce_bank | 3 | H2 | 20261112-030951-b157 | 2100.3 |  | 7 | fail | fail 0/9 | 0 | 7703674 | 0.210327 | stage 2 visited more than 6 times |
| t1_debounce_bank | 3 | H9 | 20261112-031013-9841 | 2020.7 |  | 7 | fail | fail 0/9 | 0 | 9184454 | 0.190206 | stage 2 visited more than 6 times |
| d24_no_extra_latency | 3 | A0 | 20261112-042021-6e9f | 3370.6 |  | 4 | fail | pass 3/3 | 0 | 18385825 | 0.316781 | budget: run turns limit 300 reached (300) |
| d24_no_extra_latency | 3 | H1 | 20261112-045251-6b9b | 2545.1 |  | 4 | fail | pass 3/3 | 0 | 8375032 | 0.253677 | budget: run turns limit 300 reached (300) |
| d24_no_extra_latency | 3 | H2 | 20261112-034500-7403 | 1431.4 |  | 7 | fail | pass 3/3 | 0 | 4368117 | 0.129338 | stage 2 visited more than 6 times |
| d24_no_extra_latency | 3 | H9 | 20261112-040859-844b | 2626.0 |  | 5 | fail | pass 3/3 | 0 | 14031075 | 0.27587 | budget: run turns limit 300 reached (300) |
