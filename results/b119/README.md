# results/b119: a TCP fast path for OUCH orders

Recorded results for [designs/b119_tcp_fast](../../designs/b119_tcp_fast/README.md): a block that holds the connection state software hands it and sends each OUCH
5.0 order as one complete Ethernet/IPv4/TCP frame with incrementally finished checksums, supports brief 110's speculative start and abort without consuming
sequence space, and hands every sent segment back to software; a Python TCP owner and a software OUCH exchange that exercise it; seeded faults; and an
out-of-context build on the K26 (xck26-sfvc784-2LV-c, Vivado 2026.1). Synthetic data only; no board run; nothing was ever sent to a real exchange.

## Records

| File | What | Made by |
|---|---|---|
| `bench_sim.json` | latencies of the segment in clocks, the outcome at every abort offset, the refusal codes, the outcomes of the random mix, and the figures of the end-to-end runs with the software exchange (retransmissions, takeovers, refusals) | `B119_RECORD=$PWD/results/b119 pytest designs/b119_tcp_fast/tests/test_b119_rtl.py::test_all_benches` |
| `top_sim.json` | clocks from the last byte of a triggering ITCH message to the first byte of the Ethernet frame behind brief 110's risk logic, started at the verdict and speculatively | `B119_RECORD=$PWD/results/b119 pytest designs/b119_tcp_fast/tests/test_b119_rtl.py::test_behind_the_risk_logic` |
| `mutation.json` | every seeded fault of `designs/b119_tcp_fast/verif/mutants.yaml` against the whole bench: killed, survived, invalid, and which test killed each | `python3 designs/b119_tcp_fast/tests/run_mutants.py --jobs 2 --json results/b119/mutation.json` |
| `ooc/tcp_fast.json` | post-route LUT, FF, block RAM, DSP, WNS, WHS and pulse-width slack at the required 10G core clock (6.2061 ns) and a faster one | `python3 -m designs.b119_tcp_fast.ooc.ooc` (heavy slot) |

Re-recorded 2026-11-26 (brief 236): brief 176 (PR #303) rewrote the two lines that the seeded faults `seq_captured_wrong` and `id_not_captured` matched, so the nightly fresh-evidence run stopped with "does not apply exactly once". Both faults now match the new lines and keep their meaning (the captured sequence number or IP identification is wrong or zero on the path that sends new data). The result is unchanged, 73 of 73 killed, 0 survived, 0 invalid; the only change to `mutation.json` is that 176's test `t_giveback` now also appears among the tests that kill some faults. This is not a regression.

## Reproduce

- Python 3.12, pyyaml, cocotb 2.0.1 and Icarus Verilog 12 for the bench; Verilator for the lint test; Vivado 2026.1 for the builds.
- The bench takes about ten seconds and the seeded faults about a quarter of an hour (two at a time); the out-of-context build several minutes under a heavy-job slot.
- Everything is seeded; no file here depends on a real feed. Brief 110's branch (`b110-itch-ouch`) is the base: the frame builder, the packers and the risk logic come from it.

## Known gaps and limits

- Simulation and out-of-context builds only: no board run, no power figure, no timing inside the 10G core, and the pair `tcp_fast` plus the 96 design's MAC was not simulated together.
- The latency figures are clocks inside the block; the PCS, MAC, frame check sequence and the PS's own traffic are not in them.
- One order format (brief 110's 59-byte packet), one connection, no TCP options, no SACK.
- The exchange is our own model of the Nasdaq documents, not a real port.
