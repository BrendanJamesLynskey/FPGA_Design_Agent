#### Paired effect against the base (`luna_old`)

Effect = mean over common problems of (arm pass rate − base pass rate), in points of pass rate. 97.5% interval: paired bootstrap over problems. Sign test: exact, two-sided, on the problems that changed. Arms whose interval includes 0 come first.

| Arm | Finding | Effect [97.5%] | Better / worse / same | Sign test p | Problems | Dropped |
|---|---|---|---|---|---|---|
| D | worse than base | -12.0 [-21.1, -3.5] | 12 / 26 / 48 | 0.0336 | 86 | 0 |

Problems left out of the paired effect (in only one of the arm and the base; the Arms table below still pools over them): none.

#### Arms

| Arm | Runs: pass rate each | Pooled pass@1 [95% problem bootstrap] | Cost | $/problem | $/solved | Median wall | Tokens |
|---|---|---|---|---|---|---|---|
| luna_old (base) | 6: 65.1%, 59.3%, 60.5%, 57.0%, 60.5%, 65.1% | 316/516 = 61.2% [52.1, 70.2] | ≥$3.3397 (5 unreported) | ≥$0.0065 | ≥$0.0106 | 63 s | 16,296,927 |
| D | 3: 50.0%, 46.5%, 51.2% | 127/258 = 49.2% [39.9, 58.9] | ≥$2.1930 (9 unreported) | ≥$0.0085 | ≥$0.0173 | 21 s | 14,257,107 |

#### Pareto: pass rate against $ per problem

| Arm | $/problem | Pass rate | Frontier |
|---|---|---|---|
| luna_old | ≥$0.0065 | 61.2% | n/a (cost a lower bound) |
| D | ≥$0.0085 | 49.2% | n/a (cost a lower bound) |

≥: some of the arm's cost was not reported, so its $/problem is a lower bound. It is drawn hollow and kept off the frontier.

