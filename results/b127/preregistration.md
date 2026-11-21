# Brief 127 board test: pre-registration

Written 2026-11-21 before any board time, and before the build's final timing was known to the author. The design is `designs/b96_kr260_10g/rm_gp_itch`; the test is described in
`designs/b96_kr260_10g/rm_gp_itch/docs/board_test_plan.md`, the stages are `host/b127_stages.py`, the script is `_handoff/fpga_agent/run_127_stage1.sh`.

**Arms:** speculation off and on (the latency stage only; the other stages run with speculation off, except the smoke stage may be repeated with it on). **Runs:** one session each for smoke, counters, rate and risk; 125 passes of 8 orders for each latency arm.
**Comparisons:** every counter against brief 110's model; every captured order frame against the model's frame; the latency histogram against the simulation's. **Stopping rules:** the driver stops at the first of: ID or FEATURES wrong,
polarity wrong, no link. A failed stage does not stop the later stages (each is judged on its own), a result outside the recommended operating conditions voids the run.
**Predictions:** the pass criteria of the plan; in particular the latency histogram support is {10, 11} clocks (speculation off) and {5, 6} (on), exactly the simulation's, with at most 10 % in the upper bin of each pair.
**Nulls stated plainly:** a pass shows the built logic behaves as simulated on a real transceiver. It says nothing about interoperability, wire-to-wire latency or a frequency offset.
