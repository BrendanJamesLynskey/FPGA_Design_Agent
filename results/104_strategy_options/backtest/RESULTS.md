# Back-test results (brief 104)

Scores are computed by code (`flow/options/backtest.py`) from the recorded runs. Arms A, B and the c16 arm are the pre-registered runs; A2 and B2 are the exploratory re-run with the
revised prompt (see the addendum in preregistration.md). Counts over three runs, not rates.

| case / arm | pre-registered | failed | variants found (of 4) per run | named found (of 3) per run | in range per run |
|---|---|---|---|---|---|
| b96_10g_pre97/A | yes | 0 | [1, 1, 1] | [1, 1, 1] | [1, 1, 1] |
| b96_10g_pre97/B | yes | 0 | [1, 1, 1] | [1, 1, 1] | [1, 1, 1] |
| b96_10g_pre97/A2 | no (exploratory) | 0 | [1, 1, 1] | [1, 1, 1] | [1, 1, 1] |
| b96_10g_pre97/B2 | no (exploratory) | 0 | [1, 1, 1] | [1, 1, 1] | [1, 1, 1] |
| c16_montgomery_200mhz/A | yes | 0 | [1, 1, 1] | - | [1, 1, 1] |

Per variant (found / in range, of three runs):

- b96_10g_pre97/A: agent_cdc 3/3, hand_ref 0/0, agent_both 0/0, all3 0/0; the agent_cdc range's high end above the measured 1 clock: [0, 0, 0]
- b96_10g_pre97/B: agent_cdc 3/3, hand_ref 0/0, agent_both 0/0, all3 0/0; the agent_cdc range's high end above the measured 1 clock: [0, 0, 1]
- b96_10g_pre97/A2: agent_cdc 3/3, hand_ref 0/0, agent_both 0/0, all3 0/0; the agent_cdc range's high end above the measured 1 clock: [0, 0, 0]
- b96_10g_pre97/B2: agent_cdc 3/3, hand_ref 0/0, agent_both 0/0, all3 0/0; the agent_cdc range's high end above the measured 1 clock: [1, 1, 1]
- c16_montgomery_200mhz/A: scope-only match 3/3, and naming carry-save 2/3, basis 'guess' in 2/3; high end above the measured +0.679 ns: [0.821, 0.821, 1.321]
