| Arm | Runs | Problem-runs | unparsable | invalid_edit | length | empty | provider_err | loop | cap_stop | Reliability failures | Per 86 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| L | 1 | 86 | 1 (1) | 17 (45) | 1 (1) | 0 (0) | 1 (1) | 5 (14) | 2 (2) | 17 | 17.0 |
| D | 3 | 258 | 1 (1) | 30 (37) | 4 (4) | 0 (0) | 9 (9) | 22 (45) | 31 (31) | 75 | 25.0 |

Each measure: problem-runs affected (events). Per 86 = failures / problem-runs x 86.

| Arm | Stop reasons |
|---|---|
| L | submit 83, llm_error 1, wall_time 1, max_turns 1 |
| D | submit 216, max_turns 30, llm_error 9, give_up 2, wall_time 1 |
