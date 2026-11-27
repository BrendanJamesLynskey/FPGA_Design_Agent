
## models by role (profile single)

clarify: deepagents claude-sonnet-5-5 (medium); model: deepagents claude-sonnet-5-5 (medium); tests: deepagents claude-sonnet-5-5 (medium); rtl: deepagents claude-sonnet-5-5 (medium). Interview oracle: claude-sonnet-5-5 (the oracle purpose). The stage machine is plain code.

<!-- who-did-what:start -->
## Who did what

| # | who | stage | what | detail |
|---|---|---|---|---|
| 1 | owner | start | verification profile | standard with overrides {'verif_level': 'V2'} |
| 2 | agent | clarify | stage 0 work, visit 1 | 7 files in the design |
| 3 | agent | clarify | stage 0 work, visit 2 | 7 files in the design |
| 4 | auto | clarify | interview | defaulted: Which divide should be applied to the GT reference clock for clock B? -> 2 (78.125 MHz), fixed at build time |
| 5 | auto | clarify | interview | defaulted: What happens when SEL is written while SWITCHING is 1? -> The new value is taken and the mux follows the latest SEL once the current hands |
| 6 | auto | clarify | interview | defaulted: What happens when START is written while BUSY, or GATE_LEN is 0 or changed during a gate? -> START while BUSY is ignored; GATE_LEN is sampled at START; GATE_LEN 0 is treated |
| 7 | auto | clarify | interview | defaulted: Should SWITCH_COUNT count a write of the SEL value already selected? -> No, only real changes of ACTIVE_SEL count |
| 8 | auto | clarify | interview | defaulted: What do the LEDs show? -> led[0] = ACTIVE_SEL, led[1] = SWITCHING |
| 9 | auto | clarify | interview | defaulted: What is the exact register map? -> As listed in registers.map, taken from spec.md (all offsets given) |
| 10 | auto | clarify | interview | defaulted: Width of the muxed counter and error counter saturation? -> 64-bit counter, 32-bit saturating error count |
| 11 | auto | clarify | interview | defaulted: This design has no reset input. Is every reset a reconfiguration of the FPGA (the device is reprogrammed, so every regis -> Every reset is a reconfiguration of the FPGA (reset model: reprogram): registers |
| 12 | auto | clarify | approved (review off) |  |
| 13 | agent | board-and-device-planning | stage 1 work, visit 1 | 9 files in the design |
| 14 | agent | board-and-device-planning | stage 1 work, visit 2 | 10 files in the design |
| 15 | auto | board-and-device-planning | approved (review off) |  |
| 16 | auto | board-and-device-planning | architecture approved | source: agent |
| 17 | agent | rtl-design-creation | stage 2 work, visit 1 | 19 files in the design |
| 18 | agent | rtl-design-creation | stage 2 work, visit 2 | 20 files in the design |
| 19 | agent | rtl-design-creation | stage 2 work, visit 3 | 20 files in the design |
| 20 | agent | rtl-design-creation | stage 2 work, visit 4 | 20 files in the design |
| 21 | agent | rtl-design-creation | stage 2 work, visit 5 | 20 files in the design |
| 22 | agent | rtl-design-creation | stage 2 work, visit 6 | 20 files in the design |

owner: 1, agent: 10, auto: 11
<!-- who-did-what:end -->

## review 00 clarify

approve by auto (gates fail)

## review 00 clarify

approve by auto (gates pass)

## review 01 board-and-device-planning

approve by auto (gates fail)

## review 01 board-and-device-planning

approve by auto (gates pass)

## architecture approval

approved (auto); written by the agent; sha256 4caac95fbc59

## review 02 rtl-design-creation

approve by auto (gates fail)

## review 02 rtl-design-creation

approve by auto (gates fail)

## review 02 rtl-design-creation

approve by auto (gates fail)

## review 02 rtl-design-creation

approve by auto (gates fail)

## review 02 rtl-design-creation

approve by auto (gates fail)

## review 02 rtl-design-creation

approve by auto (gates fail)

## review 02 rtl-design-creation

approve by auto (gates fail)
