
## models by role (profile single)

clarify: deepagents claude-sonnet-5-5 (medium); model: deepagents claude-sonnet-5-5 (medium); tests: deepagents claude-sonnet-5-5 (medium); rtl: deepagents claude-sonnet-5-5 (medium). Interview oracle: claude-sonnet-5-5 (the oracle purpose). The stage machine is plain code.

<!-- who-did-what:start -->
## Who did what

| # | who | stage | what | detail |
|---|---|---|---|---|
| 1 | owner | start | verification profile | standard with overrides {'verif_level': 'V2'} |
| 2 | agent | clarify | stage 0 work, visit 1 | 7 files in the design |
| 3 | agent | clarify | stage 0 work, visit 2 | 7 files in the design |
| 4 | auto | clarify | interview | defaulted: Which clock drives jtag_bus and the register block? -> clk_wr (25 MHz) |
| 5 | auto | clarify | interview | defaulted: What happens to words still in the FIFO when RUN falls? -> The reader keeps draining and checking until empty; the writer stops. |
| 6 | auto | clarify | interview | defaulted: Which bit does INJECT flip? -> Bit 0 of the next word read after INJECT is seen by the reader. |
| 7 | auto | clarify | interview | defaulted: Does a CLEAR with RUN 1 set any error flag? -> No, it is ignored silently and the bit still self-clears. |
| 8 | auto | clarify | interview | defaulted: What do snapshot registers read before the first SNAPSHOT write? -> 0 |
| 9 | auto | clarify | interview | defaulted: Should the LEDs show anything? -> led[0] = RUN, led[1] = any error seen (DATA_ERRS, OVERFLOWS or UNDERFLOWS nonzer |
| 10 | auto | clarify | interview | defaulted: Please confirm the register map (offset, width, reset value and access of every register). -> The map in registers.map: 0x000 ID, 0x004 BUILD, 0x008 SCRATCH, 0x010 CTRL, 0x01 |
| 11 | auto | clarify | interview | defaulted: This design has no reset input. Is every reset a reconfiguration of the FPGA (the device is reprogrammed, so every regis -> Every reset is a reconfiguration of the FPGA (reset model: reprogram): registers |
| 12 | auto | clarify | approved (review off) |  |
| 13 | agent | board-and-device-planning | stage 1 work, visit 1 | 9 files in the design |
| 14 | agent | board-and-device-planning | stage 1 work, visit 2 | 10 files in the design |
| 15 | auto | board-and-device-planning | approved (review off) |  |
| 16 | auto | board-and-device-planning | architecture approved | source: agent |
| 17 | agent | rtl-design-creation | stage 2 work, visit 1 | 21 files in the design |
| 18 | agent | rtl-design-creation | stage 2 work, visit 2 | 22 files in the design |
| 19 | agent | rtl-design-creation | stage 2 work, visit 3 | 24 files in the design |
| 20 | auto | rtl-design-creation | approved (review off) |  |
| 21 | agent | constraints | stage 3 work, visit 1 | 24 files in the design |
| 22 | auto | constraints | approved (review off) |  |
| 23 | agent | synthesis | stage 4 work, visit 1 | 24 files in the design |
| 24 | auto | synthesis | approved (review off) |  |
| 25 | agent | implementation | stage 5 work, visit 1 | 24 files in the design |
| 26 | auto | implementation | approved (review off) |  |
| 27 | agent | timing-closure | stage 6 work, visit 1 | 24 files in the design |
| 28 | auto | timing-closure | approved (review off) |  |
| 29 | agent | power-closure | stage 7 work, visit 1 | 24 files in the design |
| 30 | auto | power-closure | approved (review off) |  |
| 31 | agent | drc-closure | stage 8 work, visit 1 | 24 files in the design |
| 32 | auto | drc-closure | approved (review off) |  |
| 33 | agent | configuration-and-debug | stage 9 work, visit 1 | 28 files in the design |

owner: 1, agent: 14, auto: 18
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

approved (auto); written by the agent; sha256 862176c87507

## review 02 rtl-design-creation

approve by auto (gates fail)

## review 02 rtl-design-creation

approve by auto (gates fail)

## review 02 rtl-design-creation

approve by auto (gates pass)

## review 03 constraints

approve by auto (gates pass)

## review 04 synthesis

approve by auto (gates pass)

## review 05 implementation

approve by auto (gates pass)

## review 06 timing-closure

approve by auto (gates pass)

## review 07 power-closure

approve by auto (gates pass)

## review 08 drc-closure

approve by auto (gates pass)
