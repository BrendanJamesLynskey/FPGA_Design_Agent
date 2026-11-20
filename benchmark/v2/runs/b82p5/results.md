# b82p5 result (written from `records/*planted_A_r1.json` and `posthoc/gate_events.json`; one run, pre-registered in `preregistration.md`)

| Item | Value |
|---|---|
| Run | 20261120-140630-340a (planted spec, arm A, L2, Sonnet `claude-sonnet-5-5` via claude_code, Haiku oracle, CLI 2.1.321) |
| Code | frozen `05fe441d` (origin/main 031dd994 plus b82p5 files) |
| Stop | stage 2 visited more than 6 times (stage 2 visits: 7), clean stop: False |
| Own stage-2 gates | fail (V2 `failing_tests`: the bench's own `test_reset_and_id` and `test_clock_period_design_id`, which assert the planted wrong ID) |
| Constants gate at the end | ran, blocking: [] (the final RTL binds the right ID) |
| Hidden bench | 10/10 (not the test of the gate) |
| Wall | 62.9 min; tokens 3831101; plan-equivalent cost 5.1791 USD |
| Weekly usage before | 43.0% |

## Shell DESIGN_ID default in the top module, per stage-2 visit (`posthoc/gate_events.json`)

| Visit | Snapshot | Value | Right? |
|---|---|---|---|
| 1 | 2:5 | 0x55445031 | no (planted) |
| 2 | 2:6 | 0x55445031 | no |
| 3 | 2:7 | 0x55445031 | no |
| 4 | 2:8 | 0x55455031 (R0 kept 0x55445031 in `R0_ID`) | yes |
| 5 | 2:9 | 0x55445031 | no (reverted by the RTL role to satisfy the bench) |
| 6 | 2:10 | 0x55455031 | yes |
| (limit) | 2:11 | 0x55455031 | yes |

Outcome by the pre-registered table: **ID plant: gate test passed** (the RTL bound the wrong value, the gate named both values (the RTL role quotes the finding at visits 1 (through its `check` call), 2, 3, 4 and 6; the visit-5 input was the
simulation failure, since the ID was right at that point; the role kept the planted word at visits 1 to 3 and again at visit 5); the right value was bound at visits 4 and 6 and in the final RTL; the run then ended on the stage-2 visit limit
because the bench, `model.py` and `spec.yaml` carry the planted wrong word, which the RTL role may not edit: gate and bench disagree). **Clock plant: not
exercised** (the clarify stage first wrote `period_ns: 8` in spec.yaml and rewrote it to 10 within the same stage; `design.xdc` was written with
`-period 10.00`; no `CONST-CLK-01`). No false positive; no gate failure.
