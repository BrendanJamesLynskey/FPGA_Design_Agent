# results/b58a: the mock trading path

These are the recorded results of the mock low-latency trading path ([designs/b58a_trigger](../../designs/b58a_trigger/README.md)):
a packet parsed as it arrives, a run-time rule, hardware interlocks and a response, on a bench loop with our own message
format and no real market. Everything here comes from simulation, formal tools and the Vivado 2026.1 build. **No board
run has happened.**

A clock count here is one 8 ns period of the 125 MHz design clock; each file states its start and end points.

| File | What | Made by |
|---|---|---|
| `latency_sim.json` | per-stage clocks for one trigger, speculative and safe, one- and twenty-message frames: from the SFD (and from the last price byte) entering the receive MAC to the first preamble byte leaving the transmit MAC, core side; checksum computed before the decision | `B58A_RECORD=results/b58a pytest designs/b58a_trigger/tests/test_b58a_rtl.py` (`stage_latency`) |
| `latency_sim_csum_after.json`, `latency_sim_assemble.json` | the same with the IPv4 checksum computed after the decision (`BUILD_MODE=1`), and with the whole frame stored and assembled after it (`BUILD_MODE=2`) | same (`test_b58a_build_modes`) |
| `stale_parameters_sim.json` | tick-to-config: a trigger judged on the old rule table, the next on the new; software time assumed as 2,000 clocks (16 us), so the 2,125-clock total is not a measurement | same (`stale_parameters`) |
| `loop_sim.json` | the port B loop in simulation (generator -> trading port -> back), with bad-FCS and gap injection; histogram A and B read over the register bus | same (`bench_loop_port_b`) |
| `pins_sim.json` | kr260_top with RGMII looped from port B to port A: frames crossing intact, pin-side clocks (the XPM FIFO is its simulation model) | same (`test_b58a_pins`) |
| `mac_rgmii_faults.json` | 10 deliberately injected bugs in `ip_lib/eth_mac_rgmii`, each detected by its test suite | `flow/net/faults.py --only ...` |
| `formal.json` | SymbiYosys results: interlocks, bounded check, k-induction proof and cover; the order slot, and the MAC receive and transmit state machines, bounded checks (not proofs) and cover; assumptions listed | `designs/b58a_trigger/tests/test_b58a_formal.py` |
| `nl_rules.json` | the natural-language rule fixtures checked offline (which meant what was asked, which were refused) | `python3 -m designs.b58a_trigger.host.nl_rule --check` |
| `build/` | the KR260 build: `summary.json` (timing, resources, power, gates), the timing summary, utilisation, power, CDC and methodology reports, gates, the run record (time, peak memory) | `flow/run_vivado.sh designs/b58a_trigger` |
| `showcase_sim.json` | data for the showcase page, simulation values only | `python3 results/b58a/export.py` |
