# Brief 71B: the sign-off netlist gate attacked with real builds

This folder holds the evidence that the reset check's netlist part, which the sign-off gate `post_synth_resets_clean` depends on, catches
attack designs built with Vivado 2026.1: one folder of scan and reports per design, the version record `tool_version.txt`, and the table below.

## Records

`tool_version.txt`: the Vivado 2026.1 build line from the reports.
`<case>/reset_scan.tsv`, `methodology.rpt`, `drc.rpt`, `cdc.rpt`: one folder per attack design, from Vivado 2026.1.

## Measured

26 small attack designs (`flow/checks/seeded/adv/adv_*.sv`, runner `adv.tcl`) were synthesised out of context with Vivado 2026.1
(xc7a100tcsg324-1, two asynchronous clocks, one session for the batch plus one re-run of three designs), and each was run through
the sign-off reset gate's inputs: our netlist scan `reset_scan.tsv` and AMD's `report_methodology`, `report_drc` and `report_cdc`.
`flow/tests/test_71b_reset_elab.py::test_netlist_gate_attack_designs` reads these records and requires exactly the rules below.

| Design | Attack | Rules raised | Result |
|---|---|---|---|
| a01 async_plain, a08 async_set | plain asynchronous reset or set | HDL-RST-01 | caught |
| a02 prim_fdce, a03 prim_fdpe_inv_clk, a04 prim_fdcpe, a05 prim_ldce | direct primitives, inverted clock, FDCPE, latch | HDL-RST-01 | caught |
| a06 latch_with_reset, a07 macro_flop, a12 array, a13 dont_touch, a14 gated_buf | inferred latch, macro, instance array, DONT_TOUCH, reset through a BUFG | HDL-RST-01 | caught |
| a10 instance_named_reset_sync | instance named `reset_sync` of another module | HDL-RST-01 | caught (exemption is by module name) |
| a11 user_module_named_reset_sync | user module named `reset_sync` | HDL-RST-01 | caught after the fix below; before it, exempt by name |
| e01 iddr_async, e02 oddr_async | IDDR/ODDR with SRTYPE ASYNC | HDL-RST-01 | caught after the fix below; before it the scan did not list them |
| e03 srl_style_shift_async | shift register with asynchronous reset | HDL-RST-01 | caught |
| b01 polarity, b02 polarity_via_inverter | one reset used in both polarities | HDL-RST-02 | caught |
| c01 lut_drives_async | logic drives an asynchronous reset | HDL-RST-01, HDL-RST-05 (AMD LUTAR-1 also fired) | caught |
| c02 cdc_sync_reset | clk_a reset used as clk_b synchronous reset | HDL-RST-04 | caught |
| c03 cdc_async_reg | the same, asynchronous | HDL-RST-01, HDL-RST-04 (AMD CDC-7) | caught |
| d01 dsp_async, d02 bram_async | asynchronous reset on DSP and RAM registers | HDL-RST-01, HDL-RST-03 (AMD DPIR-1 on the DSP) | caught |
| z01 clean_sync, z02 clean_shell_sync, z03 clean_two_domains | xpm_cdc_async_rst, the shell's reset_sync, two domains | none | clean |

Fixes made because of the attack (both HIGH: a wrong pass):
- A module was exempt by its name alone, so a user module called `reset_sync` was exempt from HDL-RST-01. The scan now writes
  `sync_struct` (the parents that contain an `xpm_cdc_async_rst`/`xpm_cdc_sync_rst` instance or an ASYNC_REG register), and a module
  is exempt only if its name and that structure both hold. Scans made before the column existed are still judged by name.
- IDDR and ODDR with SRTYPE ASYNC were not in the scan; their R and S pins now are.

## Known gaps and limits

Findings that are not rule failures here:
- The first versions of b01, b02 and c02 used one-bit registers, which Vivado folded into the D logic (the scan had no row). A
  synchronous reset folded into D is invisible to the reset scan (a known gap, also in docs/check_suite.md); `report_cdc` reports a
  folded cross-domain reset as CDC-1 (Critical) and the `cdc` check blocks on it. The designs were widened to 8 bits and are caught.
- `sync_struct` tests for an ASYNC_REG register or an XPM reset macro inside the module; it does not check that the chain drives the reset.

## Reproduce

Vivado 2026.1, heavy slot, `systemd-run --user --scope -p MemoryMax=6G`:
`vivado -mode batch -source flow/checks/seeded/adv/adv.tcl -tclargs results/71b_netlist_scans [case ...]`
