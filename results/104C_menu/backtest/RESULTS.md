# Back-test results with the order-independent menu rule (brief 104C)

Scores are computed by code (`flow/options/backtest.py`, unchanged). P1 = the pinned prompts, P2 = brief 104's original prompts. Counts over three runs.

| set / case / arm | failed | model options per run | parts per run | combined per run | named found (of 3) per run | variants found (of 4) per run | in range per run |
|---|---|---|---|---|---|---|---|
| P1/b96_10g_pre97/A | 0 | [4, 4, 4] | [3, 1, 5] | [4, 4, 4] | [1, 2, 1] | [2, 2, 2] | [2, 2, 2] |
| P1/b96_10g_pre97/B | 0 | [4, 4, 4] | [0, 2, 3] | [3, 4, 4] | [1, 3, 1] | [2, 4, 2] | [2, 4, 2] |
| P2/b96_10g_pre97/A | 0 | [4, 4, 4] | [0, 4, 1] | [3, 4, 4] | [3, 1, 2] | [4, 2, 2] | [4, 2, 2] |
| P2/b96_10g_pre97/B | 0 | [4, 3, 4] | [1, 2, 1] | [4, 4, 4] | [2, 2, 2] | [3, 3, 3] | [3, 3, 3] |

H4 (menu invariant to the order of the model's options, 24 shuffles per run, content compared): 12 runs checked, runs with a different menu or a recorded menu that does not match the rebuild: none

H3 (no offered option outside the stage file's bounds): none outside, over 116 latency options

Over the b96 runs (104B offered -> 104C offered, of the runs; 104C in range; 104C available with the cap lifted):

- agent_cdc: 12 -> 12 of 12 (in range 12; available 12)
- hand_ref: 9 -> 10 of 12 (in range 10; available 12)
- agent_both: 0 -> 2 of 12 (in range 2; available 10)
- all3: 1 -> 7 of 12 (in range 7; available 10)

Per variant (found / in range, of three runs; the range's high end above the measured cut; the origin of the matching option):

- P1/b96_10g_pre97/A: agent_cdc 3/3 (over [0, 0, 0.0], ['model', 'model', 'splitter']); hand_ref 2/2 (over [0, 0], ['model', 'model']); agent_both 0/0 (over [], []); all3 1/1 (over [0.0], ['combiner'])
- P1/b96_10g_pre97/B: agent_cdc 3/3 (over [1, 1, 1], ['model', 'model', 'model']); hand_ref 3/3 (over [1.0, 1.0, 1.0], ['combiner', 'combiner', 'combiner']); agent_both 1/1 (over [1.0], ['combiner']); all3 1/1 (over [1], ['model'])
- P2/b96_10g_pre97/A: agent_cdc 3/3 (over [0, 0, 0], ['model', 'model', 'model']); hand_ref 2/2 (over [0.0, 0.0], ['combiner', 'combiner']); agent_both 1/1 (over [0.0], ['combiner']); all3 2/2 (over [0, 0.0], ['model', 'combiner'])
- P2/b96_10g_pre97/B: agent_cdc 3/3 (over [1, 2, 1], ['model', 'splitter', 'model']); hand_ref 3/3 (over [1.0, 2.0, 1.0], ['combiner', 'combiner', 'combiner']); agent_both 0/0 (over [], []); all3 3/3 (over [0, 0, 1], ['model', 'model', 'model'])
