
## models by role (profile single)

clarify: deepagents claude-sonnet-5-5 (medium); model: deepagents claude-sonnet-5-5 (medium); tests: deepagents claude-sonnet-5-5 (medium); rtl: deepagents claude-sonnet-5-5 (medium). Interview oracle: claude-sonnet-5-5 (the oracle purpose). The stage machine is plain code.

<!-- who-did-what:start -->
## Who did what

| # | who | stage | what | detail |
|---|---|---|---|---|
| 1 | owner | start | verification profile | standard with overrides {'verif_level': 'V2'} |
| 2 | agent | clarify | stage 0 work, visit 1 | 8 files in the design |
| 3 | agent | clarify | stage 0 work, visit 2 | 8 files in the design |
| 4 | agent | clarify | stage 0 work, visit 3 | 8 files in the design |
| 5 | agent | clarify | stage 0 work, visit 4 | 8 files in the design |
| 6 | auto | clarify | interview | defaulted: What is the register map (offset, width, reset value and access of every register)? -> The map given in spec.md: ID 0x000, BUILD 0x004, SCRATCH 0x008, CTRL 0x010, IN_P |
| 7 | auto | clarify | interview | defaulted: What happens if RUN is written while BUSY is 1? -> The write is ignored. |
| 8 | auto | clarify | interview | defaulted: What happens when the output FIFO is full during a run? -> The run is limited so it never overflows: processing stalls until the output FIF |
| 9 | auto | clarify | interview | defaulted: What happens when IN_PUSH is written while BUSY is 1? -> The sample is accepted if the FIFO is not full, and is processed by the next RUN |
| 10 | auto | clarify | interview | defaulted: Do SAT_COUNT and SAMPLES_DONE wrap or saturate at 2^32? -> They wrap. |
| 11 | auto | clarify | interview | defaulted: What do led[1:0] show? -> led[0] = BUSY, led[1] = MMCM locked. |
| 12 | auto | clarify | interview | defaulted: Is the 250 MHz clock a target or may a faster one such as 300 MHz be used? -> 250 MHz exactly from the MMCM. |
| 13 | auto | clarify | interview | defaulted: Does the BUILD register read 0 in simulation? -> Yes, the USR_ACCESSE2 primitive is replaced by a 0 constant (or a testbench word |
| 14 | auto | clarify | interview | defaulted: This design has no reset input. Is every reset a reconfiguration of the FPGA (the device is reprogrammed, so every regis -> Every reset is a reconfiguration of the FPGA (reset model: reprogram): registers |
| 15 | auto | clarify | approved (review off) |  |
| 16 | agent | board-and-device-planning | stage 1 work, visit 1 | 10 files in the design |
| 17 | agent | board-and-device-planning | stage 1 work, visit 2 | 11 files in the design |
| 18 | auto | board-and-device-planning | approved (review off) |  |
| 19 | auto | board-and-device-planning | architecture approved | source: agent |
| 20 | agent | rtl-design-creation | stage 2 work, visit 1 | 16 files in the design |
| 21 | agent | rtl-design-creation | stage 2 work, visit 2 | 21 files in the design |
| 22 | agent | rtl-design-creation | stage 2 work, visit 3 | 22 files in the design |
| 23 | agent | rtl-design-creation | stage 2 work, visit 4 | 22 files in the design |
| 24 | agent | rtl-design-creation | stage 2 work, visit 5 | 22 files in the design |
| 25 | agent | rtl-design-creation | stage 2 work, visit 6 | 22 files in the design |
| 26 | auto | rtl-design-creation | approved (review off) |  |
| 27 | agent | constraints | stage 3 work, visit 1 | 22 files in the design |

owner: 1, agent: 13, auto: 13
<!-- who-did-what:end -->

## review 00 clarify

approve by auto (gates fail)

## review 00 clarify

approve by auto (gates fail)

## review 00 clarify

approve by auto (gates fail)

## review 00 clarify

approve by auto (gates pass)

## review 01 board-and-device-planning

approve by auto (gates fail)

## review 01 board-and-device-planning

approve by auto (gates pass)

## architecture approval

approved (auto); written by the agent; sha256 2ff3bae7933f

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

approve by auto (gates pass)

## review 03 constraints

approve by auto (gates fail)

## review 02 rtl-design-creation

approve by auto (gates fail)
