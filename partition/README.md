# partition: the synthetic large system, the sweep and the vendor comparison (brief 151)

A parameterised system of sub-modules with boundaries of every kind in between, so that the questions of `docs/partitioning_study.md`
(when to register between sub-modules, whether one stage suffices, which handshake) can be answered by measurement. Vivado runs are
written and queued (decision 27), not run: what exists now is simulation (latency, throughput and data) and Yosys area, recorded in
`results/b151/`.

## Files

| File | What it is |
|---|---|
| `rtl/part_stage.sv` | one sub-module: combinational logic of stated depth `D` on a `W`-bit word, no state |
| `rtl/part_sys.sv` | `NM` sub-modules in a chain with `NM + 1` boundaries chosen by `HS` (0 forward-only, 1 skid, 2 full slice, 3 half slice, 4 combinational ready, 5 plain registers, 6 credit link) and `STAGES`; `KEEP` puts `keep_hierarchy` on the sub-modules |
| `tests/test_partition_sim.py`, `tests/part_cocotb.py` | latency, throughput and data of the system at every boundary kind and depth, against the figures the models declare |
| `sweep.py` | the 90 Vivado points (parts, boundary kind, stages, `KEEP`, retiming, distance, number of sub-modules), the Yosys area run, the queue rows, the command for one point |
| `run_point.tcl` | one point, out of context, non-project: pblocks from one corner of the device to the other, place, route, WNS, utilisation, the worst boundary path and its route share, compile time. Not run; checked for Tcl syntax only |
| `ssi/query_ssi_parts.tcl` | which installed parts have more than one SLR (result: none; `results/b151/ssi_parts_query.txt`) |
| `vendor/vendor_slice_ooc.tcl`, `vendor/vendor_slice_tb.sv` | AMD's AXI Register Slice IP in each register configuration the tool offers (area, Fmax), and an xsim bench for its latency, throughput and bubbles. Not run |

## The sweep and the questions

`python3 partition/sweep.py --list` names the 90 points; each belongs to one question: `q1` (stages 0-3, three distances), `q3` (hierarchy
and retiming), `q4` (the seven boundary kinds at one and two stages), `q5` (no pblocks), `q6` (4 and 16 sub-modules). Parts: the
Artix-7 xc7a100t at 4.0 ns and the K26 xck26 at 2.5 ns (starting points; every point records WNS). Distance `DIST` runs the sub-modules'
pblocks along the line from the lowest to the highest clock region (0 the same region, 1 opposite corners, -1 no pblocks).
The expected outcome of each is in `docs/partitioning_study.md` section 2. The queue rows are in
`_handoff/fpga_agent/vivado_later_queue.md`; the planner runs a group (`--run-group q1_a7`) when a slot is free, after taking it with
`take_heavy_slot.sh` ("Vivado impl" and the declared peak in the text).

Per-sub-module placement: `run_point.tcl` takes `TARGETS` (one entry per sub-module: an SLR name or a clock region); `sweep.py --run-point <name> --targets "SLR0 SLR1"` passes it (for phase 1, multi-die).

## Known gaps and limits

The Tcl is untested against Vivado. The simulated system is smaller (4 sub-modules) than the Vivado one (8). Yosys area is a count, not a
timing. SLR crossings cannot be measured on the owner's parts (neither has an SLR).
