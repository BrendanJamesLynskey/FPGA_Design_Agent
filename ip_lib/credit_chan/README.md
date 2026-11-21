# credit_chan 0.1.0

Credit-based pipelined channel between two AXI4-Stream ports: LF plain register stages forward, a receiver buffer of CREDITS entries, LB register stages for the credits coming back. Use it only where valid/ready does not fit (long pipelines, bare forward wires); datasheet: ip_lib/credit_chan/DATASHEET.md.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated clock by clock against a Python model with an AXI4-Stream rule monitor (cocotb, Icarus Verilog 12) at 19 points below, at and above the credit round trip; credit conservation, buffer bounds, order and the stream rules proved by k-induction at W = 4 (SymbiYosys); 12 of 12 seeded faults caught; not built with Vivado yet (queued); not run on a board.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `W` | 32 | 1..1024 | tdata width in bits |
| `CREDITS` | 8 | 1..1024 | credits at reset = receiver buffer entries; full throughput needs CREDITS >= LF + LB + 2 |
| `LF` | 1 | 0..8 | forward register stages between sender and receiver buffer (0: straight into the buffer) |
| `LB` | 1 | 0..8 | register stages on the credit return (0: counted in the clock the beat leaves) |
| `TLAST_EN` | 0 | 0, 1 | carry tlast |
| `TKEEP_EN` | 0 | 0, 1 | carry tkeep (W must be a multiple of 8) |
| `TUSER_W` | 0 | 0..64 | width of tuser carried; 0 = none |

Constraints: `TKEEP_EN == 0 or W % 8 == 0`.

Out-of-space values fail at elaboration with `$error` (tested: `W=0`, `W=1025`, `CREDITS=0`, `CREDITS=1025`, `LF=-1`, `LF=9`, `LB=-1`, `LB=9`, `TLAST_EN=2`, `TUSER_W=65`).

## Interfaces

- `s_axis`: axi4-stream (dir slave, tdata W). s_axis_tready is a flop of the credit count: low when no credit is left, in reset and for one clock after; sideband as in pipe_reg
- `m_axis`: axi4-stream (dir master, tdata W). m_axis_tvalid is a flop; m_axis_tdata is a read of the receiver buffer (a mux behind the pointer flops)

Clocks: `aclk`. Reset: `aresetn`, active low, synchronous.

## Latency and throughput

- forward: LF + 1 clocks from the edge that accepts a beat into an empty channel to the first clock it is visible at m_axis (measured at every point)
- credit round trip: RTT = LF + LB + 2 clocks: the credit of a beat sent at edge t first lets a beat go at edge t + RTT when the sink is always ready (measured at 19 points)
- bubbles: with CREDITS below RTT a source that is always valid sends CREDITS beats back to back and then waits RTT - CREDITS clocks; the pattern repeats (measured)
- throughput: min(1, CREDITS / (LF + LB + 2)) beats per clock with an always-ready sink (measured); beats held when the sink stops: CREDITS

## Evidence

cocotb against ip_lib/credit_chan/model.py clock by clock (s_tready, m_tvalid and data), an independent in-order scoreboard, mid-run resets, the AXI4-Stream rule monitor on both ports; declared latency, credit round trip, throughput and capacity checked against measured ones. Formal: credit conservation (credits + beats in flight + buffered + credits returning = CREDITS), counter and pointer bounds, order and loss, stability while stalled, and the stream rules as SVA, by k-induction. Tests: `ip_lib/credit_chan/tb/test_credit_chan_rtl.py`, `ip_lib/credit_chan/tb/test_credit_chan_formal.py`.

Try it: `python3 -m pytest ip_lib/credit_chan/tb/test_credit_chan_rtl.py ip_lib/credit_chan/tb/test_credit_chan_formal.py` (the formal jobs need SymbiYosys on PATH; they are skipped without it).

