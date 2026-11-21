| Variant | Registers in the I/O block | Input setup slack | Input hold slack | Input data path | Output setup slack | Output hold slack | Output data path (clock to pin) | iob check |
|---|---|---|---|---|---|---|---|---|
| packed | 7/7 | +1.569 | +1.603 | 1.512 | +3.702 | +8.733 | 4.069 | pass |
| unpacked | 0/7 | +0.801 | +1.883 | 2.266 | +1.011 | +9.430 | 6.953 | FAIL (IOB-NOT-PACKED, 7) |
| gate_in | 5/7 | +0.333 | +1.622 | 2.863 | +3.702 | +8.733 | 4.069 | FAIL (IOB-NOT-PACKED, 2) |
| gate_out | 6/7 | +1.569 | +1.603 | 1.512 | +0.589 | +0.534 | 7.189 | FAIL (IOB-NOT-PACKED, 1) |
| fanout_out | 7/7 | +1.569 | +1.603 | 1.512 | +3.702 | +8.733 | 4.069 | pass |
| packed_Explore | 7/7 | +1.569 | +1.603 | 1.512 | +3.702 | +8.733 | 4.069 | pass |
| unpacked_Explore | 0/7 | +0.801 | +1.883 | 2.266 | +1.011 | +9.430 | 6.953 | FAIL (IOB-NOT-PACKED, 7) |
| packed_AltSpreadLogic_high | 7/7 | +1.569 | +1.603 | 1.512 | +3.702 | +8.733 | 4.069 | pass |
| unpacked_AltSpreadLogic_high | 0/7 | +0.801 | +1.883 | 2.266 | +1.079 | +9.426 | 6.943 | FAIL (IOB-NOT-PACKED, 7) |
