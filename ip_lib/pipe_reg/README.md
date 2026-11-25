# pipe_reg 0.1.0

AXI4-Stream pipeline register with back-pressure: N register slices in series of one of five kinds (forward-only, skid buffer, full register slice, half-rate slice, combinational-ready slice), tdata plus optional tlast, tkeep and tuser. Datasheet: ip_lib/pipe_reg/DATASHEET.md.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated clock by clock against a Python model with an AXI4-Stream rule monitor (cocotb, Icarus Verilog 12) at 5 modes and several depths; data and AXI4-Stream rules proved by k-induction at W = 4 (SymbiYosys); 15 of 15 seeded faults caught by simulation; not built with Vivado yet (queued); not run on a board.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `W` | 32 | 1..1024 | tdata width in bits |
| `N` | 1 | 0..16 | slices in series; 0 is a wire (no register, no latency, s_axis_tready = m_axis_tready) |
| `MODE` | 1 | 0, 1, 2, 3, 4 | 0 forward-only, 1 skid buffer, 2 full register slice, 3 half-rate slice, 4 combinational-ready slice |
| `TLAST_EN` | 0 | 0, 1 | carry tlast |
| `TKEEP_EN` | 0 | 0, 1 | carry tkeep (W must be a multiple of 8) |
| `TUSER_W` | 0 | 0..64 | width of tuser carried; 0 = none |

Constraints: `TKEEP_EN == 0 or W % 8 == 0`.

Out-of-space values fail at elaboration with `$error` (tested: `W=0`, `W=1025`, `N=-1`, `N=17`, `MODE=5`, `MODE=-1`, `TLAST_EN=2`, `TUSER_W=65`).

## Interfaces

- `s_axis`: axi4-stream (dir slave, tdata W). tlast, tkeep (W/8 bits) and tuser (TUSER_W bits) are carried when TLAST_EN, TKEEP_EN and TUSER_W enable them; a sideband that is off is ignored at the input and 0 at the output
- `m_axis`: axi4-stream (dir master, tdata W). m_axis_tvalid is a flop in every mode; a beat offered and not taken stays offered unchanged

Clocks: `aclk`. Reset: `aresetn`, active low, synchronous.

## Latency and throughput

- forward: N clocks in every mode: a beat accepted into an empty chain at edge t is visible at m_axis after edge t plus N-1 more edges (measured at every point; 0 for N = 0)
- ready response: clocks from m_axis_tready rising (chain full, source offering) to s_axis_tready rising: 0 for modes 0 and 4 and for N = 0 (combinational), N for modes 1, 2 and 3 (measured)
- ready after reset: s_axis_tready is low in reset and for one clock after it in modes 1, 2 and 3; modes 0 and 4 follow m_axis_tready at once (a source must hold tvalid low in reset and for one clock after, AXI4-Stream 2.8)
- throughput: one beat per clock in modes 0, 1, 2, 4 and for N = 0; one beat per two clocks in mode 3 at any N (measured); stored beats when the sink stops: N in modes 0, 3 and 4, 2N in modes 1 and 2

## Evidence

cocotb against ip_lib/pipe_reg/model.py, clock by clock: s_tready, m_tvalid and the packed word every clock at 25 parameter points with random source and sink profiles and mid-run resets, an independent in-order scoreboard, the AXI4-Stream rule monitor of axi_tx/rtl/axis_rules.sv on both ports, and a check that tvalid does not move when tready is flipped within a clock; the declared latency, throughput, capacity and ready response checked against measured ones. Formal: SymbiYosys k-induction proofs of order and loss (a beat number carried in the data), stability while stalled and the stream rules as SVA (tb/axis_sva.sv, slang front end). Every assertion is labelled and paired with a cover of its own antecedent (a cover task per mode); sidecars formal/pipe.rigour.yaml and formal/pipe_sva.rigour.yaml and records in results/143c (brief 202). Tests: `ip_lib/pipe_reg/tb/test_pipe_reg_rtl.py`, `ip_lib/pipe_reg/tb/test_pipe_reg_formal.py`.

Try it: `python3 -m pytest ip_lib/pipe_reg/tb/test_pipe_reg_rtl.py ip_lib/pipe_reg/tb/test_pipe_reg_formal.py` (the formal jobs need SymbiYosys on PATH; they are skipped without it).

