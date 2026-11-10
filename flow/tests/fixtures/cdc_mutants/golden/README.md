# Golden Vivado reports of the CDC fixtures

`<fixture>/cdc_synth.rpt` (`report_cdc -details`) and `<fixture>/cdc_paths_synth.rpt` (`flow/cdc_paths.tcl`) after
`synth_design` of each fixture in `../rtl/`, Vivado 2025.2, part xc7a100tcsg324-1, out-of-context, clocks `xdc/common.xdc`
(plus `xdc/<fixture>.xdc` where present), with AMD's XPM exceptions applied by `flow/xpm_cdc.tcl`. The host, date and
command lines of the report headers are removed. Regenerate with `run_all.sh <out dir>` under a heavy slot (about 1 to 1.5
minutes a fixture on a busy machine) and copy the two files. `flow/tests/test_16_cdc_gate.py` classifies them without Vivado.
