#### Paired effect against the base (`luna_old`)

Effect = mean over common problems of (arm pass rate − base pass rate), in points of pass rate. 97.5% interval: paired bootstrap over problems. Sign test: exact, two-sided, on the problems that changed. Arms whose interval includes 0 come first.

| Arm | Finding | Effect [97.5%] | Better / worse / same | Sign test p | Problems | Dropped |
|---|---|---|---|---|---|---|
| L | no detectable effect | +0.4 [-6.6, +7.2] | 18 / 11 / 57 | 0.265 | 86 | 0 |

Problems left out of the paired effect (in only one of the arm and the base; the Arms table below still pools over them): none.

#### Arms

| Arm | Runs: pass rate each | Pooled pass@1 [95% problem bootstrap] | Cost | $/problem | $/solved | Median wall | Tokens |
|---|---|---|---|---|---|---|---|
| luna_old (base) | 6: 65.1%, 59.3%, 60.5%, 57.0%, 60.5%, 65.1% | 316/516 = 61.2% [52.1, 70.2] | ≥$3.3397 (5 unreported) | ≥$0.0065 | ≥$0.0106 | 63 s | 16,296,927 |
| L | 1: 61.6% | 53/86 = 61.6% [51.2, 72.1] | ≥$0.5307 (1 unreported) | ≥$0.0062 | ≥$0.0100 | 57 s | 2,466,028 |

#### Pareto: pass rate against $ per problem

| Arm | $/problem | Pass rate | Frontier |
|---|---|---|---|
| L | ≥$0.0062 | 61.6% | n/a (cost a lower bound) |
| luna_old | ≥$0.0065 | 61.2% | n/a (cost a lower bound) |

≥: some of the arm's cost was not reported, so its $/problem is a lower bound. It is drawn hollow and kept off the frontier.

