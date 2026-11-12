# Traceability matrix: c12_nexys_pwm_audio

Generated 2026-11-12T02:03:34Z by `flow/traceability.py` (fpga-design-agent/trace/v1). DO-254-style evidence: a record of what was verified and how; not a claim of compliance with any standard.

Inputs: computed record; flow commit `6d4603a9bc10` (dirty tree); knowledge-bank pin `811b840`; 19 input files hashed.

| Requirement | Design elements | Method | Verification (how linked) | Result | Supporting properties |
|---|---|---|---|---|---|
| **REQ-01** Reset sets gain to 2068 and clears the sample. | - | simulation | c12_bench.test_smoke_reset_defaults (tag): pass; c12_bench.test_pin_safety_and_reset (tag): pass | pass | - |
|  |  | formal | c12_bench.test_smoke_reset_defaults (replan formal->simulation): pass | pass |  |
| **REQ-02** Gain writes above 8192 are replaced by 8192; values up to 8192 are stored exactly (tests 65535, 4000, 8192, 8193). | - | simulation | c12_bench.test_gain_clamp (tag): pass | pass | - |
|  |  | formal | c12_bench.test_gain_clamp (replan formal->simulation): pass | pass |  |
| **REQ-03** sample_out = floor(sample*gain/2^15), combinational, readable over the shell. | - | simulation | c12_bench.test_sample_sout (tag): pass; c12_bench.test_unmapped_and_ro (tag): pass; c12_bench.test_random_traffic (tag): pass; c12_bench2.test_random_pwm_sweep (tag): pass | pass | - |
|  |  | formal | c12_bench.test_sample_sout (replan formal->simulation): pass | pass |  |
| **REQ-04** Pin low count per period is 1024 - (512 + floor(sample_out/128)) for samples 0, +32767, -32768 and others. | - | simulation | c12_bench.test_pwm_low_counts (tag): pass; c12_bench2.test_random_pwm_sweep (tag): pass | pass | - |
| **REQ-05** Free-running 10-bit counter gives a 1024-clock period; duty updated once per period only. | - | simulation | c12_bench.test_period_latching (tag): pass | pass | - |
|  |  | formal | c12_bench.test_period_latching (replan formal->simulation): pass | pass |  |
| **REQ-06** AUD_PWM is never driven high (low or high-Z only). | - | simulation | c12_bench.test_pin_safety_and_reset (tag): pass | pass | - |
|  |  | formal | c12_bench.test_pin_safety_and_reset (replan formal->simulation): pass | pass |  |
|  |  | hardware | ila_captures (testplan proof): pending | pending |  |
| **REQ-07** AUD_SD is always high. | c12_nexys_pwm_audio_top | simulation | c12_bench.test_pin_safety_and_reset (tag): pass | pass | A_aud_sd_high (pass), A_rst_aud_sd (pass), C_aud_sd_high (pass), C_reset_released (pass) |
|  |  | hardware | uart_tests (testplan proof): pending | pending |  |
| **REQ-08** Reset after a write restores default gain and clears the sample. | - | simulation | c12_bench.test_pin_safety_and_reset (tag): pass | pass | - |
| **REQ-09** Timing closes at 100 MHz. | - | analysis | post_route:setup (testplan proof): pass | pass | - |
| **REQ-10** Shell at 115200 baud returns design ID PWMA; LED outputs are off. | c12_nexys_pwm_audio_top | simulation | c12_bench.test_smoke_reset_defaults (tag): pass; c12_bench.test_shell_protocol (tag): pass | pass | A_led_off (pass), C_led_off (pass), C_rx_active (pass), C_tx_active (pass) |
|  |  | hardware | uart_tests (testplan proof): pending | pending |  |

Artefacts: 19 (18 cite a requirement, 0 robustness, 1 structural, 0 untagged).

Coverage: line 8/8 (100.0 %); branch 16/16 (100.0 %); toggle 399/474 (84.18 %); bins 15/15 (100.0 %); cover 5/5 (100.0 %)

| Coverage hole | Justification |
|---|---|
| toggle: 75 points, e.g. c12_nexys_pwm_audio_top.sv:10 AUD_PWM:0->1 | **none** |

| Gate | Result | Detail |
|---|---|---|
| requirements_verified | PASS | none missing |
| artefacts_cite_requirements | PASS | none missing |
| coverage_holes_justified | FAIL | 75 coverage hole(s) neither closed nor justified: toggle c12_nexys_pwm_audio_top.sv:10 AUD_PWM:0->1, toggle c12_nexys_pwm_audio_top.sv:10 AUD_PWM:1->0, toggle c12_nexys_pwm_audio_top.sv:11 AUD_SD:1->0, toggle c12_nexys_pwm_audio_top.sv:14 LED[0]:0->1, toggle c12_nexys_pwm_audio_top.sv:14 LED[0]:1->0, toggle c12_nexys_pwm_audio_top.sv:14 LED[10]:0->1, toggle c12_nexys_pwm_audio_top.sv:14 LED[10]:1->0, toggle c12_nexys_pwm_audio_top.sv:14 LED[11]:0->1, toggle c12_nexys_pwm_audio_top.sv:14 LED[11]:1->0, toggle c12_nexys_pwm_audio_top.sv:14 LED[12]:0->1 (+65 more). Close each with a test, or justify it in verif/justifications.yaml (coverage: [{kind, item (a glob), reason, owner, date}]) |
| waivers_complete | PASS | none missing |
| changed_requirements_reverified | PASS | none missing |
