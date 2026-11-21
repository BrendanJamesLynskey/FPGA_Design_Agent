# Back-test results with the splitter and the combiner (brief 104B)

Scores are computed by code (`flow/options/backtest.py`, unchanged). P1 = the pinned prompts, P2 = brief 104's original prompts. Counts over three runs.

| set / case / arm | failed | model options per run | parts per run | combined per run | named found (of 3) per run | variants found (of 4) per run | in range per run |
|---|---|---|---|---|---|---|---|
| P1/b96_10g_pre97/A | 0 | [4, 4, 4] | [0, 5, 3] | [3, 4, 4] | [1, 1, 1] | [2, 1, 1] | [2, 1, 1] |
| P1/b96_10g_pre97/B | 0 | [4, 4, 4] | [0, 3, 3] | [3, 4, 4] | [1, 1, 1] | [2, 2, 2] | [2, 2, 2] |
| P1/c16_montgomery_200mhz/A | 0 | [3, 4, 4] | [0, 0, 0] | [0, 0, 0] | [None, None, None] | [1, 1, 1] | [1, 1, 1] |
| P2/b96_10g_pre97/A | 0 | [4, 4, 4] | [1, 3, 3] | [4, 4, 4] | [2, 1, 1] | [3, 2, 1] | [3, 2, 1] |
| P2/b96_10g_pre97/B | 0 | [3, 4, 4] | [1, 4, 2] | [3, 4, 4] | [1, 1, 1] | [2, 2, 2] | [2, 2, 2] |

H3 (no offered option outside the stage file's bounds): none outside, over 120 latency options

Over the b96 runs (104A offered -> 104B offered, of the runs; 104B in range; 104B available with the cap lifted):

- agent_cdc: 12 -> 12 of 12 (in range 12; available 12)
- hand_ref: 9 -> 9 of 12 (in range 9; available 12)
- agent_both: 0 -> 0 of 12 (in range 0; available 6)
- all3: 1 -> 1 of 12 (in range 1; available 6)

Per variant (found / in range, of three runs; the range's high end above the measured cut; the origin of the matching option):

- P1/b96_10g_pre97/A: agent_cdc 3/3 (over [0, 0.0, 0.0], ['model', 'splitter', 'splitter']); hand_ref 1/1 (over [0.0], ['combiner']); agent_both 0/0 (over [], []); all3 0/0 (over [], [])
- P1/b96_10g_pre97/B: agent_cdc 3/3 (over [1, 0, 0], ['model', 'model', 'model']); hand_ref 3/3 (over [1.0, 0.0, 0.0], ['combiner', 'combiner', 'combiner']); agent_both 0/0 (over [], []); all3 0/0 (over [], [])
- P2/b96_10g_pre97/A: agent_cdc 3/3 (over [0, 0, 0], ['model', 'model', 'model']); hand_ref 2/2 (over [0.0, 0.0], ['combiner', 'combiner']); agent_both 0/0 (over [], []); all3 1/1 (over [0.0], ['combiner'])
- P2/b96_10g_pre97/B: agent_cdc 3/3 (over [1, 1, 1], ['model', 'model', 'model']); hand_ref 3/3 (over [1.0, 1.0, 1.0], ['combiner', 'combiner', 'combiner']); agent_both 0/0 (over [], []); all3 0/0 (over [], [])