Parameter points simulated: `W=16, CREDITS=1, LF=0, LB=0`; `W=16, CREDITS=2, LF=0, LB=0`; `W=16, CREDITS=1, LF=1, LB=1`; `W=16, CREDITS=3, LF=1, LB=1`; `W=16, CREDITS=4, LF=1, LB=1`; `W=16, CREDITS=8, LF=1, LB=1`; `W=16, CREDITS=3, LF=2, LB=2`; `W=16, CREDITS=9, LF=2, LB=2`; `W=8, CREDITS=5, LF=3, LB=0`; `W=8, CREDITS=5, LF=0, LB=3`; `W=8, CREDITS=16, LF=4, LB=4`; `W=1, CREDITS=4, LF=1, LB=1`; `W=64, CREDITS=5, LF=2, LB=1`; `W=8, CREDITS=1, LF=8, LB=8`; `W=8, CREDITS=18, LF=8, LB=8`; `W=32, CREDITS=6, LF=2, LB=2, TLAST_EN=1, TKEEP_EN=1, TUSER_W=5`.

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `credit_double_return` | a returned credit counts as two: the sender sends into a full receiver buffer | caught |
| `ready_without_credit` | s_ready ignores the credit count: the sender sends with no credit and the receiver buffer overflows | caught |
| `credit_lost_when_both` | a credit arriving in the clock a beat is sent is dropped: credits leak and the channel slows then stops | caught |
| `credit_start_zero` | the sender starts with no credits: nothing is ever sent | caught |
| `write_pointer_no_wrap` | the write pointer does not wrap at CREDITS: wrong entries for a depth that is not a power of two | caught |
| `read_wrong_entry` | the output reads the write position, not the read position | caught |
| `pop_without_ready` | the read pointer advances whenever the output is valid, not when it is taken: a stalled beat is skipped | caught |
| `valid_one_clock_late` | m_valid follows the buffer count one clock late: a beat is offered after it was popped | caught |
| `forward_stage_skips` | a forward stage takes its data from the first stage, not the previous one | caught |
| `return_stage_drops` | a credit-return stage past the first drops every credit | caught |
| `count_unaccepted_beat` | a beat that was offered but not accepted enters the channel | caught |
| `buffer_write_ignores_valid` | the receiver buffer is written on every clock: an entry is overwritten by an invalid beat | caught |

## Boundary and reuse

- Registered outputs: s_axis_tready and m_axis_tvalid are flops; the forward wires and the credit return are plain register stages; m_axis_tdata is a buffer read.
- Clock crossings: none (one clock; the two ends are reset together, one reset).
- Part, board or pin: none (the receiver buffer is an array: LUT RAM or registers by the tool).
- Depends on: nothing.

## Cost table

pending: out-of-context Vivado runs are queued (partition/sweep.py group q4); Yosys counts at one and two stages for a 64-bit link are in results/b151/part_sys_yosys.json.

Licence: MIT (this repository).

## Known gaps and limits

- One clock and one reset for both ends (the ends cannot yet be placed in separate reset domains); the receiver buffer holds CREDITS entries even when the link is short; the link between the ends is not AXI (no ready); the two ends are not yet separate modules, so they cannot be instantiated in two partitions apart; formal proofs at W = 4 with the sideband off.
- Board: no board run of this entry is recorded; its evidence is simulation.
- Cost: no out-of-context characterisation (no `characterisation:` in ip.yaml), so resources, Fmax and power are not measured for this entry.
- No Vivado number: whether a credit link beats a chain of skid slices on area or Fmax is the question the queued q4 runs answer.
- The sender and receiver halves are one module; separate credit_tx and credit_rx modules, to place in two partitions, are a follow-up.

## Next steps

1. Split the block into a sender and a receiver module so the halves can sit in separate partitions, and prove the same properties on the pair.
2. Run the queued q4 points and decide, with numbers, the depth at which a credit link replaces a chain of skid slices.

## History

- 0.1.0 (2026-11-21): First version (brief 151). See README.md.

Full entries: [CHANGELOG.md](CHANGELOG.md).
