# results/project_parity_2026_1: brief 18's project-mode parity probes on Vivado 2026.1 (brief 49)

The probes of [docs/project_mode_parity.md](../../docs/project_mode_parity.md) re-run on **Vivado 2026.1** (Basic licence
tier) on 2026-11-12, each Vivado in its own 6 GB scope under a heavy slot. Dates, hosts, command lines and local paths are
removed from the reports.

## Records

The table lists each directory, the script that made it and how it compares with the earlier record. Directory contents: reports and read-backs per probe (`clkwiz/clkwiz.jsonl`, the `mmcm_timing/` and `cmt_check/` reports, `wizards/*.txt`, per-case results under `mig_impl/`, JSON and SVG under `xprobe/`).

| Directory | Script (arguments as in the earlier record) | Compared with `results/project_parity` |
|---|---|---|
| `clkwiz/` | `flow/clkwiz_probe.tcl xc7a100tcsg324-1 <out> s1_74:100:MMCM:74.25 s2_vga:100:MMCM:25.175 s3_audio:100:MMCM:12.288,49.152,98.304 s4_pll:100:PLL:200,50 s5_900:100:MMCM:900 s6_4mhz:100:MMCM:4` | every read-back identical |
| `mmcm_timing/` | `flow/mmcm_timing_probe.tcl xc7a100tcsg324-1 <out> vga_wizard:4:36.375:36.125 vga_hand:6:62.875:41.625 aud_wiz:2:21.625:88.0 s1_wiz:4:37.125:12.5 s1_lowvco:5:30.0:12.0` | identical (TSJ, DJ, PE, uncertainty) |
| `cmt_check/` | `flow/cmt_check_probe.tcl xc7a100tcsg324-1 <out> legal:1:10:10 vco_high:1:13:10 vco_low:1:5:10 pfd_low:11:50:10` | identical: AVAL-46 on the three illegal settings, nothing on the legal one |
| `wizards/wizards.txt`, `wizards2.txt` | `flow/wizard_probe.tcl`, `flow/wizard_probe2.tcl` | the same OK/FAIL verdicts; 2026.1 adds a `validate_ip` command (not tested on a MIG pinout) and lists more `gt0_val_*` properties on the GTP Transceivers Wizard |
| `mig_impl/{good,bytegroup,dup}/` | `flow/mig_impl_check.tcl xc7a100tcsg324-1 <KB .prj> <out>` | the same DRC rules and counts after synthesis, placement and bitstream checks (PLIO-3 only on `dup`); synthesis 242-253 s |
| `xprobe/` | `FDA_XPROBE=1 flow/run_vivado.sh designs/<name> base`, then `flow/xprobe.py --svg --summary` | new placements: b2_acl_adxl362 WNS 3.335 ns, b2_qspi_jedec 4.278 ns (the cross-probe output itself is the same kind) |

## Reproduce

Each command is in the table above (`flow/*_probe.tcl`, `flow/mig_impl_check.tcl`, `FDA_XPROBE=1 flow/run_vivado.sh designs/<name> base` then `flow/xprobe.py --svg --summary`). They need Vivado 2026.1 (Basic tier) and a heavy slot with a 6 GB scope; the MIG checks took 242 to 253 s of synthesis each.

## Known gaps and limits

- One run per probe; the two new cross-probe placements are single builds, so their slacks are not a trend.
- The new `validate_ip` command of the wizards was not tested on a MIG pinout.
- The probes check what Vivado reports for fixed settings; they do not cover other devices or boards.
- Dates, hosts, command lines and local paths were removed from the reports.
