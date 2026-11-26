# pipe_reg datasheet (version 0.1.0, brief 151)

AXI4-Stream pipeline register with back-pressure: `N` slices in series of one of five kinds. Contract written without knowing the
larger design (owner decision 24); every figure below is measured in simulation (`results/b151/pipe_reg_measure.jsonl`, 2026-11-21) or
proved (`results/b151/pipe_reg_formal.json`). No figure here is a Vivado number.

## Ports and parameters

`aclk`, `aresetn` (active low, synchronous); slave port `s_axis_tvalid`, `s_axis_tready`, `s_axis_tdata[W]`, `s_axis_tlast`,
`s_axis_tkeep[W/8]`, `s_axis_tuser[TUSER_W]`; master port `m_axis_*` likewise. `W` 1..1024, `N` 0..16, `MODE` 0..4, `TLAST_EN`, `TKEEP_EN`
(W a multiple of 8), `TUSER_W` 0..64. A sideband that is off is not carried: its input is ignored, its output is 0. The carried signals travel as
one packed word `{tuser, tkeep, tlast, tdata}`.

## The five modes (what each does, measured)

| MODE | Kind | Latency | Throughput | Beats held when stalled | `s_axis_tready` | Ready response |
|---|---|---|---|---|---|---|
| 0 | forward-only: one shared enable `m_axis_tready \|\| !m_axis_tvalid` for all N stages | N | 1 | N | combinational from `m_axis_tready` (through the whole chain) | 0 |
| 1 | skid buffer: output register plus a side register that catches the beat arriving after tready falls | N | 1 | 2N | a flop in every slice | N |
| 2 | full register slice: two entries written alternately, valid and ready flops, data a 2:1 read | N | 1 | 2N | a flop in every slice | N |
| 3 | half-rate: one entry, accepts only into an empty slice | N | 1/2 | N | a flop in every slice | N |
| 4 | combinational-ready: one entry, `tready = !tvalid \|\| m_tready` | N | 1 | N | combinational, a chain of N | 0 |

`N = 0` is a wire. Modes 1 and 2 are cycle-identical (the same model matches both at every point); they differ in structure only.
Latency: counted from the edge that accepts a beat into an empty chain to the first clock the beat is visible at the master port
(one register is one clock). Ready response: clocks from `m_axis_tready` rising (chain full, source offering) to `s_axis_tready` rising.

## What a user could guess wrong

* **Which `tready` is combinational.** Modes 0 and 4 (and N = 0) pass `m_axis_tready` to `s_axis_tready` in the same clock: a long
  chain of them is a long combinational path backwards. Modes 1, 2 and 3 never do.
* **Mode 3 moves one beat per two clocks**, at every N, not N times worse.
* **Reset.** `s_axis_tready` is low in reset and for one clock after it in modes 1, 2 and 3; modes 0 and 4 follow `m_axis_tready` at once.
  AXI4-Stream 2.8 says a source raises `tvalid` only a clock after reset is released: the benches do it, and a source that does not
  sees a beat accepted that the reset then clears. A beat offered during reset is discarded whatever the handshake says.
* **Data is undefined while `tvalid` is low**: `tdata`, `tkeep`, `tlast` and `tuser` change freely then.
* **`tvalid` of the output never depends on `m_axis_tready`** (a flop in every slice); the N = 0 wire passes the source's `tvalid`.
* **Beats in the chain are lost by a reset**, none by back-pressure.
* **Skid buffer storage:** each slice holds up to two beats, so a chain of N skid slices can hold 2N beats; the source sees `tready`
  fall only after both places of the first slice are taken.
* **Packed word and parameters:** `W` is the tdata width only; the packed width is `W + TLAST_EN + (TKEEP_EN ? W/8 : 0) + TUSER_W`.

## Verification (the 139 standard)

Model `model.py` (a spec per slice kind, not a copy of the RTL); bench `tb/pipe_reg_cocotb.py` (cycle by cycle, random source and
sink profiles with bursts of stall, resets in mid-traffic, an independent scoreboard, the rule monitor `axi_tx/rtl/axis_rules.sv` on both ports, and a
check that `tvalid` does not move when `tready` is flipped within a clock); 32 parameter points (25 without sideband). Formal (`formal/`, k-induction at W = 4,
N up to 3): a beat number carried in the data proves no beat lost, repeated or reordered; the output holds while stalled; the stream
rules as SVA (`tb/axis_sva.sv`, bindable to any AXI4-Stream interface in a tool that reads assertions). 15 seeded faults
(`faults.yaml`), all caught by simulation; 12 refuted by the formal jobs, the other 3 are performance, liveness or valid-gating bugs that
no safety property on the ports can see (listed in `results/b151/pipe_reg_formal.json`). Testplan: `verif/testplan.yaml`.

## Against the vendor

See [docs/partitioning_study.md](../../docs/partitioning_study.md), section 3. The comparison with AMD's AXI Register Slice
(latency, bubbles, area, Fmax per register configuration) is queued (`partition/vendor/`); until it is read, the mapping from AMD's
configurations to ours is a hypothesis.

## Integration guidance

Default boundary between two sub-modules: MODE 1, N 1. Use MODE 4 or 0 only on a chain of one or two where the extra clock of ready
latency matters and the combinational ready was timed. Use MODE 3 where one beat per two clocks is enough. Put the slice at the
producer's output (the AXI practice) and leave the placer to move it; whether one or two stages are needed across a long wire is
question Q2 of the study. Do not put logic between a slice's output and the next block's first register.
