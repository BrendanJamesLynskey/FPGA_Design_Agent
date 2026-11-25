# 186: can this PC's Vivado implement the Alveo UL3524 part? (licence check, 2026-11-23)

**Answer: no. The part `xcvu2p-fsvj2104-3-e` is refused at synthesis by the installed licence tier. Brief 185 must not plan implementation (synthesis, place, route) for this part on this PC.**

## What was run
- Vivado 2026.1 (SW build 6511674), `/opt/Xilinx/2026.1/Vivado/bin/vivado`, batch mode, the owner's normal licence environment (HOME unchanged).
- Brief 33's `results/33_vivado_speed_2026_1/licence_check.tcl` (one 8-bit counter: `synth_design -mode out_of_context`, `opt_design`, `place_design`, `route_design`) with `LC_PARTS=xcvu2p-fsvj2104-3-e`; launcher `run_licence.sh` here (takes a "186:" heavy slot, waits for one, releases it). Raw output: `licence_check.log`.
- Licence file features present (names only): `Vivado_Basic_Package`, `Vivado_Implementation`, `Vivado_Simulation`, `Vivado_Synthesis`. Vivado reported: "A valid Vivado Design Suite BASIC license has been detected ... will expire on 10-nov-2027."

## Result (verbatim from `licence_check.log`)
- `WARNING: [Device 21-9575] Your current selected license is BASIC. This license doesn't cover the device you selected.`
- `synth_design failed`
- `LICENCE-CHECK xcvu2p-fsvj2104-3-e FAILED: ERROR: [Common 17-162] Invalid option value specified for '-part'.`
- Wall time of the whole run: about 17 s (refused before synthesis started). Device data for the part is installed (`data/parts/xilinx/virtexuplus`, IBIS package file `xcvu2p_fsvj2104.pkg`); the refusal is the licence tier, not missing data.

## Side note: brief 33's no-licence variant
With every licence hidden (empty HOME, no licence variables) Vivado 2026.1 does not start at all (`licence_check_nolicence.log`: "cannot be launched because a valid license was not found"); this agrees with brief 33's README. The check above therefore uses the installed Basic licence.

## What this means for the other tasks
- No synthesis, place or route for this part on this PC: OOC timing studies of the order path cannot target the VU2P here (brief 185). A paid tier that covers the device, or a cloud image that has one, would be needed (owner decision; not requested here).
- Simulation: not tested by this check. Task 2 of brief 186 checks separately whether xsim and IP generation accept the part.
