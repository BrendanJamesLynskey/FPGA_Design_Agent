# results/b96f1b: reset synchroniser and alignment timeout/retry for build rm_gp_bypass (brief 96F1b); nothing ran on a board

Build `rm_gp_bypass` of `designs/b96_kr260_10g` (the GT elastic buffers bypassed, brief 96F1) with each buffer-bypass controller's reset driven as AMD's generated example design does it (a reset synchroniser in the controller's clock domain), and an alignment timeout of 30 ms (TX) or 130 ms (RX) that resets the controller and retries, up to three times, then flags **gave up**. Design notes: `designs/b96_kr260_10g/docs/design.md` section 12.1. The default build and `rm_gp` are unchanged. The pre-registered board test of 96F1 stands, with a dated amendment (`results/b96f1/preregistration.md`, "Amendment 2026-11-20"): a gave-up flag is a FAIL, and the AR 68177 reading of the latency prediction.

## Records
- `bypass_ctl/`: `run.sh`; `result.txt` (the scaled-timeout bench, `tb_bp_ctl.sv`, plus 96F1's `tb_bp_seq.sv` run unchanged against the new gate); `result_full.txt` (the real 30 ms and 130 ms values, one hung alignment each).
- `core_sim.sh`, `core_sim/`, `core_sim_summary.txt`: the whole core in xsim (real XPM macros, stand-in transceiver) in three scenarios: normal, one retry, never aligned (`out_*.log`; `summary.json`: tick-to-trade 13.5 clocks normal, 13.38 with one retry, the datapath unchanged; GT_BUF at link-up).
- `builds/rm_gp_bypass/`: `digest.json` (timing, utilisation, power, 29 gates, methodology), `run.json`, `cdc_summary.txt`, `methodology_summary.txt`, `stamp.txt`, `commit.txt`, `dirty.txt`, `wall.txt`, `run_vivado.log`. `build_one.sh` builds under a heavy slot and records; `record_extra.sh` adds the CDC and stamp records.
- Board script (not run): `_handoff/fpga_agent/run_96f1_stage1.sh <loop m> YES`, now pointing at this tree and this build's stamp.

## Measured
- **Build:** all 29 gates pass; WNS +0.118 ns, WHS +0.010 ns; 6,774 LUT, 19,127 FF, 0 BRAM, 0 DSP; 0.926 W (vectorless); `report_cdc` 0 critical and no waivers; methodology 0 critical, 15 warnings; stamp 86037ce1 (`builds/rm_gp_bypass/`). The 96F1 build of the same variant is in `results/b96f1/builds/rm_gp_bypass`; the comparison table is in the reset-drive subsection of `designs/b96_kr260_10g/docs/design.md`.
- **Simulation:** `bypass_ctl/result.txt` 29 checks and the 28 checks of 96F1's bench pass; `result_full.txt` 12 checks pass, with the timeout at 4,833,984 clocks (30.000 ms) for TX and 20,947,266 clocks for RX (130.001 ms at the nominal 6.2061 ns clock; the bench's RX clock is 6.2000 ns on purpose, unrelated to the TX clock). Whole core: GT_BUF reads 0x00000c00 at link-up (normal), 0x30110c00 after one retry on each side, 0x3f220000 with no link when no alignment ever finishes.

## Known gaps and limits
What a real GTHE4 does when an alignment hangs (whether resetting the controller alone recovers it), and how long a real alignment takes, are not known: the 30 ms and 130 ms limits and the three retries are AMD's example values and our choice, not measurements of this transceiver. A controller error is not retried. The retry counts clear when the reset helper's done drops, so they are read after the link is up. No loop-timing or SDM build.

## Reproduce
`results/b96f1b/build_one.sh rm_gp_bypass` then `results/b96f1b/record_extra.sh rm_gp_bypass` (heavy slot, about 25 minutes); `bash results/b96f1b/bypass_ctl/run.sh` and `bash results/b96f1b/bypass_ctl/run.sh build/bypass_ctl full`; `bash results/b96f1b/core_sim.sh`; tests: `python3 -m pytest designs/b96_kr260_10g/tests`.

## Illustrative or not measured
The transceiver in both simulations is a stand-in: the alignment time and what a real hang looks like are not simulated, and the 30 ms and 130 ms limits are AMD's example values, not measured on this transceiver. Power is vectorless.
