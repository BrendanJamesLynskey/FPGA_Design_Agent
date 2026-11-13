# Licence and build probe on Vivado 2026.1 Basic, for the KR260's K26 part (brief 56A, 2026-11-13)

`get_vivado_tier` returns BASIC. Part `xck26-sfvc784-2LV-c`. Each IP was created with `designs/b56a_gth_serdes/probe/ip_probe.tcl` (default or minimal
configuration, shown there), one Vivado process each, under `systemd-run MemoryMax=8G`. Stages: create, generate (`generate_target all`), `synth_ip`
(out of context), top (`synth_design` with the IP as top), impl (`opt`/`place`/`route`), bit (`write_bitstream`). An IP used as a top has no pins; for impl
and bit the unplaced-I/O DRCs (UCIO-1, NSTD-1) and the Kria pin DRC KLOC-1 are downgraded to warnings: a probe convenience, not a licence workaround. A licence
refusal is recorded with its exact text and never worked around. "stopped" means the probe plan stopped there to save machine time, not a failure.
Raw table: `probe/probe_results.json`; peak RSS is the largest process of the run.

| IP (version) | Result on Basic | Detail |
|---|---|---|
| `gtwizard_ultrascale` 1.7 | **allowed through bitstream** | the designs/b56a_gth_serdes build (RAW, 10.3125 Gb/s, GTHE4 X0Y6): synthesis, implementation, bitstream; all flow gates pass |
| `ibert_ultrascale_gth` 1.4 | create, generate, synth_ip, top OK; implementation: placer OK, router refused for a probe reason | `ERROR: [Route 35-7] Design has 36 unroutable pins, potentially caused by placement issue or user provided physical constraints.`; the IP had no clock or pins in this probe, so this is not a licence message (`Got license for feature 'Vivado_Implementation'`). A routable wrapper (`probe/ibert_top.v`) was not run: open item |
| `in_system_ibert` 1.0 | create ... impl OK; bitstream blocked by a pin DRC | `ERROR: [DRC KLOC-1] Incorrect Loc for kria boards: ... VRP PACKAGE_PIN W9 ...` (the placer put a port on a Kria VRP pin; no licence message); a later run with KLOC-1 downgraded was not made for this IP |
| `aurora_64b66b` 13.0 | create, generate, synth_ip, top OK | impl: `ERROR: [Common 17-69] Command failed: Placer could not place all instances` (IP as top, no pins: probe reason, not a licence message) |
| `aurora_8b10b` 11.1 | create, generate, synth_ip, top OK | impl stopped by plan |
| `xxv_ethernet` 5.1 (10G/25G Ethernet) | **refused at synthesis** | create, generate, `synth_ip` OK (with `CRITICAL WARNING: [IP_Flow 19-651] IP license key 'xxv_eth_mac_pcs@2026.06' is unlicensed.` and the same for `xxv_eth_basekr@2026.06`, `xxv_tsn_802d1cm@2026.06`); `synth_design`: `Fatal Error. License Check failed for secure IP for feature 'xxv_eth_mac_pcs@2026.06'. Exiting Synthesis.` / `No such feature exists.` / `FlexNet Licensing error:-5,357` (`xxv_licence_refusal.txt`) |
| `gig_ethernet_pcs_pma` 17.0 | create, generate, synth_ip, top OK | impl stopped by plan |
| `jesd204c` 4.3, `jesd204_phy` 4.1 | create, generate, synth_ip, top OK | the catalogue lists `jesd204c` with a licence key (`jesd204@2024.11`) yet synthesis passed; impl stopped by plan, so bitstream behaviour is unknown |
| `pcie4_uscale_plus` 1.3 | create, generate, synth_ip, top OK | no PCIe edge on the KR260; impl stopped by plan |
| `xdma` 4.2 | create, generate OK | `synth_ip` was cut short by an external termination of the shell; not re-run: unknown |
| `ten_gig_eth_pcs_pma` 6.0, `ten_gig_eth_mac` 15.1, `cmac_usplus` 3.1 | **not available for this part** | `ERROR: [Ipptcl 7-1639] No IP matching VLNV 'xilinx.com:ip:<name>' is accessible for the current part 'xck26-sfvc784-2LV-c'.` |

## Simulator licence

`xsim` (Vivado Simulator, Basic tier) refuses to run the GT Wizard's own simulation model: `ERROR: The current Vivado Simulator license tier you have, BASIC, does not meet
the requirement to run the number of instances in this design. Number of instances in this design, 54716, exceed maximum allowed 50000. See the Vivado Licensing page for tier details
and how to get the right license.` (a bench of the Wizard core and clocks alone; `xsim_refusal.txt`). So no GT-based IP (Aurora, Ethernet, IBERT examples) can be simulated with its AMD model here.
The fabric around the GT is simulated against a stand-in (designs/b56a_gth_serdes/sim/gth_wiz_model.sv).

## Catalogue facts (Vivado 2026.1, `get_ipdefs`, `REQUIRES_LICENSE`)

Needs a licence key: `xxv_ethernet` 5.1, `jesd204c` 4.3, `jesd204d`, `cmac_usplus`, `ten_gig_eth_mac`, `ten_gig_eth_pcs_pma`, `axi_ethernet`. No key: `gtwizard_ultrascale`, `ibert_ultrascale_gth`, `in_system_ibert`,
`aurora_64b66b`, `aurora_8b10b`, `jesd204_phy`, `pcie4_uscale_plus`, `xdma`, `gig_ethernet_pcs_pma`. `ten_gig_eth_*`, `cmac_usplus`, `cmac` and `dcmac` do not list the Zynq UltraScale+ family.

## Open

`ibert_gth` routable run (wrapper written, not run), `xdma` synth_ip, bitstream of any probed IP other than the Wizard, jesd204c implementation.
