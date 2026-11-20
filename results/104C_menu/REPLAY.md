# Development replay of the menu rule (brief 104C)

No model call. The model's own options of the 30 recorded runs of 104A (15) and 104B (15), rebuilt with each rule and scored with the unchanged `flow/options/backtest.py`. **Development data**: the final rule was argued before this replay, but a first candidate was dropped after it (see the pre-registration), so these numbers are not a test. Counts are over the 12 b96 runs of each source.

Offered under the cap of four (found / in range when found); available = every valid combination listed (cap lifted).

| rule | source | agent_cdc | hand_ref | agent_both | all3 | menu differs for some order of the options (of 15 runs incl. c16) |
|---|---|---|---|---|---|---|
| 104B rule (before; version 2) | 104A | 12 / 12 | 11 / 11 | 0 / 0 | 2 / 2 | 12 of 15 |
| 104B rule (before; version 2) | 104B | 12 / 12 | 9 / 9 | 0 / 0 | 1 / 1 | 12 of 15 |
| candidate 1: headroom only (superseded) | 104A | 12 / 12 | 4 / 4 | 0 / 0 | 1 / 1 | 0 of 15 |
| candidate 1: headroom only (superseded) | 104B | 12 / 12 | 3 / 3 | 0 / 0 | 1 / 1 | 0 of 15 |
| final rule (version 3) | 104A | 12 / 12 | 6 / 6 | 0 / 0 | 2 / 2 | 0 of 15 |
| final rule (version 3) | 104B | 12 / 12 | 5 / 5 | 1 / 1 | 1 / 1 | 0 of 15 |

Available with the cap lifted (the same for every rule, since the cap is not part of the ordering): 104A: agent_cdc 12, hand_ref 12, agent_both 8, all3 8; 104B: agent_cdc 12, hand_ref 12, agent_both 6, all3 6

Reading: the order-independent rule removes the order dependence (the 104B rule gave a different menu for some order of the model's options in most runs) and does not make `agent_both` appear, and it offers `hand_ref` less often than the 104B rule did, which probably got `hand_ref` partly from the model's habit of listing `cross_go` first.
