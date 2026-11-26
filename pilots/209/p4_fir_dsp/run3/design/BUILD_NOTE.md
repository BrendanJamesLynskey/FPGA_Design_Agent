
## models by role (profile single)

clarify: deepagents claude-sonnet-5-5 (medium); model: deepagents claude-sonnet-5-5 (medium); tests: deepagents claude-sonnet-5-5 (medium); rtl: deepagents claude-sonnet-5-5 (medium). Interview oracle: claude-sonnet-5-5 (the oracle purpose). The stage machine is plain code.

<!-- who-did-what:start -->
## Who did what

| # | who | stage | what | detail |
|---|---|---|---|---|
| 1 | agent | clarify | stage 0 work, visit 1 | 8 files in the design |
| 2 | agent | clarify | stage 0 work, visit 2 | 8 files in the design |
| 3 | auto | clarify | interview | defaulted: What is the register map (offset, width, reset value and access of every register)? -> The map in spec.md (0x000 ID, 0x004 BUILD, 0x008 SCRATCH, 0x010 CTRL, 0x014 IN_P |
| 4 | auto | clarify | interview | defaulted: What happens to samples pushed while BUSY? -> Pushes during a run are accepted but not processed until the next RUN |
| 5 | auto | clarify | interview | defaulted: What happens to a RUN written while BUSY, or with an empty input FIFO? -> Ignored while BUSY; with an empty FIFO it completes at once with no output |
| 6 | auto | clarify | interview | defaulted: What if the output FIFO would overflow (input plus output count above 1024)? -> RUN processes only as many samples as fit in the output FIFO free space |
| 7 | auto | clarify | interview | defaulted: What if CLEAR and RUN are written together, or CLEAR while BUSY? -> CLEAR wins and aborts any run; RUN in the same write is ignored |
| 8 | auto | clarify | interview | defaulted: What do the LEDs show? -> led[0] = BUSY, led[1] = MMCM locked |
| 9 | auto | clarify | interview | defaulted: Do SAT_COUNT and SAMPLES_DONE wrap at 32 bits? -> Yes, they wrap |
| 10 | auto | clarify | interview | defaulted: Does the bit-exact result need OUT_POP sign extension? -> No, bits 30:16 are 0, host takes bits 15:0 |
| 11 | auto | clarify | approved (review off) |  |
| 12 | agent | board-and-device-planning | stage 1 work, visit 1 | 10 files in the design |
| 13 | agent | board-and-device-planning | stage 1 work, visit 2 | 11 files in the design |
| 14 | auto | board-and-device-planning | approved (review off) |  |
| 15 | auto | board-and-device-planning | architecture approved | source: agent |
| 16 | agent | rtl-design-creation | stage 2 work, visit 1 | 15 files in the design |
| 17 | agent | rtl-design-creation | stage 2 work, visit 2 | 15 files in the design |
| 18 | agent | rtl-design-creation | stage 2 work, visit 3 | 15 files in the design |
| 19 | agent | rtl-design-creation | stage 2 work, visit 4 | 15 files in the design |
| 20 | agent | rtl-design-creation | stage 2 work, visit 5 | 15 files in the design |
| 21 | agent | rtl-design-creation | stage 2 work, visit 6 | 15 files in the design |

owner: 0, agent: 10, auto: 11
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

approved (auto); written by the agent; sha256 65f4da04a7ee

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
