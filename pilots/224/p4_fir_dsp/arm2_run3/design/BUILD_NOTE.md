
## models by role (profile single)

clarify: deepagents claude-sonnet-5-5 (medium); model: deepagents claude-sonnet-5-5 (medium); tests: deepagents claude-sonnet-5-5 (medium); rtl: deepagents claude-sonnet-5-5 (medium). Interview oracle: claude-sonnet-5-5 (the oracle purpose). The stage machine is plain code.

<!-- who-did-what:start -->
## Who did what

| # | who | stage | what | detail |
|---|---|---|---|---|
| 1 | owner | start | verification profile | standard with overrides {'verif_level': 'V2'} |
| 2 | agent | clarify | stage 0 work, visit 1 | 8 files in the design |
| 3 | agent | clarify | stage 0 work, visit 2 | 8 files in the design |
| 4 | auto | clarify | interview | defaulted: What happens to a RUN written while BUSY, and to IN_PUSH while BUSY? -> RUN while BUSY is ignored; IN_PUSH while BUSY is accepted if not full and proces |
| 5 | auto | clarify | interview | defaulted: Is CLEAR during BUSY allowed? -> CLEAR aborts the run and empties everything. |
| 6 | auto | clarify | interview | defaulted: If the output FIFO lacks space for the whole input (more than 1024 total outputs)? -> The user must drain; a result arriving at a full output FIFO is dropped. SAMPLES |
| 7 | auto | clarify | interview | defaulted: Which clock frequency for the datapath? -> 250 MHz from MMCM (VCO 1000 MHz). |
| 8 | auto | clarify | interview | defaulted: What do the LEDs show? -> led[0]=BUSY, led[1]=heartbeat. |
| 9 | auto | clarify | interview | defaulted: Do STATUS counts and SAT_COUNT/SAMPLES_DONE need to be consistent snapshots? -> Each read is a single-register snapshot; no cross-register atomicity. |
| 10 | auto | clarify | interview | defaulted: BUILD value in simulation? -> Behavioural model returns 0 or a testbench-set word. |
| 11 | auto | clarify | approved (review off) |  |
| 12 | agent | board-and-device-planning | stage 1 work, visit 1 | 10 files in the design |
| 13 | agent | board-and-device-planning | stage 1 work, visit 2 | 11 files in the design |
| 14 | auto | board-and-device-planning | approved (review off) |  |
| 15 | auto | board-and-device-planning | architecture approved | source: agent |

owner: 1, agent: 4, auto: 10
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

approved (auto); written by the agent; sha256 dbd7f90a772a

## review 02 rtl-design-creation

approve by auto (gates fail)
