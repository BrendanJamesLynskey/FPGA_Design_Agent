# results/b58a: the mock trading path (brief 58A)

Simulation, formal and the Vivado 2026.1 build. **No board run yet** (`designs/b58a_trigger/docs/board_run_plan.md`).
Clock counts are 125 MHz clocks (8 ns).

| File | What | Made by |
|---|---|---|
| `latency_sim.json` | per-stage clocks for one trigger, speculative and safe, one- and twenty-message frames (pre-built headers) | `B58A_RECORD=results/b58a pytest designs/b58a_trigger/tests/test_b58a_rtl.py` (`stage_latency`) |
| `latency_sim_assemble.json` | the same with the response frame assembled after the decision (`BUILD_MODE=1`) | same (`test_b58a_assemble_then_send`) |
| `stale_parameters_sim.json` | tick-to-config: a trigger judged on the old rule table, the next on the new; the software time is an assumption, not a measurement | same (`stale_parameters`) |
| `loop_sim.json` | the port B loop in simulation (generator -> trading port -> back), with bad-FCS and gap injection; histogram A and B read over the register bus | same (`bench_loop_port_b`) |
| `pins_sim.json` | kr260_top with RGMII looped from port B to port A: frames crossing intact, pin-side clocks (the XPM FIFO is its simulation model) | same (`test_b58a_pins`) |
| `mac_rgmii_faults.json` | the 10 seeded faults of `ip_lib/eth_mac_rgmii`, each caught | `flow/net/faults.py --only ...` |
| `formal.json` | SymbiYosys results: interlocks (bmc, k-induction prove, cover), mac_rx and mac_tx (bmc, cover) | `designs/b58a_trigger/tests/test_b58a_formal.py` |
| `nl_rules.json` | the natural-language rule fixtures checked offline (which meant what was asked, which were refused) | `python3 -m designs.b58a_trigger.host.nl_rule --check` |
| `build/` | the KR260 build: `summary.json` (timing, resources, power, gates), the timing summary, utilisation, power, CDC and methodology reports, gates, the run record (time, peak memory) | `flow/run_vivado.sh designs/b58a_trigger` |
| `showcase_sim.json` | the page data in the graphics kit's shapes, from the files above (simulation only) | `python3 results/b58a/export.py` |
