# results/b96f1: GT buffer bypass on the KR260 (brief 96F1), stage 0 probe and stage 1 build; nothing ran on a board

Two builds of `designs/b96_kr260_10g` (the control `rm_gp` and the bypass build `rm_gp_bypass`), the Wizard probe, two simulations, the pre-registered board test and the script the owner runs. Design notes: `designs/b96_kr260_10g/docs/design.md` section 12.

## Records
- `wizard_probe/`: stage 0 (README with the findings: bypass options, ports, dynamic fractional-N, attributes in the generated wrapper and in both implemented netlists).
- `builds/rm_gp/`, `builds/rm_gp_bypass/`: `digest.json` (timing, utilisation, power, 29 gates, methodology), `run.json` (wall time, memory, stamp), `cdc_summary.txt`, `methodology_summary.txt`, `stamp.txt`, `commit.txt`, `dirty.txt`, `wall.txt`, `run_vivado.log`. `build_one.sh` builds one under a heavy slot and records; `record_extra.sh` adds the CDC and stamp records.
- `bypass_seq/`: the buffer-bypass start-up sequence with AMD's own controllers and our gate (`result.txt`: 28 checks pass; `run.sh`).
- `core_sim/`, `core_sim.sh`: the whole core in xsim (real XPM macros) with a stand-in transceiver: link up, 8 orders, tick-to-trade and receive-start path against `rm_gp` (`summary.json`).
- `preregistration.md`: the board test, written before any board time. Board script: `_handoff/fpga_agent/run_96f1_stage1.sh <loop m> YES`; driver `designs/b96_kr260_10g/host/b96f1_bypass.py` (tests: `tests/test_b96f1_bypass.py`).

## Measured
- **Both builds meet timing and pass every flow gate (gates.json in the digest):** `rm_gp` WNS +0.055 ns, WHS +0.011 ns, 6,842 LUT, 18,940 FF, 1.124 W (vectorless), stamp 6fd8a2bf; `rm_gp_bypass` WNS +0.090 ns, WHS +0.010 ns, 6,878 LUT (+36), 19,006 FF (+66), 0.933 W (vectorless), stamp b2a7aeea. `report_cdc`: no critical row in either, no waivers; methodology 0 critical.
- **Netlist attributes** (post_route, GTHE4_CHANNEL X0Y6): TXBUF_EN, RXBUF_EN FALSE; TX_XCLK_SEL TXUSR, RX_XCLK_SEL RXUSR; TX_FIFO_BYP_EN 1; TX_PROGDIV_CFG 16 (all TRUE, TXOUT, RXDES, 0, 0 in `rm_gp`).
- **Sequence simulation:** the Wizard's controllers start by themselves on the reset-done edge and leave the previous sequence's done high for 6 to 12 clocks, which the gate holds off; an alignment error holds the paths in reset (28 of 28 checks).
- **Whole-core simulation:** tick-to-trade 13.4 clocks for both builds (8 orders, phase 0); link up with the bypass-done delayed by 100 or 2,000 clocks.

## Illustrative or not measured
The transceiver in both simulations is a stand-in: the alignment time, the phase and the latency saving are not simulated (prediction only: E falls 2.9 to 4.5 clocks, third-party GTY figures, UNCONFIRMED for this GTH). Power is vectorless. No bitstream was loaded on a board.

## Known gaps and limits
The controllers' reset drive is our choice (UNCONFIRMED against AMD's example). TX alignment is exercised on the board only by full GT restarts (the driver does 20). The ppm registers have no effect in this build (`TXPIPPMPD_VAL = 1`). A fresh `rm_gp` was rebuilt for the comparison (it differs from 96E's record by tree, not by design).

## Reproduce
`results/b96f1/build_one.sh rm_gp_bypass` then `results/b96f1/build_one.sh rm_gp` (about 25 minutes each, 4.4 GiB, heavy slot), then `results/b96f1/record_extra.sh <name>`; `bash results/b96f1/bypass_seq/run.sh`; `bash results/b96f1/core_sim.sh` (and `WORK=... PHASES=0 bash results/b96e/core_lat_sim.sh 1:1` for the `rm_gp` side); the probe: `wizard_probe/README.md`; tests: `python3 -m pytest designs/b96_kr260_10g/tests/test_b96f1_bypass.py`.
