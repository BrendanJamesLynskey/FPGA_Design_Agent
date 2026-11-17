# results/b96: brief 96, a 10GBASE-R link on the KR260 (simulation and builds; no board run)

This folder holds the recorded simulation results and Vivado build records of brief 96's 10GBASE-R link on the Kria KR260's SFP+ cage: latency measurements from the benches, the lock-time table from the Python model, and the gate and run records of the two builds. Nothing here comes from a board.

## Records

Each file is the record of claims in [designs/b96_kr260_10g/docs/what_we_found.md](../../designs/b96_kr260_10g/docs/what_we_found.md):

| File | What it records | Made by |
|---|---|---|
| `latency_sim.json` | transmit latency over all gearbox phases, receive latency over 33 phases, lock clocks at offset 0 | `B96_WRITE_RESULTS=... pytest designs/b96_kr260_10g/tests/test_b96_pcs_rtl.py` |
| `core_sim.json` | echo, loop and the tick-to-trade pieces in the whole-core bench | `B96_CORE_RESULTS=...` with the same command |
| `lock_time_model.json` | clocks to block lock for each of the 66 bit offsets (the bit-exact Python model) | the snippet in the design note section 2.8 |
| `build_b/` | variant (b) (SFP+ live, trading path): trimmed `gates.json`, `run.json`, `stages.txt` | `flow/run_vivado.sh designs/b96_kr260_10g base` |
| `build_a/` | variant (a) (near-end PMA loopback self-test): the same | `flow/run_vivado.sh designs/b96_kr260_10g/selftest base` |

## Reproduce

- Simulation records: `B96_WRITE_RESULTS=$PWD/results/b96/latency_sim.json B96_CORE_RESULTS=$PWD/results/b96/core_sim.json python -m pytest -q designs/b96_kr260_10g/tests/test_b96_pcs_rtl.py` (about 1.5 minutes; Icarus and cocotb 2.0.1).
- Builds: `flow/run_vivado.sh designs/b96_kr260_10g base` and `flow/run_vivado.sh designs/b96_kr260_10g/selftest base` under a heavy slot (`_handoff/take_heavy_slot.sh`), about 22 minutes each at 2 threads; the `gates.json` here has its per-stage report bodies trimmed.

## Review (house rule "Check once")

One independent Sonnet review (read-only, three questions: clause 49 conformance, can the twin and the RTL disagree unseen, is any latency flattered) and one fix round. Findings and what was done:

- Fail-open poison, verdict race between orders, missing resets of the MAC's pending-end state, unclamped generator length, a lock loss mid-frame leaving the receive MAC in a frame, a searched alignment offset in the transmit twin test, lane-4 start coverage, the transmit latency reported as 2 although the pause makes it 2 or 3, and the tick-to-trade figure being assembled from several benches: fixed or restated (see the design's `docs/what_we_found.md`).
- Block type 0x66 treated as an ordered set (standard: ordered set then a lane-4 start); no RS link-fault or BER monitor; no preamble check; the model and RTL share the author's reading of clause 49 (no third-party vector available); the same-clock bench cannot show clock-crossing phase: documented as gaps, not fixed.

## Known gaps and limits

No board run: every number is simulation or a Vivado report. The GT is a behavioural stand-in in simulation; the clocks in the whole-core bench are in phase. See the design's `docs/what_we_found.md` for the full list.
