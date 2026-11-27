
## models by role (profile single)

clarify: deepagents claude-sonnet-5-5 (medium); model: deepagents claude-sonnet-5-5 (medium); tests: deepagents claude-sonnet-5-5 (medium); rtl: deepagents claude-sonnet-5-5 (medium). Interview oracle: claude-sonnet-5-5 (the oracle purpose). The stage machine is plain code.

<!-- who-did-what:start -->
## Who did what

| # | who | stage | what | detail |
|---|---|---|---|---|
| 1 | owner | start | verification profile | standard with overrides {'verif_level': 'V2'} |
| 2 | agent | clarify | stage 0 work, visit 1 | 8 files in the design |
| 3 | agent | clarify | stage 0 work, visit 2 | 8 files in the design |
| 4 | auto | clarify | interview | defaulted: Is the register map exactly the offsets in the request (0x000-0x008 common, 0x010-0x024 FIR)? -> Yes, use the map in registers.map with the offsets, widths, reset values and acc |
| 5 | auto | clarify | interview | defaulted: What do writes to IN_PUSH while BUSY, and RUN with an empty input FIFO, do? -> IN_PUSH while BUSY is accepted if not full; RUN with empty FIFO finishes at once |
| 6 | auto | clarify | interview | defaulted: What happens if the output FIFO would overflow (input count plus output count above 1024)? -> Processing stalls until the output FIFO has room (no sample lost). |
| 7 | auto | clarify | interview | defaulted: Reading OUT_POP when BUSY or STATUS counts while BUSY: are they coherent? -> Counts are the live values, synchronised to clk25 with at most a few cycles of l |
| 8 | auto | clarify | interview | defaulted: Do CLEAR and RUN written in the same CTRL write both act? -> CLEAR wins and RUN is ignored. |
| 9 | auto | clarify | interview | defaulted: What do the LEDs show? -> led[0] = BUSY, led[1] = MMCM locked. |
| 10 | auto | clarify | interview | defaulted: Does RUN written while BUSY restart or queue? -> Ignored while BUSY. |
| 11 | auto | clarify | interview | defaulted: This design has no reset input. Is every reset a reconfiguration of the FPGA (the device is reprogrammed, so every regis -> Every reset is a reconfiguration of the FPGA (reset model: reprogram): registers |
| 12 | auto | clarify | approved (review off) |  |
| 13 | agent | board-and-device-planning | stage 1 work, visit 1 | 10 files in the design |
| 14 | agent | board-and-device-planning | stage 1 work, visit 2 | 11 files in the design |
| 15 | auto | board-and-device-planning | approved (review off) |  |
| 16 | auto | board-and-device-planning | architecture approved | source: agent |
| 17 | agent | rtl-design-creation | stage 2 work, visit 1 | 20 files in the design |
| 18 | agent | rtl-design-creation | stage 2 work, visit 2 | 21 files in the design |
| 19 | agent | rtl-design-creation | stage 2 work, visit 3 | 22 files in the design |
| 20 | auto | rtl-design-creation | approved (review off) |  |
| 21 | agent | constraints | stage 3 work, visit 1 | 22 files in the design |
| 22 | agent | rtl-design-creation | stage 2 work, visit 4 | 22 files in the design |
| 23 | auto | rtl-design-creation | approved (review off) |  |
| 24 | agent | constraints | stage 3 work, visit 2 | 22 files in the design |
| 25 | auto | constraints | approved (review off) |  |
| 26 | agent | synthesis | stage 4 work, visit 1 | 22 files in the design |
| 27 | agent | board-and-device-planning | stage 1 work, visit 3 | 22 files in the design |
| 28 | agent | board-and-device-planning | stage 1 work, visit 4 | 22 files in the design |

owner: 1, agent: 13, auto: 14
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

approved (auto); written by the agent; sha256 a561b4170188

## review 02 rtl-design-creation

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

approve by auto (gates pass)

## review 04 synthesis

approve by auto (gates fail)

## review 01 board-and-device-planning

approve by auto (gates fail)

## review 01 board-and-device-planning

approve by auto (gates fail)

## review 01 board-and-device-planning

approve by auto (gates fail)
