
## models by role (profile single)

clarify: deepagents claude-sonnet-5-5 (medium); model: deepagents claude-sonnet-5-5 (medium); tests: deepagents claude-sonnet-5-5 (medium); rtl: deepagents claude-sonnet-5-5 (medium). Interview oracle: claude-sonnet-5-5 (the oracle purpose). The stage machine is plain code.

<!-- who-did-what:start -->
## Who did what

| # | who | stage | what | detail |
|---|---|---|---|---|
| 1 | owner | start | verification profile | standard with overrides {'verif_level': 'V2'} |
| 2 | agent | clarify | stage 0 work, visit 1 | 8 files in the design |
| 3 | agent | clarify | stage 0 work, visit 2 | 8 files in the design |
| 4 | auto | clarify | interview | defaulted: What is the register map (offset, width, reset value and access of every register)? -> The map in registers.map: ID 0x000 RO, BUILD 0x004 RO, SCRATCH 0x008 RW, CTRL 0x |
| 5 | auto | clarify | interview | defaulted: Which pin or bus signal gives the design reset, and is it only the jtag_bus rst? -> Use jtag_bus rst only, synchronised into clk_dp. |
| 6 | auto | clarify | interview | defaulted: What happens when RUN is written while BUSY? -> Ignored. |
| 7 | auto | clarify | interview | defaulted: What if the output FIFO lacks room for all queued inputs at RUN? -> Process only as many samples as free output space; the rest stay in the input FI |
| 8 | auto | clarify | interview | defaulted: Does CLEAR written while BUSY abort the run? -> Yes, abort and clear everything. |
| 9 | auto | clarify | interview | defaulted: Are CTRL bits read back as 0 and does writing both bits at once do CLEAR first then RUN? -> CTRL reads 0; CLEAR wins and RUN is dropped when both are set. |
| 10 | auto | clarify | interview | defaulted: Does writing IN_PUSH or reading OUT_POP while BUSY have defined behaviour? -> Push accepted into the FIFO while busy (processed in a later RUN or the same run |
| 11 | auto | clarify | interview | defaulted: What do the LEDs show? -> led[0]=BUSY, led[1]=heartbeat from clk25. |
| 12 | auto | clarify | interview | defaulted: Do SAT_COUNT and SAMPLES_DONE wrap at 32 bits? -> Wrap at 2^32. |
| 13 | auto | clarify | interview | defaulted: This design has no reset input. Is every reset a reconfiguration of the FPGA (the device is reprogrammed, so every regis -> Every reset is a reconfiguration of the FPGA (reset model: reprogram): registers |
| 14 | auto | clarify | approved (review off) |  |
| 15 | agent | board-and-device-planning | stage 1 work, visit 1 | 10 files in the design |
| 16 | agent | board-and-device-planning | stage 1 work, visit 2 | 11 files in the design |
| 17 | agent | board-and-device-planning | stage 1 work, visit 3 | 11 files in the design |
| 18 | auto | board-and-device-planning | approved (review off) |  |
| 19 | auto | board-and-device-planning | architecture approved | source: agent |
| 20 | agent | rtl-design-creation | stage 2 work, visit 1 | 22 files in the design |
| 21 | agent | rtl-design-creation | stage 2 work, visit 2 | 24 files in the design |
| 22 | agent | rtl-design-creation | stage 2 work, visit 3 | 24 files in the design |
| 23 | auto | rtl-design-creation | approved (review off) |  |
| 24 | agent | constraints | stage 3 work, visit 1 | 24 files in the design |
| 25 | agent | rtl-design-creation | stage 2 work, visit 4 | 24 files in the design |
| 26 | agent | rtl-design-creation | stage 2 work, visit 5 | 24 files in the design |
| 27 | auto | rtl-design-creation | approved (review off) |  |
| 28 | agent | constraints | stage 3 work, visit 2 | 24 files in the design |
| 29 | agent | rtl-design-creation | stage 2 work, visit 6 | 24 files in the design |
| 30 | auto | rtl-design-creation | approved (review off) |  |
| 31 | agent | constraints | stage 3 work, visit 3 | 24 files in the design |
| 32 | agent | constraints | stage 3 work, visit 4 | 24 files in the design |

owner: 1, agent: 15, auto: 16
<!-- who-did-what:end -->

## review 00 clarify

approve by auto (gates fail)

## review 00 clarify

approve by auto (gates pass)

## review 01 board-and-device-planning

approve by auto (gates fail)

## review 01 board-and-device-planning

approve by auto (gates fail)

## review 01 board-and-device-planning

approve by auto (gates pass)

## architecture approval

approved (auto); written by the agent; sha256 94579578c48d

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

## review 02 rtl-design-creation

approve by auto (gates pass)

## review 03 constraints

approve by auto (gates fail)

## review 02 rtl-design-creation

approve by auto (gates pass)

## review 03 constraints

approve by auto (gates fail)

## review 03 constraints

approve by auto (gates fail)

## review 02 rtl-design-creation

approve by auto (gates fail)
