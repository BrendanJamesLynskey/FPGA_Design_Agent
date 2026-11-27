
## models by role (profile single)

clarify: claude_code claude-sonnet-5-5 (medium); model: claude_code claude-sonnet-5-5 (medium); tests: claude_code claude-sonnet-5-5 (medium); rtl: claude_code claude-sonnet-5-5 (medium). Interview oracle: openai/gpt-6-luna (the oracle purpose). The stage machine is plain code.

<!-- who-did-what:start -->
## Who did what

| # | who | stage | what | detail |
|---|---|---|---|---|
| 1 | owner | start | verification profile | standard with overrides {'verif_level': 'V2'} |
| 2 | agent | clarify | stage 0 work, visit 1 | 7 files in the design |
| 3 | agent | clarify | stage 0 work, visit 2 | 7 files in the design |
| 4 | auto | clarify | interview | defaulted: Which clock does the jtag_bus register port run on? -> The 25 MHz C3 clock (writer domain), with reader-domain counters transferred by  |
| 5 | auto | clarify | interview | defaulted: Please give the register map (offset, width, reset value and access of every register); is the map in the request comple -> As in the request table: ID 0x000, BUILD 0x004, SCRATCH 0x008, CTRL 0x010, WORDS |
| 6 | auto | clarify | interview | defaulted: What do the LEDs show? -> led[0] = RUN, led[1] = sticky error (data, overflow or underflow, cleared by CLE |
| 7 | auto | clarify | interview | defaulted: What do the counters do while RUN is 0 and what is the FIFO state when RUN stops? -> Counters hold; the writer stops, the reader drains the FIFO and keeps checking u |
| 8 | auto | clarify | interview | defaulted: Is OCC_MAX measured on the writer side or the reader side, and what is the maximum value? -> Writer-side fill count, maximum 512. |
| 9 | auto | clarify | interview | defaulted: Which bit of the injected word is flipped? -> Bit 0. |
| 10 | auto | clarify | interview | defaulted: What if INJECT is written while RUN is 0? -> It stays armed until the next word is checked after RUN starts. |
| 11 | auto | clarify | interview | defaulted: This design has no reset input. Is every reset a reconfiguration of the FPGA (the device is reprogrammed, so every regis -> Every reset is a reconfiguration of the FPGA (reset model: reprogram): registers |
| 12 | auto | clarify | interview | defaulted: How do the clocks of this design relate to each other: clk_wr, clk_rd, tck? For each pair say asynchronous (no common so -> Every pair is asynchronous unless both clocks come from one MMCM or PLL (then re |
| 13 | auto | clarify | approved (review off) |  |
| 14 | agent | board-and-device-planning | stage 1 work, visit 1 | 9 files in the design |
| 15 | agent | board-and-device-planning | stage 1 work, visit 2 | 10 files in the design |
| 16 | auto | board-and-device-planning | approved (review off) |  |
| 17 | auto | board-and-device-planning | architecture approved | source: agent |
| 18 | agent | rtl-design-creation | stage 2 work, visit 1 | 23 files in the design |
| 19 | auto | rtl-design-creation | approved (review off) |  |
| 20 | agent | constraints | stage 3 work, visit 1 | 24 files in the design |
| 21 | agent | constraints | stage 3 work, visit 2 | 24 files in the design |
| 22 | agent | constraints | stage 3 work, visit 3 | 24 files in the design |
| 23 | agent | constraints | stage 3 work, visit 4 | 24 files in the design |

owner: 1, agent: 9, auto: 13
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

approved (auto); written by the agent; sha256 22c1138f7b30

## review 02 rtl-design-creation

approve by auto (gates pass)

## review 03 constraints

approve by auto (gates fail)

## review 03 constraints

approve by auto (gates fail)

## review 03 constraints

approve by auto (gates fail)

## review 03 constraints

approve by auto (gates fail)

## review 03 constraints

approve by auto (gates fail)