Parameter points simulated: `W=16, N=1, MODE=0`; `W=16, N=2, MODE=1`; `W=16, N=5, MODE=2`; `W=16, N=2, MODE=3`; `W=16, N=2, MODE=4`; `W=16, N=0, MODE=1`; `W=1, N=2, MODE=1`; `W=64, N=2, MODE=2`; `W=8, N=16, MODE=1`; `W=32, N=3, MODE=1, TLAST_EN=1, TKEEP_EN=1, TUSER_W=4`; `W=8, N=1, MODE=4, TLAST_EN=1, TUSER_W=3`.

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `comb_ready_ignores_take` | the comb slice's s_ready no longer depends on m_ready: it works but at half throughput and with a different ready timing | caught |
| `comb_reset_keeps_valid` | reset does not clear the comb slice's valid: a beat survives a reset | caught |
| `half_ready_stale` | the half slice's ready register is computed from the old valid: it accepts a second beat into a full slice | caught |
| `half_drop_unready` | the half slice empties itself without waiting for m_ready: a stalled beat is lost | caught |
| `skid_ready_too_late` | the skid buffer stays ready one clock too long: the side register is overwritten | caught |
| `skid_park_dropped` | the skid buffer never parks the beat that arrives after m_ready falls: it is lost | caught |
| `skid_drain_wrong_source` | the side register drains into the output register from the wrong source: the parked beat is replaced by the input | caught |
| `full_write_pointer_stuck` | the full slice's write pointer stops alternating: later beats overwrite the same entry | caught |
| `full_read_swapped` | the full slice reads the entries in the wrong order: two beats swap | caught |
| `full_ready_overfill` | the full slice never says not-ready: a third beat overwrites an unread one | caught |
| `fwd_enable_needs_ready` | the shared enable ignores an empty output: a sink that waits for valid before ready never sees the beat | caught |
| `fwd_first_stage_free_running` | the first stage's data register loads on every clock, not only when enabled: a stalled beat is overwritten | caught |
| `chain_output_ready_ignored` | the last slice is told the sink is always ready: beats are lost while the sink stalls | caught |
| `wire_ready_constant` | the N = 0 wire tells the source it is ready whatever the sink says | caught |
| `fwd_valid_gated_by_ready` | the output's tvalid depends on tready (forbidden by AXI4-Stream): the bench's tready flip within a clock sees it; the port rules cannot, because a gated valid never looks withdrawn | caught |

## Boundary and reuse

- Registered outputs: m_axis_tvalid is a flop in every slice; m_axis_tdata is a flop in modes 0, 1, 3 and 4 and a 2:1 read of two flops in mode 2; s_axis_tready is a flop in modes 1, 2 and 3 and combinational from m_axis_tready in modes 0 and 4.
- Clock crossings: none (one clock).
- Part, board or pin: none.
- Depends on: nothing.

## Cost table

pending: out-of-context Vivado runs are queued in partition/sweep.py and _handoff/fpga_agent/vivado_later_queue.md; Yosys counts for 64-bit boundaries are in results/b151/part_sys_yosys.json.

Licence: MIT (this repository).

## Known gaps and limits

- One clock domain; no packet-level behaviour (tlast is only carried); tvalid of an N = 0 wire follows the source, so the AXI4-Stream rules hold there only if the source keeps them; the formal proofs are at W = 4 with the sideband off (the sideband moves as part of the packed word and is covered by simulation).
- Board: no board run of this entry is recorded; its evidence is simulation.
- Cost: no out-of-context characterisation (no `characterisation:` in ip.yaml), so resources, Fmax and power are not measured for this entry.
- No Vivado number: Fmax and resources per mode and stage count are expectations until the queued runs, and the comparison with AMD's AXI Register Slice is hypothesis until the vendor run (partition/vendor).
- Tvalid independence from tready is established by construction and by a simulation check, not by a property on the ports (a port-level property cannot see it).

## Next steps

1. Run the queued partition sweep and the vendor slice build, fill the cost table, and replace the draft rules in the knowledge base with measured ones.
2. Add a reverse-registered mode if the owner or the vendor comparison shows a use for one.

## History

- 0.1.0 (2026-11-21): First version (brief 151). See README.md.

Full entries: [CHANGELOG.md](CHANGELOG.md).
