# results/b110: a standard-protocol trading path, phase 1

Recorded results for [designs/b110_itch_ouch](../../designs/b110_itch_ouch/README.md): MoldUDP64 and Nasdaq TotalView-ITCH 5.0 in, a small
top-of-book, pre-trade risk with a kill switch, OUCH 5.0 Enter Order in SoupBinTCP 3.00 framing out, checked bit for bit against a Python
reference model, with seeded faults, and built out of context on the K26 (xck26-sfvc784-2LV-c, Vivado 2026.1). Synthetic data only; no board
run; nothing was ever sent to a real exchange.

## Records

| File | What | Made by |
|---|---|---|
| `latency_sim.json` | clocks from the last byte of a message to the decoded event, the top-of-book update and the first word of the order frame, with the frame started at the verdict and speculatively | `B110_RECORD=$PWD/results/b110 pytest designs/b110_itch_ouch/tests/test_b110_rtl.py::test_all_benches` |
| `throughput_sim.json` | payloads back to back with no idle clock: messages, words, clocks per message, nothing dropped | same |
| `coverage_sim.json` | message start and end byte offsets in a word, last-word keep masks, counters seen non-zero | same |
| `min_idle_sim.json` | the smallest idle gap between two payloads for which the path equals the model | same |
| `mutation.json` | every seeded fault of `designs/b110_itch_ouch/verif/mutants.yaml` against the whole bench: killed, survived, invalid, and which test killed each | `python3 designs/b110_itch_ouch/tests/run_mutants.py --jobs 2 --json results/b110/mutation.json` |
| `ooc/itch_ouch_top.json` | post-route LUT, FF, block RAM, DSP, WNS, WHS and pulse-width slack at the required 10G core clock (6.2061 ns) and two faster clocks | `python3 -m designs.b110_itch_ouch.ooc.ooc` (heavy slot) |

## Reproduce

- Python 3.12, pyyaml, cocotb 2.0.1 and Icarus Verilog 12 for the bench; Verilator for the lint test; Vivado 2026.1 for the builds.
- The bench takes about a minute; the seeded faults about 45 minutes (two at a time); each out-of-context build several minutes under a heavy-job slot.
- Everything is seeded (`model/gen.py`); no file here depends on a real feed.

## Known gaps and limits

- Simulation and out-of-context builds only: no board run, no power figure, no timing inside the 10G core.
- The latency figures are clocks inside this block, from the UDP payload words in to the order frame words out; they do not include the PCS,
  MAC, header handling or the TCP stack of a real path ([phase 2 plan](../../designs/b110_itch_ouch/docs/phase2_integration.md)).
- One generator and one message mix; the numbers say nothing about a market.
