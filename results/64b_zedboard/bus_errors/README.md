# Bus-error behaviour, ZedBoard bump (Zynq-7000, Cortex-A9 core 0, bare metal), partial

One access type per run: file `e_<target><write><attr>.log`; target 0 hole in `zb_hole_okay`, 1 `zb_hole_slverr`, 2 `zb_hole_split`,
3 an address between two block windows (DECERR from `axil_xbar`), 4 above the last window; write 0 = read, 1 = write; attr 0 =
strongly ordered mapping (device and normal non-cacheable mappings are built, not yet run). 200 accesses per run, async aborts
unmasked, `ldr`/`str` followed by `dsb`, `isb`. The DDR console log is the record (the UART showed the same text when readable).
Vivado 2026.1 build `zb_hwsw`; ps7_init DDR3 settings from the ZedBoard guide; operating conditions in each log (Tj 35-40 C,
rails nominal, no alarm).

| access (SO mapping) | result of 200 attempts |
|---|---|
| read hole, `okay` | no abort, value 0 |
| write hole, `okay` | no abort |
| read hole, `slverr` | 200 precise data aborts, DFSR 0x1008 (external abort, precise, read), DFAR = the address, load result not written |
| write hole, `slverr` | 200 precise aborts at the write's barrier, DFSR 0x1808 (WnR=1), DFAR = the address |
| read hole, `split` | 200 precise aborts, DFSR 0x1008 |
| write hole, `split` | no abort (write ignored) |
| read outside every block (DECERR) | 200 precise aborts, DFSR 0x008 (ExT = 0, so DECERR is distinguishable from SLVERR by DFSR bit 12), DFAR = the address |

The error-capture register block (offsets 0xFF8 address, 0xFFC status) reads back address 0x100 and a count of 200 with the read/write bit
set as expected in every hole run, including `okay` (where no abort was taken).

Not yet measured: outside-block write (DECERR), device and normal non-cacheable mappings (where a write may be posted and the abort
imprecise or lost), Linux. See the report for the wedge that stopped the sequence.
