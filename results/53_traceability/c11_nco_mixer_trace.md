# Traceability matrix: c11_nco_mixer

Generated 2026-11-12T02:03:33Z by `flow/traceability.py` (fpga-design-agent/trace/v1). DO-254-style evidence: a record of what was verified and how; not a claim of compliance with any standard.

Inputs: computed record; flow commit `6d4603a9bc10` (dirty tree); knowledge-bank pin `811b840`; 21 input files hashed.

| Requirement | Design elements | Method | Verification (how linked) | Result | Supporting properties |
|---|---|---|---|---|---|
| **REQ-01** Result pair appears exactly one clock after each enabled clock and on no other clock | c11_nco_mixer_top | simulation | c11_nco_mixer_bench.test_single_burst_directed (tag): pass; c11_nco_mixer_bench.test_tone_bursts (tag): pass; c11_nco_mixer_bench.test_gap_patterns (tag): pass | pass | C_rx_line_busy (pass), C_tx_line_busy (pass) |
|  |  | formal | c11_nco_mixer_bench.test_single_burst_directed (replan formal->simulation): pass | pass |  |
| **REQ-02** Phase is 0 after reset, advances by fw on each enabled clock with wrap, and holds on other clocks | - | simulation | c11_nco_mixer_bench.test_phase_continuity_and_hold (tag): pass; c11_nco_mixer_bench.test_full_scale (tag): pass | pass | - |
|  |  | formal | c11_nco_mixer_bench.test_phase_continuity_and_hold (replan formal->simulation): pass | pass |  |
| **REQ-03** Table of 256 entries S[k]=floor(16383*sin(2*pi*k/256)+0.5), cosine S[(k+64) mod 256], index is top 8 bits of phase before the advance | - | simulation | c11_nco_mixer_bench.test_table_sweep (tag): pass | pass | - |
| **REQ-04** i_out=floor(x*c/2^14) and q_out=floor(-x*s/2^14) as signed 12-bit | - | simulation | c11_nco_mixer_bench.test_full_scale (tag): pass; c11_nco_mixer_bench.test_random_traffic (tag): pass | pass | - |
| **REQ-05** CPU_RESETN clears phase and loaded values | - | simulation | c11_nco_mixer_bench.test_reset_clears (tag): pass | pass | - |
|  |  | hardware | uart_tests (testplan proof): pending | pending |  |
| **REQ-06** Design closes timing at 100 MHz | - | analysis | post_route:setup (testplan proof): pass | pass | - |
| **REQ-07** Shell can set fw, load up to 16 samples, set a 32-bit pattern and go; a 1 bit presents the next sample in order | - | simulation | c11_nco_mixer_bench.test_smoke_id_and_regs (tag): pass; c11_nco_mixer_bench.test_single_burst_directed (tag): pass; c11_nco_mixer_bench.test_gap_patterns (tag): pass | pass | - |
|  |  | hardware | uart_tests (testplan proof): pending | pending |  |
| **REQ-08** Phase keeps running from one burst to the next | - | simulation | c11_nco_mixer_bench.test_phase_continuity_and_hold (tag): pass; c11_nco_mixer_bench.test_tone_bursts (tag): pass | pass | - |
|  |  | hardware | uart_tests (testplan proof): pending | pending |  |
| **REQ-09** Results readable in order, with result count and 32-bit record of clocks with a result | - | simulation | c11_nco_mixer_bench.test_single_burst_directed (tag): pass; c11_nco_mixer_bench.test_gap_patterns (tag): pass | pass | - |
|  |  | hardware | uart_tests (testplan proof): pending | pending |  |
| **REQ-10** 1500 samples (random, tone, full scale, with gaps, several fw) match the model on every pair | - | simulation | c11_nco_mixer_bench.test_table_sweep (tag): pass; c11_nco_mixer_bench.test_random_traffic (tag): pass; c11_nco_mixer_bench.test_random_dense_many_fw (tag): pass | pass | - |
|  |  | hardware | uart_tests (testplan proof): pending | pending |  |
| **REQ-11** UART at 115200 baud (CLKS_PER_BIT 868) and design ID NCOM | - | simulation | c11_nco_mixer_bench.test_smoke_id_and_regs (tag): pass; c11_nco_mixer_bench.test_shell_errors (tag): pass | pass | - |
|  |  | hardware | uart_tests (testplan proof): pending | pending |  |
| **REQ-12** Top c11_nco_mixer_top exposes CLKS_PER_BIT, TIMEOUT_CYCLES, BUILD_STAMP parameters and master-XDC port names | - | analysis | post_synth:post_synth_resources_in_range (testplan proof): pass | pass | - |

Artefacts: 14 (13 cite a requirement, 0 robustness, 1 structural, 0 untagged).

Coverage: line 17/17 (100.0 %); branch 36/36 (100.0 %); toggle 2792/2792 (100.0 %); bins 13/13 (100.0 %); cover 2/2 (100.0 %)

| Gate | Result | Detail |
|---|---|---|
| requirements_verified | PASS | none missing |
| artefacts_cite_requirements | PASS | none missing |
| coverage_holes_justified | PASS | none missing |
| waivers_complete | PASS | none missing |
| changed_requirements_reverified | PASS | none missing |
