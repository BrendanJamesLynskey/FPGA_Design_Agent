# axi_reg_slice 0.1.0

AXI4 and AXI4-Lite register slices for all five channels (AW, W, B, AR, R): one pipe_reg chain per channel with its own mode, so the channels are registered independently as in AMD's AXI Register Slice. Modules axil_reg_slice and axi4_reg_slice.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

**Verification: not assessed: no requirements recorded (no verif/testplan.yaml), so nothing here is traced to a requirement.** [VERIFIED.md](VERIFIED.md) is the generated, hash-pinned record; [what the label means](../../docs/verified.md).

Status: simulated clock by clock against the pipe_reg model on all five channels (cocotb, Icarus Verilog 12) at seven per-channel mode mixes; 6 of 6 seeded faults caught; no formal proof of its own (every channel is a pipe_reg_core chain, proved in ip_lib/pipe_reg); not built with Vivado yet (queued); not run on a board.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `ADDR_W` | 32 | 1..64 | address width |
| `DATA_W` | 32 | 8, 16, 32, 64, 128, 256, 512, 1024 | data width in bits |
| `N` | 1 | 0..16 | slices in series on every channel; 0 is a wire |
| `MODE_AW` | 1 | 0, 1, 2, 3, 4 | pipe_reg mode of the AW channel |
| `MODE_W` | 1 | 0, 1, 2, 3, 4 | mode of the W channel |
| `MODE_B` | 1 | 0, 1, 2, 3, 4 | mode of the B channel |
| `MODE_AR` | 1 | 0, 1, 2, 3, 4 | mode of the AR channel |
| `MODE_R` | 1 | 0, 1, 2, 3, 4 | mode of the R channel |

Out-of-space values fail at elaboration with `$error` (tested: `N=17`, `N=-1`, `MODE_AW=5`, `MODE_R=-1`).

## Interfaces

- `s_axi`: axi4-lite (dir slave). awaddr, awprot, wdata, wstrb, bresp, araddr, arprot, rdata, rresp; axi4_reg_slice (the second module) adds id, len, size, burst, lock, cache, qos, wlast, rlast and does not carry region or user signals
- `m_axi`: axi4-lite (dir master)

Clocks: `aclk`. Reset: `aresetn`, active low, synchronous.

## Registers

None: a register slice passes AXI4-Lite transfers through and has no registers of its own.

## Latency and throughput

- per channel: N clocks on each of the five channels in every mode (requests AW, W, AR slave to master; responses B, R master to slave); the channels are independent and are not reordered against each other
- ready: as pipe_reg for the chosen mode
- throughput: as pipe_reg per channel: one beat per clock except mode 3 (half), one beat per two clocks

## Evidence

cocotb on all five channels at once, each channel against the pipe_reg model clock by clock with its own random source and sink and an in-order scoreboard, and a check that no channel's valid depends on its ready. Tests: `ip_lib/axi_reg_slice/tb/test_axi_reg_slice_rtl.py`.

Try it: `python3 -m pytest ip_lib/axi_reg_slice/tb/test_axi_reg_slice_rtl.py`.

Parameter points simulated: `N=1`; `N=2, MODE_AW=2, MODE_W=3, MODE_B=4, MODE_AR=0`; `N=0`; `N=3, ADDR_W=12, DATA_W=64, MODE_AW=3, MODE_W=3, MODE_B=3, MODE_AR=3, MODE_R=3`.

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `wstrb_wdata_swapped` | the write strobe is taken from the wrong bits of the packed word | caught |
| `bresp_dropped` | the write response is replaced by OKAY | caught |
| `rready_not_forwarded` | the read-data channel ignores the master's rready | caught |
| `araddr_offset` | the read address is taken one bit off | caught |
| `axi4_rlast_swapped` | rlast is taken from rresp | caught |
| `axi4_awlen_dropped` | the burst length is forced to one beat | caught |

## Boundary and reuse

- Registered outputs: as pipe_reg for each channel (valid a flop in every mode).
- Clock crossings: none.
- Part, board or pin: none.
- Depends on: pipe_reg.

## Cost table

pending: no out-of-context Vivado run yet (queued with the sweep); the cost of one channel is the pipe_reg cost at its width.

Licence: MIT (this repository).

## Known gaps and limits

- No region or user signals and no AXI3 wid; the five channels have separate reset-time behaviour only through their modes; no outstanding-transaction logic (this is a register slice, not an interconnect).
- Board: no board run of this entry is recorded; its evidence is simulation.
- Cost: no out-of-context characterisation (no `characterisation:` in ip.yaml), so resources, Fmax and power are not measured for this entry.
- No protocol-level bench with an AXI4 checker on the five channels together: each channel is checked as a stream (valid, ready, hold), not for AXI4 transaction rules such as write-data before address.
- The AXI4 module is checked at default and small parameter points only.

## Next steps

1. Compare each mode with AMD's AXI Register Slice build (partition/vendor) and state the differences in this entry.
2. Add the AXI4 checker of axi_tx to the five-channel bench.

## History

- 0.1.0 (2026-11-21): First version (brief 151). See README.md.

Full entries: [CHANGELOG.md](CHANGELOG.md).
