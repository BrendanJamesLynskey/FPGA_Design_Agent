| Arm | Runs | Problem-runs | unparsable | invalid_edit | length | empty | provider_err | loop | cap_stop | Reliability failures | Per 86 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| G_void_guard060 | 1 | 86 | 1 (1) | 5 (11) | 3 (8) | 3 (7) | 2 (2) | 6 (12) | 73 (73) | 81 | 81.0 |
| G_void_guard120 | 1 | 86 | 4 (5) | 11 (16) | 6 (11) | 5 (8) | 8 (8) | 7 (12) | 36 (36) | 58 | 58.0 |
| G_void_402 | 1 | 86 | 3 (5) | 12 (16) | 6 (9) | 6 (9) | 26 (26) | 11 (22) | 26 (26) | 63 | 63.0 |
| G_void_guard281 | 1 | 86 | 4 (4) | 21 (30) | 5 (8) | 5 (7) | 21 (21) | 12 (23) | 19 (19) | 57 | 57.0 |

Each measure: problem-runs affected (events). Per 86 = failures / problem-runs x 86.

| Arm | Stop reasons |
|---|---|
| G_void_guard060 | run_budget_exhausted 67, submit 11, max_turns 3, wall_time 3, llm_error 2 |
| G_void_guard120 | submit 42, run_budget_exhausted 32, llm_error 8, wall_time 4 |
| G_void_402 | submit 34, llm_error 26, run_budget_exhausted 16, max_turns 6, wall_time 4 |
| G_void_guard281 | submit 46, llm_error 21, run_budget_exhausted 13, wall_time 5, max_turns 1 |
