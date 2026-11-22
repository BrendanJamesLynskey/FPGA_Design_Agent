# 82P7 wall-time breakdown (minutes of the run's wall time)

Role = all role calls (their own `simulate` calls are inside it, shown separately); Verilator, Icarus, V3 cov = the graph's gate
simulations; synth = the synthesis gate (span of its calls, which includes waiting for the Vivado slot); other = the rest
(spec-test benches, contract, standards, harness, startup).

| Run | Wall | Hidden | S2 visits | Role | of which role's own sim | Spec-test role | Gate Verilator | Gate Icarus | Icarus time-outs | V3 cov | Synth gate | Other tools | Other |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A r1 38c3 | 96 | 6/10 | 2 | 37 | 19 | 0 | 15 | 33 | 0 | 0 | 13 | 0 | -2 |
| B r1 1338 | 161 | 1/10 | 4 | 48 | 21 | 3 | 25 | 73 | 0 | 0 | 11 | 0 | -1 |
| A r2 2e7d | 79 | 1/10 | 3 | 34 | 9 | 0 | 5 | 25 | 0 | 0 | 16 | 0 | -1 |
| B r2 b927 | 240 killed | 10/10 | 3 | 43 | 21 | 2 | 19 | 52 | 0 | 0 | 96 | 0 | 28 |
| A r3 7f46 | 91 | 10/10 | 2 | 52 | 34 | 0 | 11 | 26 | 0 | 0 | 2 | 0 | 0 |
| B r3 cca6 | 45 | 10/10 | 1 | 25 | 8 | 2 | 3 | 9 | 0 | 0 | 2 | 0 | 3 |

Pooled over 6 runs (11.8 h): role 33 %, gate Verilator 11 %, gate Icarus 31 %, V3 cov 0 %, spec-test role 1 %.

## Per stage-2 visit (minutes)

| Run | Visit | Role | Role's own sim | Gate Verilator | Gate Icarus | Icarus time-outs | V3 cov | Synth span |
|---|---|---|---|---|---|---|---|---|
| A r1 | 1 | 34 | 19 | 8 | 0 | 0 | 0 | 0 |
| A r1 | 2 | 0 | 0 | 7 | 33 | 0 | 0 | 13 |
| B r1 | 1 | 17 | 2 | 2 | 0 | 0 | 0 | 0 |
| B r1 | 2 | 2 | 1 | 2 | 0 | 0 | 0 | 0 |
| B r1 | 3 | 6 | 2 | 3 | 0 | 0 | 0 | 0 |
| B r1 | 4 | 19 | 16 | 19 | 73 | 0 | 0 | 11 |
| A r2 | 1 | 22 | 4 | 1 | 0 | 0 | 0 | 0 |
| A r2 | 2 | 3 | 1 | 1 | 0 | 0 | 0 | 0 |
| A r2 | 3 | 6 | 4 | 3 | 25 | 0 | 0 | 16 |
| B r2 | 1 | 33 | 15 | 7 | 32 | 0 | 0 | 49 |
| B r2 | 2 | 6 | 6 | 5 | 21 | 0 | 0 | 48 |
| B r2 | 3 | 0 | 0 | 7 | 0 | 0 | 0 | 0 |
| A r3 | 1 | 26 | 11 | 6 | 7 | 0 | 0 | 0 |
| A r3 | 2 | 24 | 23 | 5 | 18 | 0 | 0 | 2 |
| B r3 | 1 | 22 | 8 | 3 | 9 | 0 | 0 | 2 |
