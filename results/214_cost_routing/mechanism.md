# Mechanism counts per run (from role_usage.jsonl, routing_events.jsonl, kway.jsonl)

| n | design | k | arm | stage-2 visits | own pass | stop | calls by tier (plan USD) | escalated calls | k-way rounds | candidates (gates passed/findings) | kept | plan USD | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | p1_clkmeter | 1 | routing_kway | 3 | yes | done | cheap 1 (0.01); standard 12 (3.27) | 0 | 1 | 1: 9/9, 0; 2: 7/9, 2; 3: 9/9, 0 | cand 3 by LUTs (own gates only) | 3.2801 | 1186.9 |
| 2 | p3_crc_engine | 2 | routing_kway | 3 | yes | done | cheap 1 (0.01); standard 8 (1.91); strong 3 (0.83) | 3 | 1 | 1: 9/9, 0; 2: 9/9, 0; 3: 9/9, 0 | cand 1 by candidate number (own gates only) | 2.7538 | 1016.7 |
| 3 | p3_crc_engine | 2 | control | 1 | no | stage 1 visited more than 4 times; last failing gate: model contract,  | standard 9 (2.04) | 0 | 0 | - | - | 2.0362 | 529.5 |
| 4 | p1_clkmeter | 2 | routing_kway | 5 | yes | done | standard 11 (2.88); strong 5 (2.38) | 5 | 1 | 1: 6/9, 5; 2: 6/9, 5; 3: 6/9, 5 | cand 1 by candidate number (own gates only) | 5.2587 | 1116.0 |
| 5 | p3_crc_engine | 1 | control | 1 | no | stage 1 visited more than 4 times; last failing gate: lint, design sta | standard 10 (2.15) | 0 | 0 | - | - | 2.1512 | 546.7 |
| 6 | p2_bram_rom | 2 | control | 4 | yes | done | standard 11 (2.98) | 0 | 0 | - | - | 2.9827 | 1131.5 |
| 7 | p1_clkmeter | 1 | routing | 3 | yes | done | cheap 1 (0.01); standard 7 (1.99); strong 1 (0.45) | 1 | 0 | - | - | 2.4459 | 705.8 |
| 8 | p3_crc_engine | 1 | routing_kway | 1 | no | stage 1 visited more than 4 times; last failing gate: lint, simulate,  | standard 9 (1.75) | 0 | 0 | - | - | 1.7485 | 444.5 |
| 9 | p1_clkmeter | 1 | control | 3 | yes | done | standard 9 (2.32) | 0 | 0 | - | - | 2.3236 | 784.3 |
| 10 | p2_bram_rom | 1 | control | 5 | yes | done | standard 13 (3.17) | 0 | 0 | - | - | 3.1698 | 923.7 |
| 11 | p1_clkmeter | 2 | control | 2 | yes | done | standard 8 (2.17) | 0 | 0 | - | - | 2.1671 | 688.3 |
| 12 | p2_bram_rom | 1 | routing | 3 | yes | done | cheap 1 (0.01); standard 9 (2.38); strong 1 (0.39) | 1 | 0 | - | - | 2.7741 | 883.1 |
| 14 | p2_bram_rom | 2 | routing | 2 | no | stage 1 visited more than 4 times; last failing gate: lint, simulate,  | standard 10 (2.99) | 0 | 0 | - | - | 2.9905 | 640.8 |
