# Traceability matrix: t1_dimmer_counter

Generated 2026-11-12T04:19:22Z by `flow/traceability.py` (fpga-design-agent/trace/v1). DO-254-style evidence: a record of what was verified and how; not a claim of compliance with any standard.

Inputs: computed record; flow commit `5aa14219b8c6` (dirty tree); knowledge-bank pin `811b840`; 36 input files hashed.

| Requirement | Design elements | Method | Verification (how linked) | Result | Supporting properties |
|---|---|---|---|---|---|
| **REQ-01** Each debounced press steps COUNT up or down by one or clears it, wrapping modulo 65536 | debounce, dimmer_counter | simulation | t1_cocotb.bouncy_buttons_match_the_model (tag): pass; t1_cocotb.count_wraps_both_ways (tag): pass; t1_cocotb.random_operations_match_the_model (tag): pass; t1_verif.simultaneous_presses_priority (tag): pass; t1_verif.directed_closure_sweep (tag): pass; t1_verif.constrained_random_operations (tag): pass | pass | A_CT_CLEAR (pass), A_CT_UP (pass), A_CT_DOWN (pass), A_CT_HOLD (pass), C_CT_WRAP_UP (pass), C_CT_WRAP_DOWN (pass), C_CT_SAME_CLOCK_PRESSES (pass), A_DB_PULSE (pass), C_DB_PRESS (pass) |
| **REQ-02** A button change shorter than the debounce time never makes a press | debounce | simulation | t1_cocotb.debounce_boundary_is_exact (tag): pass; t1_cocotb.bouncy_buttons_match_the_model (tag): pass; t1_verif.short_glitches_are_ignored (tag): pass | pass | A_DB_RISE (pass), A_DB_RISE_ONLY (pass), A_DB_HOLD (pass), A_DB_FLIP (pass), C_DB_GLITCH_IGNORED (pass) |
|  |  | formal | debounce (tag): pass | pass |  |
| **REQ-03** LED brightness is linear in the effective duty over one PWM period | dimmer_counter | simulation | t1_cocotb.pwm_on_time_matches_duty (tag): pass | pass | A_PWM_SUBSET (pass), A_PWM_ZERO_OFF (pass), C_CT_DUTY_FULL (pass) |
| **REQ-04** The display lights exactly one digit at a time, in order, showing COUNT and the duty in hex | sevenseg_scan | simulation | t1_cocotb.display_shows_count_and_duty (tag): pass; t1_verif.directed_closure_sweep (tag): pass | pass | A_SC_ONE_DIGIT (pass), A_SC_BLANK (pass), A_SC_DISABLED (pass), C_SC_DIGIT_0_LIT (pass), C_SC_DIGIT_1_LIT (pass), C_SC_DIGIT_2_LIT (pass), C_SC_DIGIT_3_LIT (pass), C_SC_DIGIT_4_LIT (fail), C_SC_DIGIT_5_LIT (fail), C_SC_DIGIT_6_LIT (pass), C_SC_DIGIT_7_LIT (pass), C_SC_ALL_DARK_ENABLED (pass) |
|  |  | formal | scan (tag): pass | pass |  |
| **REQ-05** The register window has the listed map and reset values | dimmer_counter | simulation | t1_cocotb.identity_and_reset_values (tag): pass; t1_cocotb.inputs_register_shows_levels (tag): pass; t1_cocotb.random_operations_match_the_model (tag): pass; t1_verif.directed_closure_sweep (tag): pass; t1_verif.reset_state_of_outputs (tag): pass; t1_verif.constrained_random_operations (tag): pass | pass | A_CT_RESET (pass), A_CT_PRESS_COUNTED_UP (pass), A_CT_PRESS_COUNTED_DOWN (pass), A_CT_PRESS_COUNTED_CLEAR (pass), A_CT_DUTY_WRITE (pass), A_CT_CTRL_WRITE (pass), A_CT_RO_IGNORED (pass) |
| **REQ-06** The design closes timing at 100 MHz with no unconstrained path | t1_dimmer_counter_top | analysis | post_route:setup (testplan proof): pass; post_route:hold (testplan proof): pass; post_route:no_unconstrained_endpoints (testplan proof): pass | pass | - |
| **REQ-07** The design stays within its predicted LUT and FF ranges, with no BRAM or DSP | t1_dimmer_counter_top | analysis | post_synth:post_synth_resources_in_range (testplan proof): pass | pass | - |
| **REQ-08** On the board the register window answers as the model predicts | t1_dimmer_counter_top | hardware | uart_tests:test_t1_registers_against_the_model (testplan proof): pass | pass | - |
| **REQ-09** A shell write to COUNT on the same clock as a press wins over the press | dimmer_counter | simulation | t1_cocotb.register_write_and_press_on_the_same_clock (tag): pass; t1_verif.constrained_random_operations (tag): pass | pass | A_CT_WRITE_WINS (pass), C_CT_WRITE_AND_PRESS (pass) |
| **REQ-10** Releasing a button never makes a press | debounce | simulation | t1_cocotb.debounce_boundary_is_exact (tag): pass | pass | A_DB_FALL_NO_PRESS (pass), C_DB_RELEASE (pass) |
|  |  | formal | debounce (tag): pass | pass |  |
| **REQ-11** On the board the ILA captures of the count write and the PWM agree with the model | t1_dimmer_counter_top | hardware | ila_captures (testplan proof): pass | pass | - |

