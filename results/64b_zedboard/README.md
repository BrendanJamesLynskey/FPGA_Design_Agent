# 64B: HW/SW partitioning on the ZedBoard (Zynq-7000, bare metal)

Records from brief 64B: the build reports of the ZedBoard design `designs/b64b_zedboard` (Vivado 2026.1) and the console logs of the
bare-metal programs that ran on its Cortex-A9, measuring port latency, interrupt latency, software against the HP and ACP offload paths for
CRC-32 and a 16-tap FIR, and the A9's reaction to AXI error responses. Every log is the DDR copy of the console text read over JTAG
(or the UART where noted), with the XADC temperature and rails at the start and end of each run.

## Records

| File or folder | What it is |
|---|---|
| `summary.json` | the numbers the design's handover cites, read from the logs and reports below by `designs/b64b_zedboard/make_summary.py` |
| `builds/full/` | Vivado 2026.1 reports of the full design (utilisation, timing, power, DRC, methodology); `builds/p0/` the earlier bring-up design |
| `bringup/` | hello program, GP-port read and write latency, interrupt-to-handler latency (caches on and MMU/caches off) |
| `sweeps/crc32_sweep.log`, `sweeps/fir16_sweep.log` | one line per path and size: min, median, 95th percentile, max, mean in ns and a 16-bin histogram; `sweeps/summary.md` is the table of medians |
| `sweeps/partition_crc32_zynq_measured.{json,txt}` | the 64A cost model run with the measured ranges (`hwsw/examples/partition_crc32_zynq_measured.yaml`) |
| `bus_errors/` | 30 runs, one access type each (`e_<target><write><mapping>.log`), and `bus_errors/README.md` with the table of results |

## Reproduce

Build: `vivado -mode batch -source designs/b64b_zedboard/vivado/build_full.tcl -tclargs <out> <repo>` (Vivado 2026.1, heavy slot, about 16
minutes; reproduced on 2026-11-15 with the same slack figures). Programs: `make -C designs/b64b_zedboard/sw ...` and `sw/build_err.sh`.
Board runs need the ZedBoard, the board lock and a first load then light reloads (`designs/b64b_zedboard/tcl/zb.tcl`); they cannot be
regenerated without the board. `python3 designs/b64b_zedboard/make_summary.py` rebuilds `summary.json` from the files here.

## Known gaps and limits

One board, one bitstream, one power-up (2026-11-15); the earlier bring-up logs are from 2026-11-14. Operating conditions were inside the
recommended range with no latched alarm in every log, but the XADC cannot see fast supply droop. Medians come with the min, 95th percentile
and max, not with confidence intervals. No Linux measurement and no power measurement exist. The normal non-cacheable error-capture count and
the lost posted-write error are observed but not explained (see `bus_errors/README.md`). The sweep buffers sit in DDR; the L2 cache is 512 KB, so the 1 MB case also measures capacity effects.
