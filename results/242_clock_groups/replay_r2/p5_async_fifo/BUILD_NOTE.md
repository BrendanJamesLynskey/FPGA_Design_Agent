
## models by role (profile single)

clarify: claude_code claude-sonnet-5-5 (medium); model: claude_code claude-sonnet-5-5 (medium); tests: claude_code claude-sonnet-5-5 (medium); rtl: claude_code claude-sonnet-5-5 (medium). Interview oracle: openai/gpt-6-luna (the oracle purpose). The stage machine is plain code.

<!-- who-did-what:start -->
## Who did what

| # | who | stage | what | detail |
|---|---|---|---|---|
| 1 | owner | start | verification profile | standard with overrides {'verif_level': 'V2'} |
| 2 | agent | clarify | stage 0 work, visit 1 | 7 files in the design |
| 3 | agent | clarify | stage 0 work, visit 2 | 7 files in the design |
| 4 | agent | clarify | stage 0 work, visit 3 | 7 files in the design |
| 5 | auto | clarify | interview | defaulted: Which clock should the JTAG register bus and register file run on? -> clk_c3 (25 MHz) |
| 6 | auto | clarify | interview | defaulted: Where is OCC_MAX measured, and is a conservative value acceptable? -> Write side, from the synchronised read pointer (never below true fill). |
| 7 | auto | clarify | interview | defaulted: What does INJECT flip, and does it flip a word already in the FIFO or the next one received? -> Bit 0 of the next word the reader receives after the INJECT request arrives. |
| 8 | auto | clarify | interview | defaulted: What do the two LEDs show? -> led[0] = RUN, led[1] = DATA_ERRS non-zero. |
| 9 | auto | clarify | interview | defaulted: Should RUN falling to 0 let the reader drain the FIFO, and can WORDS_R then catch up with WORDS_W? -> Yes, the reader drains until empty. |
| 10 | auto | clarify | interview | defaulted: Is the register map exactly as given in the request (offsets 0x000 to 0x030, 32-bit, 4-byte steps)? Please confirm offse -> As in spec.md, with reserved CTRL bits reading 0 and reset value 0 for all count |
| 11 | auto | clarify | interview | defaulted: This design has no reset input. Is every reset a reconfiguration of the FPGA (the device is reprogrammed, so every regis -> Every reset is a reconfiguration of the FPGA (reset model: reprogram): registers |
| 12 | auto | clarify | interview | defaulted: How do the clocks of this design relate to each other: clk_c3, gt_refclk? For each pair say asynchronous (no common sour -> Every pair is asynchronous unless both clocks come from one MMCM or PLL (then re |
| 13 | auto | clarify | approved (review off) |  |
| 14 | agent | board-and-device-planning | stage 1 work, visit 1 | 9 files in the design |
| 15 | agent | board-and-device-planning | stage 1 work, visit 2 | 10 files in the design |
| 16 | auto | board-and-device-planning | approved (review off) |  |
| 17 | auto | board-and-device-planning | architecture approved | source: agent |
| 18 | agent | rtl-design-creation | stage 2 work, visit 1 | 23 files in the design |
| 19 | agent | rtl-design-creation | stage 2 work, visit 2 | 24 files in the design |
| 20 | agent | rtl-design-creation | stage 2 work, visit 3 | 24 files in the design |
| 21 | auto | rtl-design-creation | approved (review off) |  |
| 22 | agent | constraints | stage 3 work, visit 1 | 24 files in the design |
| 23 | agent | constraints | stage 3 work, visit 2 | 24 files in the design |
| 24 | agent | constraints | stage 3 work, visit 3 | 24 files in the design |

owner: 1, agent: 11, auto: 12
<!-- who-did-what:end -->

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

approved (auto); written by the agent; sha256 86621c6bbbb2

## review 02 rtl-design-creation

approve by auto (gates fail)

## review 02 rtl-design-creation

approve by auto (gates fail)

## review 02 rtl-design-creation

approve by auto (gates pass)

## review 03 constraints

approve by auto (gates fail)

## review 03 constraints

approve by auto (gates fail)

## review 03 constraints

approve by auto (gates fail)
