#### Paired effect against the base (`L`)

Effect = mean over common problems of (arm pass rate − base pass rate), in points of pass rate. 97.5% interval: paired bootstrap over problems. Sign test: exact, two-sided, on the problems that changed. Arms whose interval includes 0 come first.

| Arm | Finding | Effect [97.5%] | Better / worse / same | Sign test p | Problems | Dropped |
|---|---|---|---|---|---|---|
| G | no detectable effect | -4.1 [-13.4, +5.8] | 10 / 16 / 60 | 0.327 | 86 | 0 |
| D | worse than base | -12.4 [-21.7, -3.5] | 4 / 21 / 61 | 0.000911 | 86 | 0 |

Problems left out of the paired effect (in only one of the arm and the base; the Arms table below still pools over them): none.

#### Arms

| Arm | Runs: pass rate each | Pooled pass@1 [95% problem bootstrap] | Cost | $/problem | $/solved | Median wall | Tokens |
|---|---|---|---|---|---|---|---|
| L (base) | 1: 61.6% | 53/86 = 61.6% [51.2, 72.1] | ≥$0.5307 (1 unreported) | ≥$0.0062 | ≥$0.0100 | 57 s | 2,466,028 |
| G | 2: 59.3%, 55.8% | 99/172 = 57.6% [48.3, 66.9] | ≥$1.1454 (34 unreported) | ≥$0.0067 | ≥$0.0116 | 203 s | 10,343,103 |
| D | 3: 50.0%, 46.5%, 51.2% | 127/258 = 49.2% [39.9, 58.9] | ≥$2.1930 (9 unreported) | ≥$0.0085 | ≥$0.0173 | 21 s | 14,257,107 |

#### Pareto: pass rate against $ per problem

| Arm | $/problem | Pass rate | Frontier |
|---|---|---|---|
| L | ≥$0.0062 | 61.6% | n/a (cost a lower bound) |
| G | ≥$0.0067 | 57.6% | n/a (cost a lower bound) |
| D | ≥$0.0085 | 49.2% | n/a (cost a lower bound) |

≥: some of the arm's cost was not reported, so its $/problem is a lower bound. It is drawn hollow and kept off the frontier.

