# Merged functional coverage (cocotb-coverage), 42 runs

**215 of 217 bins hit**, 2 open holes.

| coverage point | bins | hit | hit % |
|---|---|---|---|
| block.kind | 16 | 16 | 100.0 % |
| block.kind x lock | 32 | 32 | 100.0 % |
| block.lock | 2 | 2 | 100.0 % |
| error.kind | 11 | 11 | 100.0 % |
| frame.fcs | 2 | 2 | 100.0 % |
| frame.gap | 6 | 6 | 100.0 % |
| frame.len | 8 | 8 | 100.0 % |
| frame.len x fcs | 16 | 16 | 100.0 % |
| frame.len x gap | 48 | 46 | 95.8 % |
| frame.mod8 | 8 | 8 | 100.0 % |
| frame.pat | 5 | 5 | 100.0 % |
| ifg.bytes | 6 | 6 | 100.0 % |
| ifg.tlane | 8 | 8 | 100.0 % |
| lock.event | 5 | 5 | 100.0 % |
| lock.hunt_slips_before_first_lock | 4 | 4 | 100.0 % |
| lock.transition | 3 | 3 | 100.0 % |
| rxf.outcome | 3 | 3 | 100.0 % |
| rxf.outcome x slane | 6 | 6 | 100.0 % |
| rxf.slane | 2 | 2 | 100.0 % |
| rxf.slane (non-aborted) | 2 | 2 | 100.0 % |
| rxf.slane x tlane | 16 | 16 | 100.0 % |
| rxf.tlane | 8 | 8 | 100.0 % |

## Open holes

- `frame.len x gap|('LEN_1024_1500', 'GAP_256P')`
- `frame.len x gap|('LEN_60', 'GAP_1_3')`
