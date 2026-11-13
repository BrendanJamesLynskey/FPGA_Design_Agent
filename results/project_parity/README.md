# results/project_parity

Records of the project-mode parity probes of brief 18 (clocking-wizard read-back, MMCM timing, clock-manager legality checks, IP wizards, MIG implementation checks and cross-probing), run on an earlier Vivado release for [docs/project_mode_parity.md](../../docs/project_mode_parity.md).

Measured on 2025.2, superseded by `results/project_parity_2026_1`.

## Records

| Path | What |
|---|---|
| `clkwiz/clkwiz.jsonl` | Read-back of the clocking wizard for six requested settings |
| `mmcm_timing/` | Clock uncertainty, jitter and phase error of five MMCM set-ups |
| `cmt_check/` | The clock-manager legality checks: one legal and three illegal settings, with the DRC and methodology reports |
| `wizards/` | The OK or FAIL verdicts of the IP wizard probes |
| `mig_impl/` | The memory-interface implementation checks on a good case, a byte-group case and a duplicate-pin case |
| `xprobe/` | Cross-probe output of two designs (JSON and SVG device map) and timings |
| `generated_xdc_lines.txt` | The constraint lines the probes generated |

## Reproduce

The scripts and arguments are in the table of [results/project_parity_2026_1](../project_parity_2026_1/README.md). They need Vivado under a heavy slot and now write the Vivado 2026.1 records there, so these cannot be regenerated.

## Known gaps and limits

- Superseded by [results/project_parity_2026_1](../project_parity_2026_1/README.md), which re-ran every probe and compares each against these records; this folder's Vivado figures are not quoted.
- One run per probe; the cross-probe placements are single builds.
