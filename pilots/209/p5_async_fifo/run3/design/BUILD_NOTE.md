
## models by role (profile single)

clarify: deepagents claude-sonnet-5-5 (medium); model: deepagents claude-sonnet-5-5 (medium); tests: deepagents claude-sonnet-5-5 (medium); rtl: deepagents claude-sonnet-5-5 (medium). Interview oracle: claude-sonnet-5-5 (the oracle purpose). The stage machine is plain code.

<!-- who-did-what:start -->
## Who did what

| # | who | stage | what | detail |
|---|---|---|---|---|
| 1 | agent | clarify | stage 0 work, visit 1 | 7 files in the design |
| 2 | agent | clarify | stage 0 work, visit 2 | 7 files in the design |
| 3 | auto | clarify | interview | defaulted: What is the register map (offset, width, reset value and access of every register)? -> The map in spec.md as written in registers.map, all 32 bits on 4-byte steps, wit |
| 4 | auto | clarify | interview | defaulted: Which clock drives the register port (clk of jtag_bus)? -> clk25 |
| 5 | auto | clarify | interview | defaulted: How is the snapshot of reader-domain counters made coherent with writer-domain counters? -> On SNAPSHOT write a request toggle goes to the gt_refclk domain which freezes it |
| 6 | auto | clarify | interview | defaulted: What do snapshot registers return before any SNAPSHOT write? -> 0, shadow registers reset to 0 |
| 7 | auto | clarify | interview | defaulted: Which bit does INJECT flip and in which word? -> Bit 0 of the next word received after INJECT is set. INJECT is ignored while RUN |
| 8 | auto | clarify | interview | defaulted: Does CLEAR also clear the pending INJECT, SLOW_READ and the FIFO contents? -> CLEAR empties the FIFO, clears counters and the pending INJECT. SLOW_READ is unc |
| 9 | auto | clarify | interview | defaulted: What happens to words still in the FIFO when RUN goes from 1 to 0? -> The writer stops at once and the reader keeps draining and checking until empty, |
| 10 | auto | clarify | interview | defaulted: Is OCC_MAX measured in the writer domain and can it reach 512? -> Writer-domain fill estimate from the synchronised read pointer, so it may read s |
| 11 | auto | clarify | interview | defaulted: What do the LEDs show? -> led[0] = RUN, led[1] = sticky error flag (any of DATA_ERRS, OVERFLOWS, UNDERFLOW |
| 12 | auto | clarify | interview | defaulted: What tolerance counts as the word counts moving at the clock rate? -> WORDS_W delta per 10 s equals 250 Mwords within 0.1 percent when STALL_W delta i |
| 13 | auto | clarify | interview | defaulted: Is the reset internal? -> Yes, a power-on counter of 16 clk25 cycles |
| 14 | auto | clarify | approved (review off) |  |
| 15 | agent | board-and-device-planning | stage 1 work, visit 1 | 9 files in the design |
| 16 | agent | board-and-device-planning | stage 1 work, visit 2 | 10 files in the design |
| 17 | auto | board-and-device-planning | approved (review off) |  |
| 18 | auto | board-and-device-planning | architecture approved | source: agent |
| 19 | agent | rtl-design-creation | stage 2 work, visit 1 | 14 files in the design |
| 20 | agent | rtl-design-creation | stage 2 work, visit 2 | 14 files in the design |
| 21 | agent | rtl-design-creation | stage 2 work, visit 3 | 14 files in the design |
| 22 | agent | rtl-design-creation | stage 2 work, visit 4 | 14 files in the design |
| 23 | agent | rtl-design-creation | stage 2 work, visit 5 | 14 files in the design |
| 24 | agent | rtl-design-creation | stage 2 work, visit 6 | 14 files in the design |

owner: 0, agent: 10, auto: 14
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

approved (auto); written by the agent; sha256 9f6c75d6cb62

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
