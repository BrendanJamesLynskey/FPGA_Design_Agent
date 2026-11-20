# results/b113: the ML decision stage in the 10G trading path (brief 113)

Records of build `rm_gp_ml` of `designs/b96_kr260_10g`: whole-core simulation (xsim 2026.1, AMD's real XPM macros, the GT stand-in), the Vivado 2026.1 build for the KR260 and the in-context timing of the stage.
**Synthetic data only.** Nothing ran on a board; the board test is pre-registered ([preregistration.md](preregistration.md)) and the owner's script is `_handoff/fpga_agent/run_113_ml_stage3.sh` (never run).
Design notes: [designs/b96_kr260_10g/rm_gp_ml/docs/ml_stage.md](../../designs/b96_kr260_10g/rm_gp_ml/docs/ml_stage.md) (which block and why, the arrangement, the numbers), registers:
[ml_registers.md](../../designs/b96_kr260_10g/rm_gp_ml/docs/ml_registers.md). Every number in the notes is in [summary.json](summary.json), made by `python3 results/b113/summary.py` from the records below (`--check` in CI).

## Records
- `ml_sim.sh`, `tb_ml_core.sv` (`designs/b96_kr260_10g/rm_gp_ml/sim/`), `gth_wiz_model113.sv`: the whole core in xsim with a synthetic feed injected on the receive words, for build `ml` or the unmodified `rm_gp` (`base`); `LOOP=<n>` runs the board's own stream instead.
- `lat_all.sh`, `lat/*.log`, `lat_summary.py`, `latency.json`: tick-to-trade at four receive-clock phases, for the control, shadow, veto and the counterfactual holds of 1 and 2 clocks.
- `twin_runs.sh`, `ml_check.py`, `loop_check.py`, `twin/`: the bit-exactness runs (per-frame features, class, decision and veto, order count, stage counters against the Python twin; the board stream against the board driver's prediction).
- `build_one.sh`, `builds/rm_gp_ml/` (`digest.json`, `run.json`, `cdc_summary.txt`, `timing_summary_head.txt`, `commit.txt`, `dirty.txt`, `wall.txt`, `run_vivado.log`), `stage_timing.tcl`, `builds/rm_gp_ml/stage/` (`stage_timing.json`, `stage_timing_summary.txt`, `utilization_hier.txt`).

## Measured (from summary.json)
- **Tick-to-trade in simulation: 12.93 clocks without the stage, 12.93 with it in shadow and in veto mode, at every phase: the stage adds 0.00 clocks.** The counterfactual in which the class is made after the message arrives adds 1.1
  (hold 1) and 2.0 clocks (hold 2).
- **Bit-exact:** 350 frames of a mixed synthetic feed, 0 mismatches in feature vector, class, hit, decision and veto; order counts 25 (veto) and 78 (shadow) equal the twin's, the unmodified `rm_gp` sends the same 78 in shadow
  mode; stage counters equal the twin's. The board's stream gives 49 down, 1 up; 1 order in veto mode, 50 in shadow mode.
- **Build rm_gp_ml:** 29 of 29 gates, setup +0.220 ns, hold +0.010 ns at the 6.206 ns core clock, 0 critical in `report_cdc`, DRC and methodology, 8,312 LUT, 22,136 FF, 0 BRAM, 0 DSP, 1.149 W vectorless, stamp 22c35e72 (input commit
  a3f9a4a2 in `commit.txt`, working tree clean; the build inputs have not changed since: `git diff` of the RTL, build.yaml, constraints, IP script and flow is empty, and `flow/manifest.py show` gives the same build ID, 26dc74ce, at that commit and now).
- **Stage timing in context:** the worst setup path of any part of the stage has +0.556 ns of slack (the trees' path +0.757 ns).

## Board result, 2026-11-21 (rm_gp_ml, stamp 22c35e72, build ID 0ba30107 read back over JTAG): PASS

`hw/20261120_220813/rm_gp_ml/` (stage3.json, sweeps.json, session.json). How the numbers are defined (all from FPGA counters at the 6.2061 ns core clock, median of the per-link minimum over 100 link restarts, fibre loopback with the 0.17 m OS2 lead and the 10G-LR module in J24): **E** is one pass out and back through the transmit and receive paths (MAC, PCS, GT, optics, fibre); **L** is the whole trading loop, a price word in to an order out and back, which crosses the transceiver twice, so L = 2E + D; **D** is the decision logic between the two crossings; **tick-to-trade** is L - E, first bit in to first bit out at the SFP+ pins as seen by FPGA counters, optics included (not a wire-to-wire STAC-T0 figure; see docs/latency_definitions.md).

| | rm_gp without the ML stage (96E) | rm_gp_ml (ML stage in the path) | change |
|---|---|---|---|
| E | 21.0 | 21.0 | 0.0 |
| L | 54.0 | 53.0 | -1.0 (inside the pre-registered 1-clock band; 96E's per-link L minimum ranged 53 to 55, so this is spread, not a gain) |
| D | 12.0 | 11.0 | |

Why the stage adds no clock: the ML class is computed ahead of time from book state that changes only when a good frame ends; the order path reads the class from a register, so nothing is added between the price word arriving and the order leaving. The stage's counters equal the Python twin exactly in both the shadow and the veto sweeps. Safety counters 0; inside the operating conditions (28.4 C at the end); laser off at the end. The model was trained on synthetic data, so this shows the latency cost of an ML decision stage, not a trading edge.

## Reproduce
Each step below writes the records named above; the simulations need Vivado 2026.1's xsim and take one to three minutes a run, the build needs a heavy slot (take_heavy_slot.sh) and about 37 minutes, and the tests need only Python, Icarus Verilog and Verilator.
```
python3 -m pytest -q designs/b96_kr260_10g/rm_gp_ml/tests         # twin, ml_stage in Icarus, register map, driver on a fake board, lint (CI)
results/b113/lat_all.sh <stream dir> <out dir>                      # needs Vivado 2026.1 for xsim; stream: python3 -m designs.b96_kr260_10g.rm_gp_ml.model.stream lat <dir>
results/b113/twin_runs.sh                                           # the bit-exactness runs
results/b113/build_one.sh rm_gp_ml                                  # the build (heavy slot, about 37 minutes)
vivado -mode batch -source results/b113/stage_timing.tcl -tclargs <post_route.dcp> <out dir>
```

## Known gaps and limits
- Not on a board: the transceiver in simulation is a stand-in, so the latency result is "no clock added in the fabric"; the board measurement is pre-registered and not run.
- The control build `rm_gp` was not rebuilt in this brief; resource and slack comparisons use brief 96F1's rebuild (stamp 6fd8a2bf), made at an earlier main.
- Latency runs have 10 orders per phase and four phases (the receive-clock phase sweep of brief 96E); the bit-exactness stream has 350 observed frames from one planted-signal generator, so it tests the hardware against the twin, not the model's usefulness.
- One instrument, first message of a frame only, frames at least 10 clocks apart: see docs/ml_stage.md section 7.
