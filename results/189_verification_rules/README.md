# Brief 189: verification and measurement rules (records)

Advisory records (`enforced: false`) written by the tools in `docs/verification_measurement_rules.md`; each is reproduced by the command shown. Simulations: Icarus Verilog 12.0, cocotb 2.0.1.

| File | Command | What it shows |
|---|---|---|
| `conservation.json` | `python3 flow/verif_lib/conservation_demo.py` | correct filter passes; silent-drop mutant fails at frame 15, 12, 7 |
| `claims_tail.json` | `python3 -m flow.claims_tail --json results/189_verification_rules/claims_tail.json` | tail percentiles quoted with too few or no observations |
| `ratchet/` | `python3 -m flow.ratchet snapshot ...`, `record`, `check` (see `docs/verification_measurement_rules.md`) | the b110 out-of-context records at 6.2 and 4.4 ns as two builds (illustrative) |
| `latency_race.json` | `python3 -m flow.latency.race_demo` | counter bench reads 2 and 4 clocks, simulator clock 3, repaired bench 3 |
| `latency_crosscheck_scan.json` | `python3 -m flow.latency.crosscheck --json ...` | latency records in `results/` with no second method |
| `cdc_skew.json`, `cdc_skew.md` | `python3 -m flow.cdc_skew_table` | binary-pointer FIFO caught at skew 2 (2 of 8 seeds) and 4 (8 of 8), not at 1; Gray FIFO never |
| `hist_split_b127_at_verdict.json`, `hist_split_b127_speculative.json` | `python3 -m flow.latency.split_hist results/b127/latency_unit_sim.json --rows latency_by_alignment.<mode> --value sop_minus_X --by end_byte_in_word` | byte lane explains 88.8 % of the latency variance |
| `tb_xcheck.json` | `python3 -m flow.tb_xcheck --json ...` | `!=` compares that raise errors in testbenches |
| `mtbf_k26_survey.json`, `mtbf_kr260_b96.json`, `mtbf_a7_no_report.json` | `python3 -m flow.mtbf <rpt> --out ...` | per-crossing MTBF from the brief-105 reports; 7-series has none |
| `level_delay.json` | `python3 -m flow.level_delay results/b89/ooc/{a7,k26}/reports/*/timing_summary.rpt --out ...` | delay per logic level and per register stage |