Artefacts: 57 (56 cite a requirement, 0 robustness, 1 structural, 0 untagged).

Coverage: line 36/36 (100.0 %); branch 28/28 (100.0 %); toggle 759/870 (87.24 %); bins 69/69 (100.0 %); cover 15/17 (88.24 %)

| Coverage hole | Justification |
|---|---|
| toggle: 6 points, e.g. dimmer_counter.sv:18 an[4]:1->0 | re:.* (an\|AN)\[[45]\]:1->0: The anodes of digits 4 and 5 are never driven low (spec display: those digits stay dark). |
| toggle: 16 points, e.g. dimmer_counter.sv:27 win_rdata[20]:0->1 | re:.*win_rdata\[2[0-3]\]:.*: Read-back of PRESSES bits 23:20 (the clear counter's bits 7:4); the same gap as the counter bits above. |
| toggle: 32 points, e.g. dimmer_counter.sv:27 win_rdata[24]:0->1 | re:.*win_rdata\[(2[4-9]\|3[01])\]:.*: Bits 31:24 of the read data are 0 for every register (spec registers.map); they are constant by design. |
| toggle: 24 points, e.g. dimmer_counter.sv:35 n_clear[4]:0->1 | re:dimmer_counter\.sv:\d+ n_(up\|down\|clear)\[[4-7]\]:.*: Open gap, justified only by similarity (not elemental analysis): no seed presses one button 16 or more times, so bits 7:4 of the three 8-bit PRESSES counters never change. Each counter is one incrementer whose low bits are exercised; a test with 256 presses of each button would close it. |
| toggle: 2 points, e.g. dimmer_counter.sv:38 pre[2]:0->1 | dimmer_counter.sv:* pre[2]:*: The prescaler is $clog2(PWM_PRESCALE + 1) bits wide; at PWM_PRESCALE 4 it counts 0 to 3, so its top bit is always 0. Constant for this parameter value. |
| toggle: 8 points, e.g. sevenseg_scan.sv:13 digits[16]:0->1 | re:sevenseg_scan\.sv:\d+ digits\[(1[6-9])\]:.*: Digit 4's glyph input is tied to 0 (spec display: digits 4 and 5 are blank). |
| toggle: 8 points, e.g. sevenseg_scan.sv:13 digits[20]:0->1 | re:sevenseg_scan\.sv:\d+ digits\[(2[0-3])\]:.*: Digit 5's glyph input is tied to 0 (spec display: digits 4 and 5 are blank). |
| toggle: 14 points, e.g. sevenseg_scan.sv:14 blank[0]:0->1 | sevenseg_scan.sv:* blank[*]:*: The blank mask is the constant 8'b0011_0000 (digits 4 and 5 blank by the spec); it never changes. |
| toggle: t1_dimmer_counter_top.sv:21 DP:1->0 | t1_dimmer_counter_top.sv:* DP:1->0: The decimal point is always off (spec display: DP is always 1). |
| cover: 2 points, e.g. C_SC_DIGIT_4_LIT | re:C_SC_DIGIT_[45]_LIT: Unreachable by the spec: digits 4 and 5 are blank, so these covers must stay unhit (a hit would be a bug, and A_SC_BLANK would also fire). |

| Waiver | Item | Problem |
|---|---|---|
| justifications.coverage | re:.*win_rdata\[(2[4-9]\|3[01])\]:.* | complete |
| justifications.coverage | re:dimmer_counter\.sv:\d+ n_(up\|down\|clear)\[[4-7]\]:.* | complete |
| justifications.coverage | re:.*win_rdata\[2[0-3]\]:.* | complete |
| justifications.coverage | dimmer_counter.sv:* pre[2]:* | complete |
| justifications.coverage | re:sevenseg_scan\.sv:\d+ digits\[(1[6-9])\]:.* | complete |
| justifications.coverage | re:sevenseg_scan\.sv:\d+ digits\[(2[0-3])\]:.* | complete |
| justifications.coverage | sevenseg_scan.sv:* blank[*]:* | complete |
| justifications.coverage | re:.* (an\|AN)\[[45]\]:1->0 | complete |
| justifications.coverage | t1_dimmer_counter_top.sv:* DP:1->0 | complete |
| justifications.coverage | re:C_SC_DIGIT_[45]_LIT | complete |
| justifications.reconfirmed | REQ-08 | complete |
| justifications.reconfirmed | REQ-11 | complete |
| lint/waivers.yaml | HDL-XDC-01 | complete |

| Gate | Result | Detail |
|---|---|---|
| requirements_verified | PASS | none missing |
| artefacts_cite_requirements | PASS | none missing |
| coverage_holes_justified | PASS | none missing |
| waivers_complete | PASS | none missing |
| changed_requirements_reverified | PASS | none missing |
