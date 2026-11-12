# Release: t1_dimmer_counter (base), build ID `89315dac`

- Design `designs/t1_dimmer_counter`, top `t1_dimmer_counter_top`, part `xc7a100tcsg324-1`.
- **Build ID `89315dac`**: the first 8 hex digits of the SHA-256 of the manifest's identity (`89315dac261d95d7b8f690671b9bd0e16fe897bac70cd871eb0a9c04b7918855`). The bitstream carries it in USR_ACCESS (read over JTAG as REGISTER.USR_ACCESS).
- Flow commit `41264bf12147` (clean tree); knowledge-bank pin `811b840`.
- Vivado 2026.1 (ran 2026.1, SW build 6511674, licence tier BASIC); 2 threads; directives synth_design Default, opt_design Default, place_design Default, phys_opt_design Default, route_design Default.
- Gates: **pass**.
- Timing: WNS 3.609 ns, TNS 0.0 ns, WHS 0.064 ns, THS 0.0 ns.
- Utilisation: 487 LUT, 488 FF, 0 block RAM tiles, 0 DSP.
- Power: 0.15 W on chip, junction 42.7 C (the board's thermal environment).

## Files

- `t1_dimmer_counter_top.bit`
- `manifest.json`
- `gates.json`
- `run.json`
- `reports/timing_summary.rpt`
- `reports/check_timing.rpt`
- `reports/utilization.rpt`
- `reports/power.rpt`
- `reports/drc.rpt`
- `reports/methodology.rpt`
- `reports/cdc.rpt`
- `reports/qor_unavailable_route.txt`
- `SHA256SUMS`

## Check

```
sha256sum -c SHA256SUMS
python3 flow/release.py check <this folder>     # sums, gates, build ID in the manifest and in the bitstream
```
