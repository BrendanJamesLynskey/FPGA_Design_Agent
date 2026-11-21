# Functional coverage, merged over 42 runs

Bins hit 213 of 213 (100.0 %). Bins waived with a reason: 0. Open holes: 0. Coverage excluding waived bins: 100.0 %.

| coverage point | bins | hit | waived | hit of all | hit of reachable |
|---|---|---|---|---|---|
| block.kind x lock | 32 | 32 | 0 | 100.0 % | 100.0 % |
| block.kind | 16 | 16 | 0 | 100.0 % | 100.0 % |
| error.kind | 11 | 11 | 0 | 100.0 % | 100.0 % |
| frame.fcs | 2 | 2 | 0 | 100.0 % | 100.0 % |
| frame.gap | 6 | 6 | 0 | 100.0 % | 100.0 % |
| frame.len x fcs | 16 | 16 | 0 | 100.0 % | 100.0 % |
| frame.len x gap | 48 | 48 | 0 | 100.0 % | 100.0 % |
| frame.len | 8 | 8 | 0 | 100.0 % | 100.0 % |
| frame.mod8 | 8 | 8 | 0 | 100.0 % | 100.0 % |
| frame.pat | 5 | 5 | 0 | 100.0 % | 100.0 % |
| ifg.bytes | 6 | 6 | 0 | 100.0 % | 100.0 % |
| ifg.tlane | 8 | 8 | 0 | 100.0 % | 100.0 % |
| lock.event | 5 | 5 | 0 | 100.0 % | 100.0 % |
| lock.hunt_slips_before_first_lock | 4 | 4 | 0 | 100.0 % | 100.0 % |
| lock.transition | 3 | 3 | 0 | 100.0 % | 100.0 % |
| rxf.outcome x slane | 6 | 6 | 0 | 100.0 % | 100.0 % |
| rxf.outcome | 3 | 3 | 0 | 100.0 % | 100.0 % |
| rxf.slane x tlane | 16 | 16 | 0 | 100.0 % | 100.0 % |
| rxf.slane | 2 | 2 | 0 | 100.0 % | 100.0 % |
| rxf.tlane | 8 | 8 | 0 | 100.0 % | 100.0 % |

## Open holes

None.

## Waived bins (not reachable on this bench, with the reason)

None.

## SVA cover properties (hits summed over all runs)

| instance and cover | hits |
|---|---|
| u_mr.u_sva abort | 399 |
| u_mr.u_sva end_and_abort_same_clock | 2 |
| u_mr.u_sva frame_bad_fcs | 536 |
| u_mr.u_sva frame_good_fcs | 1917 |
| u_mt.u_sva eop | 2449 |
| u_mt.u_sva sop | 2449 |
| u_mt.u_sva source_waiting | 7309 |
| u_pr.u_sva hunting_slip | 7104 |
| u_pr.u_sva lock | 188 |
| u_pr.u_sva loss | 67 |
| u_pr.u_sva ordered_set | 20 |
| u_pr.u_sva sh_err | 1937 |
| u_pr.u_sva type_err | 493 |
| u_pt.u_sva full_33_clock_period | 6070 |
| u_pt.u_sva pause | 6140 |
