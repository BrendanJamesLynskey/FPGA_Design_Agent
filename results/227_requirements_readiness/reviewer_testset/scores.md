### Condition `fallback` (run 1 of each problem)

| Measure | Result |
|---|---|
| Recall, fact-missing positives (A and D): flagged | 9/10 = 90% [60%, 98%] |
| Recall, fact-missing positives: flagged and the missing fact named | 6/10 = 60% [31%, 83%] |
| Borderline positives (B), apart: flagged / named | 2/2 = 100% [34%, 100%] / 1/2 = 50% [9%, 91%] |
| Test-reaches-into-implementation (C), apart: flagged / named | 6/6 = 100% [61%, 100%] / 3/6 = 50% [19%, 81%] |
| Specificity on all negatives (E and F): not flagged | 8/23 = 35% [19%, 55%] |
| Specificity, hard negatives (E) / easy negatives (F) | 0/2 = 0% [0%, 66%] / 8/21 = 38% [21%, 59%] |
| Precision for the fact-missing positives (at this set's prevalence 30% positives) | 38% |
| Flag everything (reference): recall / specificity | 100% / 0% |
| Flag nothing (reference): recall / specificity | 0% / 100% |
| Blocking questions that changed nothing: on negatives / on positives without the fact named | 70 / 37 |
| Run-to-run: same flag on both runs | 0/0 |
| Group G (undiagnosed candidates): flagged | 0/0 (not scored) |
| Unlabelled agentic problems (U, no group): flagged | 0/0 (a flag rate, not a score) |
| Findings per problem (mean) | 5.51 |
| Tokens (input / output), run 1 | 302,653 / 45,709 |

### Condition `fallback_v2` (run 1 of each problem)

| Measure | Result |
|---|---|
| Recall, fact-missing positives (A and D): flagged | 9/10 = 90% [60%, 98%] |
| Recall, fact-missing positives: flagged and the missing fact named | 6/10 = 60% [31%, 83%] |
| Borderline positives (B), apart: flagged / named | 2/2 = 100% [34%, 100%] / 1/2 = 50% [9%, 91%] |
| Test-reaches-into-implementation (C), apart: flagged / named | 5/6 = 83% [44%, 97%] / 3/6 = 50% [19%, 81%] |
| Specificity on all negatives (E and F): not flagged | 11/23 = 48% [29%, 67%] |
| Specificity, hard negatives (E) / easy negatives (F) | 0/2 = 0% [0%, 66%] / 11/21 = 52% [32%, 72%] |
| Precision for the fact-missing positives (at this set's prevalence 30% positives) | 43% |
| Flag everything (reference): recall / specificity | 100% / 0% |
| Flag nothing (reference): recall / specificity | 0% / 100% |
| Blocking questions that changed nothing: on negatives / on positives without the fact named | 32 / 22 |
| Run-to-run: same flag on both runs | 0/0 |
| Group G (undiagnosed candidates): flagged | 0/0 (not scored) |
| Unlabelled agentic problems (U, no group): flagged | 0/0 (a flag rate, not a score) |
| Findings per problem (mean) | 2.07 |
| Tokens (input / output), run 1 | 314,382 / 57,333 |

### Condition `kb` (run 1 of each problem)

| Measure | Result |
|---|---|
| Recall, fact-missing positives (A and D): flagged | 9/10 = 90% [60%, 98%] |
| Recall, fact-missing positives: flagged and the missing fact named | 6/10 = 60% [31%, 83%] |
| Borderline positives (B), apart: flagged / named | 2/2 = 100% [34%, 100%] / 1/2 = 50% [9%, 91%] |
| Test-reaches-into-implementation (C), apart: flagged / named | 6/6 = 100% [61%, 100%] / 4/6 = 67% [30%, 90%] |
| Specificity on all negatives (E and F): not flagged | 7/23 = 30% [16%, 51%] |
| Specificity, hard negatives (E) / easy negatives (F) | 0/2 = 0% [0%, 66%] / 7/21 = 33% [17%, 55%] |
| Precision for the fact-missing positives (at this set's prevalence 30% positives) | 36% |
| Flag everything (reference): recall / specificity | 100% / 0% |
| Flag nothing (reference): recall / specificity | 0% / 100% |
| Blocking questions that changed nothing: on negatives / on positives without the fact named | 75 / 30 |
| Run-to-run: same flag on both runs | 40/41 |
| Group G (undiagnosed candidates): flagged | 25/25 (not scored) |
| Unlabelled agentic problems (U, no group): flagged | 0/0 (a flag rate, not a score) |
| Findings per problem (mean) | 6.23 |
| Tokens (input / output), run 1 | 517,136 / 80,944 |

### Condition `kb_v2` (run 1 of each problem)

| Measure | Result |
|---|---|
| Recall, fact-missing positives (A and D): flagged | 9/10 = 90% [60%, 98%] |
| Recall, fact-missing positives: flagged and the missing fact named | 5/10 = 50% [24%, 76%] |
| Borderline positives (B), apart: flagged / named | 2/2 = 100% [34%, 100%] / 1/2 = 50% [9%, 91%] |
| Test-reaches-into-implementation (C), apart: flagged / named | 5/6 = 83% [44%, 97%] / 4/6 = 67% [30%, 90%] |
| Specificity on all negatives (E and F): not flagged | 10/23 = 43% [26%, 63%] |
| Specificity, hard negatives (E) / easy negatives (F) | 0/2 = 0% [0%, 66%] / 10/21 = 48% [28%, 68%] |
| Precision for the fact-missing positives (at this set's prevalence 30% positives) | 41% |
| Flag everything (reference): recall / specificity | 100% / 0% |
| Flag nothing (reference): recall / specificity | 0% / 100% |
| Blocking questions that changed nothing: on negatives / on positives without the fact named | 38 / 22 |
| Run-to-run: same flag on both runs | 39/41 |
| Group G (undiagnosed candidates): flagged | 23/25 (not scored) |
| Unlabelled agentic problems (U, no group): flagged | 25/49 (a flag rate, not a score) |
| Findings per problem (mean) | 2.00 |
| Tokens (input / output), run 1 | 1,058,849 / 170,111 |

