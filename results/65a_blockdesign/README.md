# Block designs: the sample built end to end

The sample block design [designs/b65a_axil_soc](../../designs/b65a_axil_soc) (three `ip_lib` blocks behind a generated
AXI4-Lite crossbar, under the UART test shell) was validated, generated, simulated and built. How the format,
checks and generator work: [docs/blockdesign.md](../../docs/blockdesign.md).

Scope: AXI4-Lite only, one 100 MHz clock domain; built with Vivado 2026.1, not run on the board.

## Results

| What | Result | Record |
|---|---|---|
| Validation of the sample | 0 errors; 1 warning (the hole between `tone.s_fd` and `la.s_axil`, which answers DECERR); 1 note (`fd.valid` left open) | `designs/b65a_axil_soc/gen/manifest.json` |
| Crossbar on its own | 35 tests, all pass: 20 random-traffic runs at five parameter points (1x1 to 4x2 and 2x5) with the AXI4-Lite protocol checker (`axi_tx/rtl/axil_checker.sv`) silent on every link; read fairness and write fairness at three points; a reset with a write and a read in flight at two points; 7 parameter guards | `ip_lib/axil_xbar/tb/test_axil_xbar_rtl.py` |
| Crossbar seeded faults | 10 of 10 caught (decode, read and write arbitration, response, data path, protocol, strobes, reset) | [faults.json](faults.json) |
| Generated design in simulation (Icarus Verilog 12, cocotb 2.0.1) | through the UART shell: register reset values, byte strobes, SLVERR for a status write and an unmapped word, DECERR at both ends of the hole, SLVERR above the analyser's 128-word window; the frequency counter read 62 edges in a 4000-clock gate for a 64-clock tone (62.5 expected); 24 logic-analyser samples are a contiguous run of the DDS model; 86 AXI4-Lite transfers with no rule broken on the four top-level links | [sim_end_to_end.json](sim_end_to_end.json) |
| Vivado 2026.1 build for the Nexys A7 (xc7a100tcsg324-1) | every gate passed (RTL, post-synthesis, placement, routing, bitstream); worst setup slack +2.040 ns at 100 MHz; 1064 LUT, 1150 FF, 0.5 block RAM tile; 0.129 W on-chip (vectorless), junction 42.3 C; build ID `ad946e1a`; 185 s wall at 4 threads, 2184 MiB peak anonymous memory | [vivado_build/](vivado_build) (`gates.json`, `run.json`, `manifest.json`, `timing_summary.rpt`, `utilization.rpt`, `utilization_hier.rpt`, `power.rpt`) |
| Viewer graph against the build | 14 of 14 RTL instances (the 14 include the generated wrappers) found in the synthesised netlist with the module the graph names, and no netlist cell inside the top, the hierarchy or a wrapper missing from the graph; 6 of the 7 links between blocks found as nets in the direction drawn, and no net between two blocks left undrawn (the 7th, an inverted bit, goes through logic and is not compared); the crossbar's 3 address ranges equal the built RTL's | [../blockdesign/b65a_axil_soc/build.json](../blockdesign/b65a_axil_soc/build.json) |
| Viewer in a browser (Chrome, puppeteer) | stand-alone page and site page at 390 and 1280 px, light and dark: no console errors, no horizontal overflow, no overlapping or overflowing diagram text, text at least 11 px, every block's details panel opens | `flow/blockdesign/tests/e2e_viewer.js` |

## Interop: IP Integrator export on Vivado 2026.1 (a check only)

Records [interop/](interop) (each run's JSON and its Vivado log), made by `flow/blockdesign/vivado/bd_export_probe.tcl`
on a two-slave AXI4-Lite block design (two AXI GPIO cores behind an AXI crossbar core):

- In batch mode, `create_bd_design`, `assign_bd_address`, `validate_bd_design` and `write_bd_tcl` (a 10247-byte script)
  work ([probe_batch.json](interop/probe_batch.json)).
- `write_bd_layout` does not work in batch mode: it warns "write_bd_layout failed. Please run the tool in GUI mode and
  try again" (BD 5-349) and writes no file, while the Tcl command returns without an error
  ([vivado_batch.log](interop/vivado_batch.log)). A script must check that the file exists.
- In GUI mode on a virtual display (`xvfb-run`), after `regenerate_bd_layout`, it wrote an SVG (7429 bytes) and a PDF
  (20757 bytes) ([probe_gui.json](interop/probe_gui.json), [probe_layout_gui.svg](interop/probe_layout_gui.svg)).
  Without `regenerate_bd_layout` it wrote an empty drawing: an SVG of 868 bytes with a zero view box
  ([probe_gui_noregen.json](interop/probe_gui_noregen.json), [probe_layout_gui_noregen.svg](interop/probe_layout_gui_noregen.svg)).

Importing a `.bd` for viewing is a later phase.

## Not measured

- Nothing here has run on the board; the bitstream was built, not programmed.
- Power is `report_power` without activity files.
- The crossbar has no out-of-context cost sweep; its in-context cost is in the build table above.
- The parameter guards of the crossbar and the support RTL run in simulation only; Vivado ignores them.
