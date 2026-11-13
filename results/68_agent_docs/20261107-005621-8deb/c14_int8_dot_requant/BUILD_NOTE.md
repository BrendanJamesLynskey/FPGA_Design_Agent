
## models by role (profile single)

clarify: claude_code claude-sonnet-5-5 (medium); model: claude_code claude-sonnet-5-5 (medium); tests: claude_code claude-sonnet-5-5 (medium); rtl: claude_code claude-sonnet-5-5 (medium). Interview oracle: openai/gpt-6-luna (fixed). The stage machine is plain code.

<!-- who-did-what:start -->
## Who did what

| # | who | stage | what | detail |
|---|---|---|---|---|
| 1 | agent | clarify | stage 0 work, visit 1 | 5 files in the design |
| 2 | agent | clarify | stage 0 work, visit 2 | 5 files in the design |
| 3 | auto | clarify | interview | answered: What is the register map (offset, width, reset value and access of every register) of the shell-facing block? -> A_LO: offset 0x00, RW, reset 0: [31:0] activations 0..3, a_i in bits [8i+7:8i] A |
| 4 | auto | clarify | interview | answered: Is acc allowed to overflow 32 bits when bias is near its limit? -> The specification does not allow overflow: it says the sum never overflows for t |
| 5 | auto | clarify | interview | answered: Is ready cleared when a new go is accepted, and are results held until then? -> Yes. A write to GO clears READY and presents the operands for one clock; READY b |
| 6 | auto | clarify | interview | defaulted: What are the TIMEOUT_CYCLES default and BUILD_STAMP default values? -> TIMEOUT_CYCLES = 100000000 (1 s at 100 MHz), BUILD_STAMP = 0 overridden by the f |
| 7 | auto | clarify | interview | defaulted: How is the DOTQ design ID presented by the shell? -> Four ASCII bytes D,O,T,Q read as 0x444F5451 at ID register offset 0x00, if the s |
| 8 | auto | clarify | interview | defaulted: Does a 'go' with the ready flag already set restart the computation using the currently loaded operands? -> Yes, always accepted. |
| 9 | auto | clarify | approved (review off) |  |
| 10 | agent | board-and-device-planning | stage 1 work, visit 1 | 7 files in the design |
| 11 | agent | board-and-device-planning | stage 1 work, visit 2 | 8 files in the design |
| 12 | auto | board-and-device-planning | approved (review off) |  |
| 13 | auto | board-and-device-planning | architecture approved | source: agent |
| 14 | agent | rtl-design-creation | stage 2 work, visit 1 | 18 files in the design |
| 15 | agent | rtl-design-creation | stage 2 work, visit 2 | 18 files in the design |
| 16 | agent | rtl-design-creation | stage 2 work, visit 3 | 18 files in the design |
| 17 | agent | rtl-design-creation | stage 2 work, visit 4 | 18 files in the design |

owner: 0, agent: 8, auto: 9
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

approved (auto); written by the agent; sha256 f7e23d106c57

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
