# Back-test results with the combiner (brief 104A)

Scores are computed by code (`flow/options/backtest.py`, unchanged). P1 = the pinned prompts, P2 = brief 104's original prompts. Counts over three runs.

| set / case / arm | failed | model options per run | combined per run | named found (of 3) per run | variants found (of 4) per run | in range per run |
|---|---|---|---|---|---|---|
| P1/b96_10g_pre97/A | 0 | [4, 4, 4] | [1, 2, 0] | [1, 1, 1] | [2, 2, 2] | [2, 2, 2] |
| P1/b96_10g_pre97/B | 0 | [4, 4, 4] | [4, 2, 3] | [1, 1, 1] | [1, 2, 2] | [1, 2, 2] |
| P1/c16_montgomery_200mhz/A | 0 | [3, 3, 3] | [0, 0, 0] | [None, None, None] | [1, 1, 1] | [0, 1, 1] |
| P2/b96_10g_pre97/A | 0 | [4, 4, 4] | [4, 4, 4] | [1, 1, 2] | [2, 2, 3] | [2, 2, 3] |
| P2/b96_10g_pre97/B | 0 | [4, 4, 3] | [4, 4, 1] | [1, 1, 1] | [1, 2, 1] | [1, 2, 1] |

Per variant (found / in range, of three runs; the range's high end above the measured cut; the origin of the matching option):

- P1/b96_10g_pre97/A: agent_cdc 3/3 (over [0, 0, 0], ['model', 'model', 'model']); hand_ref 3/3 (over [0, 0, 0], ['combiner', 'combiner', 'model']); agent_both 0/0 (over [], []); all3 0/0 (over [], [])
- P1/b96_10g_pre97/B: agent_cdc 3/3 (over [1, 1, 1], ['model', 'model', 'model']); hand_ref 2/2 (over [1, 1], ['combiner', 'combiner']); agent_both 0/0 (over [], []); all3 0/0 (over [], [])
- P2/b96_10g_pre97/A: agent_cdc 3/3 (over [0, 0, 0], ['model', 'model', 'model']); hand_ref 3/3 (over [0, 0, 0], ['combiner', 'combiner', 'combiner']); agent_both 0/0 (over [], []); all3 1/1 (over [0], ['combiner'])
- P2/b96_10g_pre97/B: agent_cdc 3/3 (over [1, 1, 0], ['model', 'model', 'model']); hand_ref 1/1 (over [1], ['model']); agent_both 0/0 (over [], []); all3 0/0 (over [], [])
