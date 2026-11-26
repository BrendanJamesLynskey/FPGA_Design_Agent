# credit_chan datasheet (version 0.1.0, brief 151)

Credit-based pipelined channel between two AXI4-Stream ports. Every figure is measured in simulation
(`results/b151/credit_chan_measure.jsonl`, 2026-11-21) or proved (`results/b151/credit_chan_formal.json`); none is a Vivado number.

## When to use it, and when not to

**Default to `pipe_reg`.** AXI4-Stream valid/ready with a skid slice is the AXI practice; a chain of skid slices has no ready loop
longer than one slice (every slice's ready is its own flop). Use `credit_chan` only where valid/ready does not fit:

* a long pipeline or a long distance where a ready that has to travel back through every stage cannot close timing and a chain of
  skid slices is too costly (two stored beats per stage);
* a link whose forward wires must be plain registers (no mux, no enable) so they can be pipelined at any depth and placed anywhere.

It costs `CREDITS` entries of receiver buffer, a latency of `LF + 1`, and the link between its two ends is not AXI. Whether it beats a chain of
skid slices on area or Fmax is question Q7 of the study; the Vivado runs are queued.

## The AXI4-Stream bridge

The block *is* the bridge: an AXI4-Stream slave port in (`s_axis_*`, `tready` a flop of the credit count), the credit link in the
middle (LF forward register stages, LB return stages, no ready), an AXI4-Stream master port out (`m_axis_*`, `tvalid` a flop). Sideband
(`TLAST_EN`, `TKEEP_EN`, `TUSER_W`) as in `pipe_reg`. The two halves are one module today; separate sender and receiver modules for two
partitions are a follow-up.

## Behaviour (measured; the model declares the formulas and the test asserts them)

| Figure | Value |
|---|---|
| Latency, accepted into empty channel to visible at `m_axis` | `LF + 1` clocks |
| Credit round trip `RTT` | `LF + LB + 2` clocks |
| Throughput, always-ready sink | `min(1, CREDITS / RTT)` beats per clock |
| Full throughput needs | `CREDITS >= LF + LB + 2` |
| Beats held when the sink stops | `CREDITS` |
| Bubbles when `CREDITS < RTT` | bursts of `CREDITS` beats, then `RTT - CREDITS` idle clocks, repeating |

Example (measured): `CREDITS 2, LF 1, LB 1` sends two beats, waits two clocks (throughput 0.5); `CREDITS 4` sends one beat per clock.

## What a user could guess wrong

* `CREDITS` is both the number of credits at reset and the receiver buffer depth; it is not a throughput knob beyond `RTT`.
* `s_axis_tready` is low in reset and for one clock after, and low whenever no credit is left; `m_axis_tvalid` is a flop.
* `LF = 0` puts the beat straight into the receiver buffer in the clock it is accepted (latency 1); `LB = 0` counts the credit in the
  clock the beat leaves.
* One reset for both ends; they are not meant to be reset at different times (a reset of one end alone loses the count).
* `m_axis_tdata` is a read of the buffer (a mux behind the pointer flops), not a flop.
* A beat offered during reset is discarded; the source must hold `tvalid` low in reset and one clock after.

## Verification

Model `model.py`; bench `tb/credit_cocotb.py` (clock by clock, in-order scoreboard, resets in traffic, the rule monitor on both ports, 19
points below, at and above the round trip plus three with sideband); formal (`formal/`, k-induction at W = 4): credits + beats
in flight + beats buffered + credits returning = `CREDITS` (so no overflow, no underflow, counter in range), pointers in range,
order and loss, stability while stalled, and the stream rules as SVA. 12 seeded faults, 12 caught by simulation and 12 refuted by the proofs.
