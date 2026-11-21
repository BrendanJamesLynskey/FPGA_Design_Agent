# 82P6 wall-time breakdown (minutes of the run's wall time)

Role = all role calls (their own `simulate` calls are inside it, shown separately); Verilator, Icarus, V3 cov = the graph's gate
simulations; synth = the synthesis gate (span of its calls, which includes waiting for the Vivado slot); other = the rest
(spec-test benches, contract, standards, harness, startup).

| Run | Wall | Hidden | S2 visits | Role | of which role's own sim | Spec-test role | Gate Verilator | Gate Icarus | Icarus time-outs | V3 cov | Synth gate | Other tools | Other |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A r1 8b7c | 100 | 0/10 | 6 | 54 | 21 | 0 | 15 | 30 | 1 | 0 | 0 | 0 | 0 |
| B r1 36d0 | 240 killed | 10/10 | 6 | 39 | 13 | 2 | 19 | 64 | 0 | 0 | 112 | 0 | 5 |
| A r2 c80a | 240 killed | 10/10 | 5 | 106 | 80 | 0 | 42 | 91 | 4 | 0 | 0 | 0 | 1 |
| B r2 f825 | 240 killed | 10/10 | 4 | 39 | 20 | 2 | 17 | 72 | 0 | 0 | 103 | 0 | 6 |
| A r3 1ea8 | 117 | 6/10 | 7 | 76 | 70 | 0 | 40 | 0 | 3 | 0 | 0 | 0 | 0 |
| B r3 2fe1 | 240 killed | 1/10 | 6 | 69 | 46 | 8 | 26 | 85 | 0 | 0 | 47 | 0 | 6 |

Pooled over 6 runs (19.6 h): role 33 %, gate Verilator 14 %, gate Icarus 29 %, V3 cov 0 %, spec-test role 1 %.

## Per stage-2 visit (minutes)

| Run | Visit | Role | Role's own sim | Gate Verilator | Gate Icarus | Icarus time-outs | V3 cov | Synth span |
|---|---|---|---|---|---|---|---|---|
| A r1 | 1 | 18 | 1 | 0 | 0 | 0 | 0 | 0 |
| A r1 | 2 | 3 | 1 | 1 | 0 | 0 | 0 | 0 |
| A r1 | 3 | 4 | 2 | 2 | 0 | 0 | 0 | 0 |
| A r1 | 4 | 4 | 2 | 2 | 0 | 0 | 0 | 0 |
| A r1 | 5 | 10 | 5 | 3 | 0 | 0 | 0 | 0 |
| A r1 | 6 | 13 | 10 | 7 | 30 | 1 | 0 | 0 |
| B r1 | 1 | 19 | 1 | 0 | 0 | 0 | 0 | 0 |
| B r1 | 2 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| B r1 | 3 | 4 | 2 | 2 | 0 | 0 | 0 | 0 |
| B r1 | 4 | 8 | 6 | 6 | 22 | 0 | 0 | 48 |
| B r1 | 5 | 0 | 0 | 6 | 24 | 0 | 0 | 47 |
| B r1 | 6 | 5 | 4 | 5 | 18 | 0 | 0 | 16 |
| A r2 | 1 | 29 | 9 | 9 | 1 | 0 | 0 | 0 |
| A r2 | 2 | 41 | 39 | 13 | 30 | 2 | 0 | 0 |
| A r2 | 3 | 12 | 12 | 12 | 30 | 1 | 0 | 0 |
| A r2 | 4 | 21 | 21 | 9 | 30 | 1 | 0 | 0 |
| A r2 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| B r2 | 1 | 26 | 10 | 4 | 19 | 0 | 0 | 0 |
| B r2 | 2 | 5 | 4 | 4 | 18 | 0 | 0 | 47 |
| B r2 | 3 | 0 | 0 | 4 | 18 | 0 | 0 | 47 |
| B r2 | 4 | 5 | 5 | 4 | 17 | 0 | 0 | 9 |
| A r3 | 1 | 60 | 30 | 0 | 0 | 1 | 0 | 0 |
| A r3 | 2 | 2 | 30 | 30 | 0 | 2 | 0 | 0 |
| A r3 | 3 | 3 | 2 | 2 | 0 | 0 | 0 | 0 |
| A r3 | 4 | 3 | 2 | 2 | 0 | 0 | 0 | 0 |
| A r3 | 5 | 2 | 2 | 2 | 0 | 0 | 0 | 0 |
| A r3 | 6 | 2 | 2 | 2 | 0 | 0 | 0 | 0 |
| A r3 | 7 | 0 | 2 | 2 | 0 | 0 | 0 | 0 |
| B r3 | 1 | 19 | 2 | 2 | 0 | 0 | 0 | 0 |
| B r3 | 2 | 3 | 2 | 2 | 0 | 0 | 0 | 0 |
| B r3 | 3 | 37 | 34 | 7 | 27 | 0 | 0 | 0 |
| B r3 | 4 | 1 | 0 | 1 | 0 | 0 | 0 | 0 |
| B r3 | 5 | 7 | 7 | 7 | 29 | 0 | 0 | 47 |
| B r3 | 6 | 0 | 0 | 7 | 29 | 0 | 0 | 0 |
