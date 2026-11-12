| id | what | Vivado rules | ignored / coverage | WNS / WHS after synthesis | without the exception (re-timed after routing where routed) | after routing | flow flags (why) | expected |
|---|---|---|---|---|---|---|---|---|
| E1 | 2-cycle enable multiply, -setup 2 and -hold 1 | none | none / [32, 32] | +1.647 / +0.293 | -4.615 / +0.243 | +0.385 / +0.243 | no (-) | clean |
| E2 | same, -setup 2 with no -hold | XDCH-1 | none / [32] | +1.647 / -4.721 | -3.353 / +0.293 | - | **yes** (XDCH-1, FDA-CON-10, slack) | flag |
| E3 | multicycle on registers with CE tied high | none | none / [32, 32] | +1.647 / +0.314 | -4.591 / +0.364 | +0.409 / +0.364 | **yes** (EXC-MCP-ENABLE) | flag |
| E4 | false path between two MMCM outputs (synchronous) | TIMING-47 | none / [16] | +3.546 / +0.132 | +3.406 / -0.011 | - | **yes** (TIMING-47) | flag |
| E5 | false path over an 8-bit binary bus crossing | none | none / [8] | +6.175 / +0.164 | -0.121 / +0.164 | - | **yes** (CDC unsafe) | flag |
| E6 | multicycle whose -to has a typo (matches nothing) | TIMING-16 | none / [] | -3.202 / +0.293 | -3.202 / +0.293 | - | **yes** (EXC-XDC-MSG, slack) | flag |
| E6B | multicycle between registers with no path | TIMING-16 | Non-existent path; Non-existent path / [0, 0] | -3.202 / +0.293 | -3.202 / +0.293 | - | **yes** (EXC-IGNORED, slack) | flag |
| E7 | datapath-only max delay overridden by a clock group | TIMING-24 | Totally overridden path by CG 4 / [4] | +6.175 / +0.164 | -0.101 / +0.164 | - | **yes** (EXC-IGNORED, TIMING-24, CDC unsafe) | flag |
| E8 | 100 -> 200 MHz multicycle, -setup 2 -end / -hold 1 -end | none | none / [16, 16] | +3.546 / -0.011 | +1.911 / +0.145 | +3.364 / +0.145 | no (-) | clean |
| E8B | same crossing written with -start | none | none / [16, 16] | +3.546 / -0.011 | +1.911 / +0.145 | +3.364 / +0.145 | **yes** (EXC-MCP-ENABLE) | flag |
| E9 | quasi-static bit, 2-flop sync, commented false path | none | none / [1] | +5.639 / +0.164 | -0.094 / +0.164 | - | no (-) | clean |
| E10 | slow FSM on 125 MHz, 1-in-8 enable, multicycle 8/7 on tagged registers | none | none / [64, 64] | +4.337 / +0.189 | -5.709 / +0.188 | +4.110 / +0.188 | no (-) | clean |
| E10B | E10 with the consumer copying every clock (not qualified) | none | none / [64, 64] | +4.337 / +0.189 | -6.807 / +0.164 | +3.864 / +0.164 | **yes** (EXC-MCP-ENABLE) | flag |
| E10C | E10 with the multicycle on all_registers | none | none / [214, 214] | +54.478 / +0.189 | -1.522 / +0.189 | - | **yes** (EXC-MCP-ENABLE) | flag |
| E10D | E10 alternative: FSM on a fabric-divided clock (BUFG), no exception | none | none / [] | +4.280 / +0.070 | +3.964 / +0.156 | +3.964 / +0.156 | no (-) | - |
