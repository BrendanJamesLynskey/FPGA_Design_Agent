# Brief 65A: block designs, the sample built end to end

The sample block design [designs/b65a_axil_soc](../../designs/b65a_axil_soc) (three `ip_lib` blocks behind a generated
AXI4-Lite crossbar, under the UART test shell) was validated, generated, simulated and built. How the format,
checks and generator work: [docs/blockdesign.md](../../docs/blockdesign.md).

## Results

| What | Result | Record |
|---|---|---|
| Validation of the sample | 0 errors; 1 warning (the hole between `tone.s_fd` and `la.s_axil`, which answers DECERR); 1 note (`fd.valid` left open) | `designs/b65a_axil_soc/gen/manifest.json` |
| Crossbar on its own | 20 random-traffic runs at five parameter points (1x1 to 4x2 and 2x5), fairness at three, map guards: all pass with brief 59's AXI4-Lite checker silent on every link | `ip_lib/axil_xbar/tb/test_axil_xbar_rtl.py` |
| Crossbar seeded faults | 8 of 8 caught (decode, arbitration, response, data path, protocol, strobes) | [faults.json](faults.json) |
| Generated design in simulation (Icarus Verilog 12, cocotb 2.0.1) | through the UART shell: 79 AXI4-Lite transfers; register reset values, byte strobes, SLVERR for a status write and an unmapped word, DECERR at both ends of the hole; the frequency counter read 62 edges in a 4000-clock gate for a 64-clock tone (62.5 expected); 24 logic-analyser samples are a contiguous run of the DDS model; no AXI4-Lite rule broken on the four top-level links | [sim_end_to_end.json](sim_end_to_end.json) |
| Vivado 2026.1 build for the Nexys A7 (xc7a100tcsg324-1) | every gate passed (RTL, post-synthesis, placement, routing, bitstream); worst setup slack +2.076 ns at 100 MHz; 1054 LUT, 1149 FF, 0.5 block RAM tile; 0.129 W on-chip (vectorless), junction 42.3 C; build ID `cf30a039`; 179 s wall, 2184 MiB peak anonymous memory | [build/](build) |
| Viewer graph against the synthesised hierarchy | 14 of 14 expected instances found with the modules the graph names; no unexpected instance in the top, the hierarchy or a wrapper | [../blockdesign/b65a_axil_soc/build.json](../blockdesign/b65a_axil_soc/build.json) |
| Viewer in a browser (Chrome, puppeteer) | stand-alone page and site page at 390 and 1280 px, light and dark: no console errors, no horizontal overflow, no overlapping or overflowing diagram text, every block's drawer opens | `flow/blockdesign/tests/e2e_viewer.js` |

## Interop: IP Integrator export on Vivado 2026.1 (a check only)

[interop/probe_batch.json](interop/probe_batch.json), [interop/probe_gui.json](interop/probe_gui.json),
made by `flow/blockdesign/vivado/bd_export_probe.tcl` on a two-slave AXI4-Lite block design (two AXI GPIO cores
behind an AXI crossbar core):

- `create_bd_design`, `assign_bd_address`, `validate_bd_design` and `write_bd_tcl` all work in batch mode.
  (`validate_bd_design` refused the first version of the probe, whose clock pins were not connected: its own
  unconnected-clock check.)
- `write_bd_layout` does not work in batch mode: it warns "write_bd_layout failed. Please run the tool in GUI mode"
  and writes nothing, while the Tcl command itself returns without an error.
- In GUI mode on a virtual display (`xvfb-run`), after `regenerate_bd_layout`, `write_bd_layout` wrote an SVG
  (7429 bytes) and a PDF. Without `regenerate_bd_layout` the SVG was empty (a zero-size view box).

Importing a `.bd` for viewing is a later phase.

## Not measured

- Nothing here has run on the board; the bitstream was built, not programmed.
- Power is `report_power` without activity files.
- The crossbar has no out-of-context cost sweep; its in-context cost is in the build table above.
