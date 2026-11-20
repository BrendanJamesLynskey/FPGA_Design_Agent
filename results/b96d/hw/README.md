# results/b96d/hw: the 2026-11-19 KR260 eye-scan run (brief 96D): NO EYE WAS MEASURED

**This run counted no samples at any point of any scan. There is no eye, no width, no height and no BER in these files.** They are kept as the record of a failed run and of its diagnosis (brief 96D2).
Every point of all ten scans (9 x 1023 points and one of 2046, 11,253 points in all) reads `{"pre":0,"err":0,"samp":0,"tmo":true}`: the eye-scan state machine never reached END and the sample counter never advanced. About 88 minutes of laser time
(the sum of the ten `run.seconds`) produced nothing. The old `summary.txt` said `open 0`, which reads like "a closed eye"; it meant "no data". `summary.txt` here has been regenerated with `python -m flow.eyescan summary` and says `NO DATA` instead.

## What was run
`_handoff/fpga_agent/run_96d_stage3.sh` (brief 96D), 2026-11-19 from 23:18: the eye-scan build (`designs/b96_kr260_10g/eyescan`, build stamp 4fbc10e6, build ID a224f340, loaded over JTAG into SRAM), the KR260's SFP+ 10G-LR module in fibre
loopback, ten scans (`lpm_1`, `dfe_1`, `lpm_2` to `lpm_4`, `tx_d16`, `tx_d8`, `tx_post4`, `tx_post8`, `tx_pre4`). Every scan ended without an error, restored all 18 DRP words it had saved (`restore.ok` true), kept the link up
(`link.ok_throughout` true) and read SYSMON inside the recommended operating conditions at its start and end (for example `lpm_1`: 27.4 C at the start, VCCINT 0.715 V, VCCAUX 1.796 V, VCCBRAM 0.847 V). The conditions and the link were therefore not
the cause.

## Why no samples (diagnosis of brief 96D2; confidence stated in the report)
UG576 v1.7.1 Table 4-20 (printed pp. 230 to 232) says that for **UltraScale+** the eye-scan masks are **ten** 16-bit words each (`ES_QUALIFIER`, `ES_QUAL_MASK`, `ES_SDATA_MASK` are 160 bits; Table C-2 puts words 5 to 9 at 0x0E7 to 0x0F5, printed
p. 511). The brief-96D driver wrote five words of each, the UltraScale (80-bit) layout. Words 5 to 9 of `ES_QUAL_MASK` stayed at their start value, so the sample counter counted a cycle only when 80 further bits of
the previous cycle matched an all-zero `ES_QUALIFIER`; real data never does, so no cycle was counted, neither counter saturated, and each point ran into the host's 0.5 s timeout. That is also why each scan took about 525 s (1023 points x about
0.51 s) however short the prescale. The `probe.json` here read 0x03F to 0x04D and 0x03C, 0x04F, 0x097, 0x066 only: the words at 0x0E7 to 0x0F5 were not read, so their start value is **unconfirmed** (zero is expected, from the other words).
The status address (0x253), the run bit (ES_CONTROL[0], DRP 0x03C bit 10), ES_EYE_SCAN_EN / ES_ERRDET_EN (0x03C [9:8] = 0x0300, set by the build) and the DRP access path were checked against the guide and are not the cause (the DRP reads and the restore
worked). The fix is in the driver only (`flow/eyescan/hw.py`); no bitstream change.

## Files
- `20261119_231836/probe.json`, `program.json`: the read-only probe and the programming record. `<scan>.json`: the captures (`fda-capture-eye/1`); `<scan>.partial.jsonl`: the same points as written during the scan; `<scan>.run.txt`: the run's own output.
- `20261119_231836/summary.txt`: regenerated, `NO DATA: N/N points timed out` per scan. `summary_as_written.txt` is the original, byte for byte (its `open 0` lines are the misleading wording this brief removed).
- `20261119_231836/page.html`, `svg/`: the plots the script drew from the captures. They show empty grids (no point is measured); they are kept only because the script wrote them.
- `20261119_231836/git_heads.txt`: the commits of the tree that ran.

## Measured
Nothing about the link's eye. What the run does show: the DRP path, the save and restore of DRP words, the JTAG load and build-ID check, the link and the SYSMON readings worked as designed; and the timing of a point that never ends (about 0.51 s each).

## Reproduce
- The check that fails on this run: `python3 -m pytest flow/tests/test_eyescan_nodata.py` (it loads these ten captures and asserts they are NO DATA and that `capture.require_data` raises on each); or by hand
  `python3 -m flow.eyescan summary results/b96d/hw/20261119_231836` (prints `NO DATA` lines and exits 9; it rewrites `summary.txt`).
- The rerun on the board (owner, after the board is power-cycled): `bash _handoff/fpga_agent/run_96d_stage3.sh <loop lead metres> YES` (it begins with a short self-test scan and stops on NO DATA).

## Known gaps and limits
No eye exists for this link yet. The start value of the mask words 5 to 9 was not read. Whether the corrected masks give counts on the real part is untested until the rerun.
