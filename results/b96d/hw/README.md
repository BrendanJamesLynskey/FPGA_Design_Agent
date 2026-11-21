# results/b96d/hw: KR260 eye-scan runs (briefs 96D, 96D2): the first measured eye, and the two runs that measured none

**`20261120_105134/` is the first measured receive eye of the KR260 10G link** (fibre loopback, 10G-LR module, eye-scan build stamp 4fbc10e6, build ID a224f340). It needed two fixes found on the board: the
ten-word UltraScale+ masks (brief 96D2) and forcing the eye-scan 4T clock phase (USE_PCS_CLK_PHASE_SEL = 1, ES_CLK_PHASE_SEL = 1, DRP 0x094 [10]/[11]; UG576 v1.7.1 Table 4-20 gives this remedy). The runs below it measured no eye:
`20261119_231836/` counted no samples (five-word masks), and `20261120_093417/` counted samples on the wrong clock phase (about half of all bits "in error" at every offset).

## Records
- `20261120_105134/`: the measured run (`run_96d_stage3.sh`, 2026-11-20 from 10:51): `selftest.json` and ten scans (`lpm_1` to `lpm_4`, `dfe_1`, `tx_d16`, `tx_d8`, `tx_post4`, `tx_post8`, `tx_pre4`), `summary.txt`, `svg/`, `page.html`,
  `probe.json` (34 DRP words read before any write, including 0x0E7 to 0x0F5 = 0 and 0x094 = 0), `program.json`, `git_heads.txt`. The self-test chose ES_CLK_PHASE_SEL = 1 at its first trial (`selftest.json` `clk_phase`).
- `20261120_maskprobe/mask_probe.json` (`tools/eyescan_mask_probe.py`): 30 placements of the unmasked window of ES_SDATA_MASK, eye centre and both edges each. Only bits [79:48] (current cycle, errors summed) and [159:128] (previous cycle, one per cycle) count;
  that matches UG576's description, so the 96D2 layout {80'b1, 32'b0, 48'b1} is right. Every counting window gave the same result at the centre and at the edges.
- `20261120_phaseprobe/phase_probe.json` (`tools/eyescan_phase_probe.py`): horizontal and vertical sweeps at the default phase, with the 4T clock phase forced to 0 and to 1, and with ES_ERRDET_EN off. Only phase 1 shows an eye
  (no errors from -24 to +24 counts at prescale 0); the default, phase 0 and ERRDET off all read about half the bits as errors everywhere.
- `20261120_093417/`: the first rerun, stopped by the planner after the self-test and four scans had saturated the error counter at every point: `probe.json`, `program.json`, the `run.txt` files and `git_heads.txt` are kept (the script was stopped before it wrote `summary.txt`);
  its capture files are **not** committed, because they look like data and are not (wrong 4T phase).
- `20261119_231836/`: the 2026-11-19 run with no data (below).

## Measured (20261120_105134, fibre loopback, one board, one module, room temperature)
| scan | equaliser | depth | width | height |
|---|---|---|---|---|
| lpm_1, lpm_2, lpm_3, lpm_4 | LPM | 1e-09 | 0.71875 UI | 360.0 mV (at that run's vertical limit, `vs_range` 0; see the tall scan below: 470.4 mV, closing inside the wider reach) |
| dfe_1 | DFE | 1e-09 | 0.75 UI | 288.0 mV |
| tx_d16, tx_d8, tx_post4, tx_post8, tx_pre4 | LPM | 1e-07 | 0.71875 UI | 360.0 mV |

The four LPM repeats agree to one grid point. The 360 mV height is a lower bound only: that run's vertical range setting (`vs_range` 0, 1.5 mV per code) stops at +-180 mV and the eye is still error-free there. The tall scan below (`vs_range` 3) supersedes it: 470.4 mV. The TX drive variants change nothing measurable at
1e-07 on this short, clean loop. Width is in the scan's own grid (2 counts = 1/32 UI). The scan sees the eye after the equaliser, inside the receiver, not at the pins.

## Tall LPM scan (20261120_221528, board run 2026-11-21, one run)
`20261120_221528/` holds `selftest.json` and `tall_lpm.json` (with `.partial.jsonl`, `.run.txt`, `summary.txt`, `svg/`, `probe.json`, `program.json`, `git_heads.txt`): the same fibre loopback with the scan's vertical range raised to `vs_range` 3 (2.8 mV per code, nominal, from UG576; not calibrated on this part). The self-test chose the 4T clock phase 1.
The scan measures the eye after the LPM equaliser, inside the receiver, not at the pins.

| scan | equaliser | depth | width | height |
|---|---|---|---|---|
| selftest | LPM | 1e-06 | 0.5 UI | 240.0 mV (`vs_range` 0) |
| tall_lpm | LPM | 1e-09 | 0.71875 UI | 470.4 mV |

At the centre column the error-free region runs from -80 to +88 codes (about -224 to +246 mV), so the eye closes inside the +-336 mV reach (+-120 codes at 2.8 mV): this height is a measured closure, not a scan-range limit. mV values use the nominal UG576 mV per code; one board, one module, one run, room temperature.

---

# The 2026-11-19 run (brief 96D): NO EYE WAS MEASURED

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

## Measured in 2026-11-19
Nothing about the link's eye. What the run does show: the DRP path, the save and restore of DRP words, the JTAG load and build-ID check, the link and the SYSMON readings worked as designed; and the timing of a point that never ends (about 0.51 s each).

## Reproduce
- The check that fails on this run: `python3 -m pytest flow/tests/test_eyescan_nodata.py` (it loads these ten captures and asserts they are NO DATA and that `capture.require_data` raises on each); or by hand
  `python3 -m flow.eyescan summary results/b96d/hw/20261119_231836` (prints `NO DATA` lines and exits 9; it rewrites `summary.txt`).
- The board runs (owner): `bash _handoff/fpga_agent/run_96d_stage3.sh <loop lead metres> YES` (it begins with a short self-test scan that chooses the 4T clock phase and stops on NO DATA); the probes: `python3 tools/eyescan_mask_probe.py --help`, `python3 tools/eyescan_phase_probe.py --help` (board, owner).
- Tables of this README: `python3 -m flow.eyescan summary results/b96d/hw/20261120_105134`.

## Known gaps and limits
One board, one module, a 0.17 m fibre loopback at room temperature: the eye says little about a real link; a NIC link is the next test. The 20261120_105134 LPM height is a lower bound (scan range); the tall scan of 20261120_221528 measured it as 470.4 mV. Why the default 4T clock phase is wrong on this part is not known; the driver now picks the phase that gives an error-free eye centre and records it. The 2026-11-19 run's own gaps: none left open (words 5 to 9 read as 0 on 2026-11-20; the corrected masks count on the real part).
