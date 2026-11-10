# Brief 27B P1: phase 0 on two specs (development subjects only)

Written by `results/27b_p1/summarise.py` from the runs' own files. Drafter and oracle: `openai/gpt-6-luna`
(the agent's default), OpenRouter, `data_collection: deny`. Cost is the provider-reported figure per call.
Runs in the order made. The harness was changed twice after reading a run (never during one):
- after `pilot1_run1`: a stream latency or throughput the drafter left out is asked too; a contract for a
  module not in the design is a repair note;
- after `pilot1_run2` and `c12_pwm_audio_run1`: a field the apply step changes without an answer naming it is
  sent back as a repair note (it was only logged); a quote of fewer than three words no longer states a field.
- after `pilot1_run3` (it stopped: the unasked-change notes used up the apply step's repairs and a checker
  error remained): the last repair is kept for checker errors, and an apply step that never passes keeps the
  valid draft and writes every answer it could not apply as an open assumption carrying the answer.
- after `pilot1_run4` (planner review of PR #104; the median latency was asked but fell past the single
  40-question budget): pass 2 asks interface fields first, each module within its own share (12), then the
  design's own fields (12), then data formats and board pins (12 together); the checker now rejects a
  multi-module graph with no connections or with a module that reaches neither a board pin nor the shell,
  and a board pin whose direction disagrees with the board (master XDC sections, inventory `dir`).
- after `pilot1_run5` (the median latency, 1651, was "stated" by a quote with no number in it, so never
  asked): a quote states a field only if it holds every number of the field's value.
`pilot1` (run 6) ran with the final harness. `c12_pwm_audio` (run 2) ran before the last three changes. The last column re-checks every run's files with today's checker. Each row is a single run.

**Owner choice 2 in run 6.** The median latency was asked (question order and shares fixed it) and the oracle
answered "1 clock cycle", quoting the `c9_median3x3` task ("exactly 1 clock: the result of a window
presented in clock n is seen in clock n + 1"): that task filters a presented window, the pilot's median a
raster with line buffers. The oracle's hidden file holds both that line and the owner's "Median latency
H_TOTAL + 2." and nothing says which wins, so the choice is lost in the oracle, not in the harness.

| Spec | Modules | Pass 1 asked / answered / assumptions | Contract and design fields | Stated by a spec quote | Pass 2 asked / answered / assumptions | Assumptions written | Files valid | Calls | Tokens (in / out) | USD | Today's checker |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pilot1_run1 | video_timing, median_filter, vga_output | 6 / 2 / 4 | 60 | 16 | 44 / 15 / 29 | 33 | yes | 51 | 222714 / 54522 | 0.0339 | 2 errors |
| pilot1_run2 | video_timing, color_bars, median_filter, frame_counter, video_cdc, video_output, video_control | 6 / 2 / 4 | 82 | 15 | 67 / 4 / 63 | 67 | yes | 50 | 194446 / 37839 | 0.0243 | 6 errors |
| c12_pwm_audio_run1 | c12_nexys_pwm_audio_top, audio_state, pwm_stage | 3 / 1 / 2 | 34 | 22 | 12 / 4 / 8 | 10 | yes | 19 | 72390 / 30099 | 0.0187 | 2 errors |
| c12_pwm_audio | audio_gain, pwm_audio | 4 / 3 / 1 | 23 | 12 | 11 / 5 / 6 | 7 | yes | 16 | 50430 / 26603 | 0.0160 | 1 errors |
| pilot1_run4 | pixel_clock, timing_gen, pattern_gen, median_filter, vga_output | 7 / 2 / 5 | 86 | 22 | 64 / 9 / 55 | 60 | yes | 53 | 309079 / 66135 | 0.0427 | 1 errors |
| pilot1_run5 | video_source, median_filter, vga_output | 5 / 1 / 4 | 64 | 27 | 37 / 10 / 27 | 31 | yes | 46 | 299641 / 72051 | 0.0451 | valid |
| pilot1 | pattern_timing, median_filter, vga_output | 6 / 1 / 5 | 66 | 8 | 58 / 14 / 44 | 49 | yes | 64 | 351751 / 74278 | 0.0470 | valid |

## pilot1_run1

Drafter repairs: pass 1 0, pass 2 {'draft': 1, 'apply': 1}. Quotes that were not in the spec (so the field was asked): 8. Questions over the pass 2 budget: 4. Fields the drafter changed without being asked: 0. Calls by role: {'drafter': 5, 'oracle': 46}.

Today's checker on these files:

- board port UART_RXD_OUT: dir in, but the board pin is an output of the FPGA (boards/nexys_a7_100t/inventory.yaml)
- board port UART_TXD_IN: dir out, but the board pin is an input of the FPGA (boards/nexys_a7_100t/inventory.yaml)

Checks against facts fixed before the run:

| Fact | Holds | Found |
|---|---|---|
| owner choice 1: a full-raster video stream with no back-pressure (every stream link: no back-pressure, no gaps) | no | [{'link': 'video_timing.out -> median_filter.in', 'protocol': 'axi4-stream', 'backpressure': [False, False]... |
| owner choice 2: median latency H_TOTAL + 2 | no | [] |
| owner choice 3: shell registers at window base 0x00 | yes | {'video_timing': 0} |

Pass 1 questions:

| Question | Result | Settles |
|---|---|---|
| What board clock source and condition should define pixel-clock stability? | answered | S-1, S-5, S-6 |
| What RGB channel width and numeric levels should the VGA output use? | answered | S-2, S-3, S-5 |
| How should the 3 x 3 filter handle neighbourhoods at the active-picture edges? | defaulted | S-3 |
| Which patterns should be selectable, and when should a pattern change take effect? | defaulted | S-2, S-7 |
| What UART framing, command syntax, and response format should the test shell use, including how the host ob... | defaulted | S-7 |
| What should the frame counter count, and what are its width, wrap, and reset behavior? | defaulted | S-7 |

Pass 2 questions (one per field the spec does not state; the fields each one settles):

| Fields | Result | Draft value | Final value |
|---|---|---|---|
| video_timing.contract.resets.rst | assumption (oracle) | {polarity: active_low, style: async} | {polarity: active_low, style: async} |
| video_timing.contract.data_formats.channel | assumption (oracle) | {format: u4, packing: One unsigned 4-bit RGB ch... | {format: u4, packing: One unsigned 4-bit RGB ch... |
| video_timing.contract.data_formats.frame_counter | assumption (oracle) | {format: u32, packing: Unsigned completed-frame... | {format: u32, packing: Unsigned completed-frame... |
| video_timing.contract.interfaces.out.tlast<br>median_filter.contract.interfaces.in.tlast | assumption (oracle) | Assert on the final pixel clock of each 1650-cl... | Assert on the final pixel clock of each 1650-cl... |
| video_timing.contract.interfaces.out.packet_beats<br>median_filter.contract.interfaces.in.packet_beats | assumption (oracle) | 1650 | 1650 |
| video_timing.contract.interfaces.out.backpressure<br>median_filter.contract.interfaces.in.backpressure | answered | true | false |
| video_timing.contract.interfaces.out.source_gaps<br>median_filter.contract.interfaces.in.source_gaps | assumption (oracle) | false | false |
| video_timing.contract.registers | assumption (oracle) | [{name: PATTERN, offset: 0, access: RW, reset: ... | [{name: PATTERN, offset: 0, access: RW, reset: ... |
| video_timing.contract.throughput.out | assumption (oracle) | {beats_per_cycle: 1} | {beats_per_cycle: 1} |
| median_filter.contract.resets.rst | answered | {polarity: active_low, style: async} | {polarity: active_low, style: async} |
| median_filter.contract.data_formats.channel | assumption (oracle) | {format: u4, packing: One unsigned 4-bit RGB ch... | {format: u4, packing: One unsigned 4-bit RGB ch... |
| median_filter.contract.interfaces.out.tlast<br>vga_output.contract.interfaces.in.tlast | assumption (oracle) | Assert on the final pixel clock of each 1650-cl... | Assert on the final pixel clock of each 1650-cl... |
| median_filter.contract.interfaces.out.packet_beats<br>vga_output.contract.interfaces.in.packet_beats | assumption (oracle) | 1650 | 1650 |
| median_filter.contract.interfaces.out.backpressure<br>vga_output.contract.interfaces.in.backpressure | assumption (oracle) | true | true |
| median_filter.contract.interfaces.out.source_gaps<br>vga_output.contract.interfaces.in.source_gaps | answered | true | true |
| median_filter.contract.throughput.out | answered | {beats_per_cycle: 1} | {beats_per_cycle: 1, from: in, out_per_in: 1} |
| vga_output.contract.resets.rst | assumption (oracle) | {polarity: active_low, style: async} | {polarity: active_low, style: async} |
| vga_output.contract.ports.pixel_clock_stable | assumption (oracle) | {dir: in, width: 1} | {dir: in, width: 1} |
| vga_output.contract.ports.hsync | assumption (oracle) | {dir: out, width: 1, reset_value: 0} | {dir: out, width: 1, reset_value: 0} |
| vga_output.contract.ports.vsync | answered | {dir: out, width: 1, reset_value: 0} | {dir: out, width: 1} |
| vga_output.contract.ports.vga_r | assumption (oracle) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| vga_output.contract.ports.vga_g | assumption (oracle) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| vga_output.contract.ports.vga_b | assumption (oracle) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| vga_output.contract.data_formats.channel | assumption (oracle) | {format: u4, packing: One unsigned 4-bit RGB ch... | {format: u4, packing: One unsigned 4-bit RGB ch... |
| vga_output.contract.interfaces.in.protocol | assumption (oracle) | {protocol: axi4-stream, role: slave} | {protocol: axi4-stream, role: slave} |
| vga_output.contract.throughput.in | answered | {beats_per_cycle: 1} | {beats_per_cycle: 1, from: in, out_per_in: 1} |
| fpga_shell.contract.clocks.clk.max_mhz | answered | 100 | 100 |
| fpga_shell.contract.resets.rst | assumption (oracle) | {polarity: active_low, style: async} | {polarity: active_low, style: async} |
| design.clocks.clk_sys | answered | {source: board, mhz: 100, port: CLK100MHZ} | {source: board, mhz: 100, port: CLK100MHZ} |
| design.clocks.clk_pix | answered | {source: mmcm, mhz: 74.25, from: clk_sys} | {source: mmcm, mhz: 74.25, from: clk_sys} |
| design.resets.rst_sys | answered | {from: CPU_RESETN, polarity: active_low, style:... | {from: CPU_RESETN, polarity: active_low, style:... |
| design.resets.rst_pix | answered | {from: rst_sys, polarity: active_low, style: as... | {from: rst_sys, polarity: active_low, style: as... |
| design.modules.video_timing.window_base | answered | 0 | 0 |
| design.board_ports.CLK100MHZ | assumption (oracle) | {dir: in, drive: input, to: clk_sys} | {dir: in, drive: input, to: clk_sys} |
| design.board_ports.CPU_RESETN | assumption (oracle) | {dir: in, drive: input, to: rst_sys} | {dir: in, drive: input, to: rst_sys} |
| design.board_ports.BTNC | answered | {dir: in, drive: input, to: vga_output.btnc} | {dir: in, drive: input, to: vga_output.btnc} |
| design.board_ports.UART_RXD_OUT | assumption (oracle) | {dir: in, drive: input, to: shell.uart_rx} | {dir: in, drive: input, to: shell.uart_rx} |
| design.board_ports.UART_TXD_IN | answered | {dir: out, drive: push-pull, from: shell.uart_tx} | {dir: out, drive: push-pull, from: shell.uart_tx} |
| design.board_ports.VGA_HS | assumption (oracle) | {dir: out, drive: push-pull, from: vga_output.h... | {dir: out, drive: push-pull, from: vga_output.h... |
| design.board_ports.VGA_VS | answered | {dir: out, drive: push-pull, from: vga_output.v... | {dir: out, drive: push-pull, from: vga_output.v... |
| design.board_ports.VGA_R[3:0] | assumption (limit) | {dir: out, drive: push-pull, from: vga_output.v... | {dir: out, drive: push-pull, from: vga_output.v... |
| design.board_ports.VGA_G[3:0] | assumption (limit) | {dir: out, drive: push-pull, from: vga_output.v... | {dir: out, drive: push-pull, from: vga_output.v... |
| design.board_ports.VGA_B[3:0] | assumption (limit) | {dir: out, drive: push-pull, from: vga_output.v... | {dir: out, drive: push-pull, from: vga_output.v... |
| design.board_ports.LED[0] | assumption (limit) | {dir: out, drive: push-pull, from: clk_pix.locked} | {dir: out, drive: push-pull, from: clk_pix.locked} |

## pilot1_run2

Drafter repairs: pass 1 0, pass 2 {'draft': 1, 'apply': 0}. Quotes that were not in the spec (so the field was asked): 26. Questions over the pass 2 budget: 27. Fields the drafter changed without being asked: 8. Calls by role: {'drafter': 4, 'oracle': 46}.

Today's checker on these files:

- connections: the design has 7 modules and no connection between them; connect each module's interfaces (point to point), or merge the modules
- module video_timing: not reachable from the board ports or the shell (no board port, no registers in the shell window, and no connection to a module that has one)
- module color_bars: not reachable from the board ports or the shell (no board port, no registers in the shell window, and no connection to a module that has one)
- module median_filter: not reachable from the board ports or the shell (no board port, no registers in the shell window, and no connection to a module that has one)
- module frame_counter: not reachable from the board ports or the shell (no board port, no registers in the shell window, and no connection to a module that has one)
- module video_cdc: not reachable from the board ports or the shell (no board port, no registers in the shell window, and no connection to a module that has one)

Checks against facts fixed before the run:

| Fact | Holds | Found |
|---|---|---|
| owner choice 1: a full-raster video stream with no back-pressure (every stream link: no back-pressure, no gaps) | no | [] |
| owner choice 2: median latency H_TOTAL + 2 | no | [] |
| owner choice 3: shell registers at window base 0x00 | yes | {'video_control': 0} |

Pass 1 questions:

| Question | Result | Settles |
|---|---|---|
| Which clock input should be used to generate the 74.25 MHz pixel clock, and what should count as stable? | defaulted | S-1, S-5, S-6 |
| What should the median filter use for neighbourhood samples beyond the active picture boundaries? | defaulted | S-3, S-4, S-5 |
| What set of patterns should be selectable through the test shell? | answered | S-2, S-7 |
| What UART command and response format should the host use? | defaulted | S-7 |
| How wide should the frame counter be, and when should it increment? | defaulted | S-7 |
| What colour-channel width should be used for the VGA output? | answered | S-2, S-3, S-5 |

Pass 2 questions (one per field the spec does not state; the fields each one settles):

| Fields | Result | Draft value | Final value |
|---|---|---|---|
| video_timing.contract.resets.rst | assumption (oracle) | {polarity: active_high, style: sync} | {polarity: active_low, style: async} |
| video_timing.contract.ports.x | assumption (oracle) | {dir: out, width: 11, reset_value: 0} | {dir: out, width: 11, reset_value: 0} |
| video_timing.contract.ports.y | assumption (oracle) | {dir: out, width: 10, reset_value: 0} | {dir: out, width: 10, reset_value: 0} |
| video_timing.contract.ports.active | assumption (oracle) | {dir: out, width: 1, reset_value: 0} | {dir: out, width: 1, reset_value: 0} |
| video_timing.contract.ports.hsync | assumption (oracle) | {dir: out, width: 1, reset_value: 0} | {dir: out, width: 1, reset_value: 0} |
| video_timing.contract.ports.vsync | assumption (oracle) | {dir: out, width: 1, reset_value: 0} | {dir: out, width: 1, reset_value: 0} |
| video_timing.contract.ports.frame_end | assumption (oracle) | {dir: out, width: 1, reset_value: 0} | {dir: out, width: 1, reset_value: 0} |
| color_bars.contract.resets.rst | answered | {polarity: active_high, style: sync} | {polarity: active_low, style: async} |
| color_bars.contract.ports.x | assumption (oracle) | {dir: in, width: 11} | {dir: in, width: 11} |
| color_bars.contract.ports.y | assumption (oracle) | {dir: in, width: 10} | {dir: in, width: 10} |
| color_bars.contract.ports.active | assumption (oracle) | {dir: in, width: 1} | {dir: in, width: 1} |
| color_bars.contract.ports.pattern | assumption (oracle) | {dir: in, width: 2} | {dir: in, width: 2} |
| color_bars.contract.ports.red | assumption (oracle) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| color_bars.contract.ports.green | assumption (oracle) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| color_bars.contract.ports.blue | assumption (oracle) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| median_filter.contract.resets.rst | answered | {polarity: active_high, style: sync} | {polarity: active_low, style: async} |
| median_filter.contract.ports.in_red | assumption (oracle) | {dir: in, width: 4} | {dir: in, width: 4} |
| median_filter.contract.ports.in_green | assumption (oracle) | {dir: in, width: 4} | {dir: in, width: 4} |
| median_filter.contract.ports.in_blue | assumption (oracle) | {dir: in, width: 4} | {dir: in, width: 4} |
| median_filter.contract.ports.in_active | assumption (oracle) | {dir: in, width: 1} | {dir: in, width: 1} |
| median_filter.contract.ports.in_hsync | assumption (oracle) | {dir: in, width: 1} | {dir: in, width: 1} |
| median_filter.contract.ports.in_vsync | assumption (oracle) | {dir: in, width: 1} | {dir: in, width: 1} |
| median_filter.contract.ports.out_red | assumption (oracle) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| median_filter.contract.ports.out_green | assumption (oracle) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| median_filter.contract.ports.out_blue | assumption (oracle) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| median_filter.contract.ports.out_active | assumption (oracle) | {dir: out, width: 1, reset_value: 0} | {dir: out, width: 1, reset_value: 0} |
| median_filter.contract.ports.out_hsync | assumption (oracle) | {dir: out, width: 1, reset_value: 0} | {dir: out, width: 1, reset_value: 0} |
| median_filter.contract.ports.out_vsync | assumption (oracle) | {dir: out, width: 1, reset_value: 0} | {dir: out, width: 1, reset_value: 0} |
| frame_counter.contract.resets.rst | assumption (oracle) | {polarity: active_high, style: sync} | {polarity: active_low, style: async} |
| frame_counter.contract.ports.frame_end | assumption (oracle) | {dir: in, width: 1} | {dir: in, width: 1} |
| video_cdc.contract.clocks.clk_sys.max_mhz | answered | 100 | 100 |
| video_cdc.contract.resets.rst_sys | assumption (oracle) | {polarity: active_high, style: sync} | {polarity: active_low, style: async} |
| video_cdc.contract.resets.rst_pix | assumption (oracle) | {polarity: active_high, style: sync} | {polarity: active_low, style: async} |
| video_cdc.contract.ports.pattern_sys | assumption (oracle) | {dir: in, width: 2} | {dir: in, width: 2} |
| video_cdc.contract.ports.frame_count_pix | assumption (oracle) | {dir: in, width: 32} | {dir: in, width: 32} |
| video_cdc.contract.ports.pattern_pix | assumption (oracle) | {dir: out, width: 2, reset_value: 0} | {dir: out, width: 2, reset_value: 0} |
| video_cdc.contract.ports.frame_count_sys | assumption (oracle) | {dir: out, width: 32, reset_value: 0} | {dir: out, width: 32, reset_value: 0} |
| video_control.contract.clocks.clk.max_mhz | answered | 100 | 74.25 |
| video_control.contract.resets.rst | assumption (oracle) | {polarity: active_high, style: sync} | {polarity: active_low, style: async} |
| video_control.contract.ports.pattern | assumption (oracle) | {dir: in, width: 2} | {dir: in, width: 2} |
| video_control.contract.ports.pattern_selected | assumption (limit) | {dir: out, width: 2, reset_value: 0} | {dir: out, width: 2, reset_value: 0} |
| video_control.contract.ports.frame_count_in | assumption (limit) | {dir: in, width: 32} | {dir: in, width: 32} |
| video_control.contract.ports.frame_count | assumption (limit) | {dir: out, width: 32, reset_value: 0} | {dir: out, width: 32, reset_value: 0} |
| video_control.contract.registers | assumption (limit) | [{name: PATTERN, offset: 0, access: RW, reset: ... | [{name: PATTERN, offset: 0, access: RW, reset: ... |
| video_output.contract.resets.rst | assumption (limit) | {polarity: active_high, style: sync} | {polarity: active_low, style: async} |
| video_output.contract.ports.locked | assumption (limit) | {dir: in, width: 1} | {dir: in, width: 1} |
| video_output.contract.ports.active | assumption (limit) | {dir: in, width: 1} | {dir: in, width: 1} |
| video_output.contract.ports.in_hsync | assumption (limit) | {dir: in, width: 1} | {dir: in, width: 1} |
| video_output.contract.ports.in_vsync | assumption (limit) | {dir: in, width: 1} | {dir: in, width: 1} |
| video_output.contract.ports.in_red | assumption (limit) | {dir: in, width: 4} | {dir: in, width: 4} |
| video_output.contract.ports.in_green | assumption (limit) | {dir: in, width: 4} | {dir: in, width: 4} |
| video_output.contract.ports.in_blue | assumption (limit) | {dir: in, width: 4} | {dir: in, width: 4} |
| video_output.contract.ports.hsync | assumption (limit) | {dir: out, width: 1, reset_value: 0} | {dir: out, width: 1, reset_value: 0} |
| video_output.contract.ports.vsync | assumption (limit) | {dir: out, width: 1, reset_value: 0} | {dir: out, width: 1, reset_value: 0} |
| video_output.contract.ports.red | assumption (limit) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| video_output.contract.ports.green | assumption (limit) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| video_output.contract.ports.blue | assumption (limit) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| design.clocks.clk_sys | assumption (limit) | {source: board, mhz: 100, port: CLK100MHZ} | {source: board, mhz: 100, port: CLK100MHZ} |
| design.resets.rst_sys | assumption (limit) | {from: CPU_RESETN, polarity: active_high, style... | {from: CPU_RESETN, polarity: active_low, style:... |
| design.modules.video_control.window_base | assumption (limit) | 0 | 0 |
| design.board_ports.CLK100MHZ | assumption (limit) | {dir: in, drive: input, to: clk_sys} | {dir: in, drive: input, to: clk_sys} |
| design.board_ports.CPU_RESETN | assumption (limit) | {dir: in, drive: input, to: rst_sys} | {dir: in, drive: input, to: rst_sys} |
| design.board_ports.VGA_HS | assumption (limit) | {dir: out, drive: push-pull, from: video_output... | {dir: out, drive: push-pull, from: video_output... |
| design.board_ports.VGA_VS | assumption (limit) | {dir: out, drive: push-pull, from: video_output... | {dir: out, drive: push-pull, from: video_output... |
| design.board_ports.VGA_R[3:0] | assumption (limit) | {dir: out, drive: push-pull, from: video_output... | {dir: out, drive: push-pull, from: video_output... |
| design.board_ports.VGA_G[3:0] | assumption (limit) | {dir: out, drive: push-pull, from: video_output... | {dir: out, drive: push-pull, from: video_output... |
| design.board_ports.VGA_B[3:0] | assumption (limit) | {dir: out, drive: push-pull, from: video_output... | {dir: out, drive: push-pull, from: video_output... |

Unasked changes:

- `design.resets.rst_pix`: {from: rst_sys, polarity: active_high, style: s... -> {from: rst_sys, polarity: active_low, style: as...
- `design.resets.rst_sys`: {from: CPU_RESETN, polarity: active_high, style... -> {from: CPU_RESETN, polarity: active_low, style:...
- `frame_counter.contract.resets.rst`: {polarity: active_high, style: sync} -> {polarity: active_low, style: async}
- `video_cdc.contract.resets.rst_pix`: {polarity: active_high, style: sync} -> {polarity: active_low, style: async}
- `video_cdc.contract.resets.rst_sys`: {polarity: active_high, style: sync} -> {polarity: active_low, style: async}
- `video_control.contract.resets.rst`: {polarity: active_high, style: sync} -> {polarity: active_low, style: async}
- `video_output.contract.resets.rst`: {polarity: active_high, style: sync} -> {polarity: active_low, style: async}
- `video_timing.contract.resets.rst`: {polarity: active_high, style: sync} -> {polarity: active_low, style: async}

## c12_pwm_audio_run1

Drafter repairs: pass 1 0, pass 2 {'draft': 2, 'apply': 0}. Quotes that were not in the spec (so the field was asked): 12. Questions over the pass 2 budget: 0. Fields the drafter changed without being asked: 1. Calls by role: {'drafter': 5, 'oracle': 14}.

Today's checker on these files:

- connections: the design has 3 modules and no connection between them; connect each module's interfaces (point to point), or merge the modules
- module pwm_stage: not reachable from the board ports or the shell (no board port, no registers in the shell window, and no connection to a module that has one)

Checks against facts fixed before the run:

| Fact | Holds | Found |
|---|---|---|
| recorded c12 failure: AUD_PWM is open-drain (pulled low or released, never driven high) | no | {'name': 'AUD_PWM', 'dir': 'out', 'drive': 'pulled-up', 'from': 'c12_nexys_pwm_audio_top.aud_pwm'} |
| recorded c12 failure: the top has the 16-bit LED output (left off) | yes | [{'name': 'LED[15:0]', 'dir': 'out', 'drive': 'push-pull', 'from': 'c12_nexys_pwm_audio_top.led'}] |
| register map = the hidden spec's map (offset, name, access) | yes | [(0, 'SAMPLE', 'RW'), (1, 'GAIN', 'WO'), (2, 'SOUT', 'RO')] |

Pass 1 questions:

| Question | Result | Settles |
|---|---|---|
| What shell command framing, command encodings, numeric formats, and response format should be used for samp... | defaulted | S-1, S-2, S-3, S-10 |
| When should a changed duty value take effect, and what PWM counter and duty state should be used at reset? | defaulted | S-5, S-6 |
| Should CPU_RESETN assertion and release be synchronous or asynchronous to CLK100MHZ? | answered | S-2, S-3, S-5 |

Pass 2 questions (one per field the spec does not state; the fields each one settles):

| Fields | Result | Draft value | Final value |
|---|---|---|---|
| c12_nexys_pwm_audio_top.contract.parameters.CLKS_PER_BIT | answered | {default: 868, values: [868]} | {default: 868} |
| c12_nexys_pwm_audio_top.contract.parameters.TIMEOUT_CYCLES | answered | {default: 100000000, values: [100000000]} | {default: 100000} |
| c12_nexys_pwm_audio_top.contract.parameters.BUILD_STAMP | assumption (oracle) | {default: 0, values: [0]} | {default: 0, values: [0]} |
| c12_nexys_pwm_audio_top.contract.ports.aud_pwm | assumption (oracle) | {dir: out, width: 1} | {dir: out, width: 1} |
| c12_nexys_pwm_audio_top.contract.ports.aud_sd | assumption (oracle) | {dir: out, width: 1, reset_value: 1} | {dir: out, width: 1, reset_value: 1} |
| c12_nexys_pwm_audio_top.contract.ports.led | assumption (oracle) | {dir: out, width: 16, reset_value: 0} | {dir: out, width: 16, reset_value: 0} |
| audio_state.contract.ports.gain | assumption (oracle) | {dir: in, width: 16} | {dir: in, width: 16} |
| audio_state.contract.data_formats.gain_u16 | assumption (oracle) | {format: u16, packing: unsigned Q15 gain register} | {format: u16, packing: unsigned Q15 gain register} |
| pwm_stage.contract.ports.sample_in | assumption (oracle) | {dir: in, width: 16} | {dir: in, width: 16} |
| pwm_stage.contract.ports.aud_pwm | assumption (oracle) | {dir: out, width: 1} | {dir: out, width: 1} |
| design.modules.audio_state.window_base | answered | 0 | 0 |
| design.board_ports.LED[15:0] | answered | {dir: out, drive: push-pull, from: c12_nexys_pw... | {dir: out, drive: push-pull, from: c12_nexys_pw... |

Unasked changes:

- `audio_state.contract.registers`: [{name: SAMPLE, offset: 0, access: RW, reset: 0... -> [{name: SAMPLE, offset: 0, access: RW, reset: 0...

## c12_pwm_audio

Drafter repairs: pass 1 0, pass 2 {'draft': 1, 'apply': 0}. Quotes that were not in the spec (so the field was asked): 11. Questions over the pass 2 budget: 0. Fields the drafter changed without being asked: 0. Calls by role: {'drafter': 4, 'oracle': 12}.

Today's checker on these files:

- connections: the design has 2 modules and no connection between them; connect each module's interfaces (point to point), or merge the modules

Checks against facts fixed before the run:

| Fact | Holds | Found |
|---|---|---|
| recorded c12 failure: AUD_PWM is open-drain (pulled low or released, never driven high) | yes | {'name': 'AUD_PWM', 'dir': 'out', 'drive': 'open-drain', 'from': 'pwm_audio.AUD_PWM'} |
| recorded c12 failure: the top has the 16-bit LED output (left off) | yes | [{'name': 'LED[15:0]', 'dir': 'out', 'drive': 'push-pull', 'from': 'pwm_audio.LED'}] |
| register map = the hidden spec's map (offset, name, access) | yes | [(0, 'SAMPLE', 'RW'), (1, 'GAIN', 'WO'), (2, 'SOUT', 'RO')] |

Pass 1 questions:

| Question | Result | Settles |
|---|---|---|
| What shell command, response, and register-addressing format should be used for sample writes, gain writes,... | answered | S-3 |
| When during a PWM period should the duty be captured, and what should the PWM counter and duty be initializ... | defaulted | S-4 |
| Should CPU_RESETN reset assertion be synchronous or asynchronous? | answered | S-6 |
| What defaults and representation should be used for CLKS_PER_BIT, TIMEOUT_CYCLES, and BUILD_STAMP? | answered | S-7 |

Pass 2 questions (one per field the spec does not state; the fields each one settles):

| Fields | Result | Draft value | Final value |
|---|---|---|---|
| audio_gain.contract.registers | answered | [{name: SAMPLE, offset: 0, access: RW, reset: 0... | [{name: SAMPLE, offset: 0, access: RW, reset: 0... |
| pwm_audio.contract.ports.AUD_PWM | assumption (oracle) | {dir: out} | {dir: out} |
| pwm_audio.contract.ports.AUD_SD | assumption (oracle) | {dir: out, reset_value: 1} | {dir: out, reset_value: 1} |
| pwm_audio.contract.ports.LED | assumption (oracle) | {dir: out, width: 16, reset_value: 0} | {dir: out, width: 16, reset_value: 0} |
| design.clocks.clk_sys | answered | {source: board, mhz: 100, port: CLK100MHZ} | {source: board, mhz: 100, port: CLK100MHZ} |
| design.modules.audio_gain.window_base | answered | 0 | 0 |
| design.board_ports.CLK100MHZ | assumption (oracle) | {dir: in, drive: input, to: clk_sys} | {dir: in, drive: input, to: clk_sys} |
| design.board_ports.CPU_RESETN | answered | {dir: in, drive: input, to: rst_sys} | {dir: in, drive: input, to: rst_sys} |
| design.board_ports.AUD_PWM | assumption (oracle) | {dir: out, drive: open-drain, from: pwm_audio.A... | {dir: out, drive: open-drain, from: pwm_audio.A... |
| design.board_ports.AUD_SD | assumption (oracle) | {dir: out, drive: push-pull, from: pwm_audio.AU... | {dir: out, drive: push-pull, from: pwm_audio.AU... |
| design.board_ports.LED[15:0] | answered | {dir: out, drive: push-pull, from: pwm_audio.LED} | {dir: out, drive: push-pull, from: pwm_audio.LED} |

## pilot1_run4

Drafter repairs: pass 1 0, pass 2 {'draft': 1, 'apply': 2}. Quotes that were not in the spec (so the field was asked): 30. Questions over the pass 2 budget: 24. Fields the drafter changed without being asked: 0. Calls by role: {'drafter': 6, 'oracle': 47}.

Today's checker on these files:

- module pixel_clock: not reachable from the board ports or the shell (no board port, no registers in the shell window, and no connection to a module that has one)

Checks against facts fixed before the run:

| Fact | Holds | Found |
|---|---|---|
| owner choice 1: a full-raster video stream with no back-pressure (every stream link: no back-pressure, no gaps) | yes | [{'link': 'timing_gen.out -> pattern_gen.in', 'protocol': 'axi4-stream', 'backpressure': [False, False], 's... |
| owner choice 2: median latency H_TOTAL + 2 | no | [] |
| owner choice 3: shell registers at window base 0x00 | yes | {'timing_gen': 4, 'pattern_gen': 0} |

Pass 1 questions:

| Question | Result | Settles |
|---|---|---|
| How should the 74.25 MHz pixel clock be generated on the Nexys A7-100T? | answered | S-1, S-5, S-6 |
| What should the filter do at the active-picture boundaries, where a full 3x3 neighbourhood extends outside ... | defaulted | S-3 |
| What colour-output width and encoding should be used for the VGA connector? | answered | S-2, S-3, S-5 |
| Which patterns should be selectable through the test shell? | defaulted | S-2, S-8 |
| What UART command and response format should the host use for identifying the design, selecting a pattern, ... | defaulted | S-7, S-8 |
| What should the frame counter count, and what width and wrap behaviour should it have? | defaulted | S-8 |
| How should the design initialize its state at FPGA configuration, given that BTNC is specified as a video-b... | defaulted | S-3, S-8 |

Pass 2 questions (one per field the spec does not state; the fields each one settles):

| Fields | Result | Draft value | Final value |
|---|---|---|---|
| pixel_clock.contract.clocks.clk.max_mhz | assumption (oracle) | 100 | 100 |
| pixel_clock.contract.resets.rst | answered | {polarity: active_low, style: async} | {polarity: active_low, style: async} |
| pixel_clock.contract.ports.locked | assumption (oracle) | {dir: out, width: 1, reset_value: 0} | {dir: out, width: 1, reset_value: 0} |
| timing_gen.contract.resets.rst | assumption (oracle) | {polarity: active_high, style: sync} | {polarity: active_high, style: sync} |
| timing_gen.contract.data_formats.rgb12 | assumption (oracle) | {format: u12, packing: three 4-bit RGB channels} | {format: u12, packing: three 4-bit RGB channels} |
| timing_gen.contract.data_formats.y10 | assumption (oracle) | {format: u10, packing: vertical raster coordinate} | {format: u10, packing: vertical raster coordinate} |
| timing_gen.contract.data_formats.bit1 | assumption (oracle) | {format: u1, packing: one raster metadata bit} | {format: u1, packing: one raster metadata bit} |
| timing_gen.contract.interfaces.out.protocol | assumption (oracle) | {protocol: axi4-stream, role: master} | {protocol: axi4-stream, role: master} |
| timing_gen.contract.interfaces.out.tdata<br>pattern_gen.contract.interfaces.in.tdata | assumption (oracle) | {width: 36, fields: [{name: rgb, bits: [35, 24]... | {width: 36, fields: [{name: rgb, bits: [35, 24]... |
| timing_gen.contract.interfaces.out.tlast<br>pattern_gen.contract.interfaces.in.tlast | assumption (oracle) | Assert on the final raster position of each frame. | Assert on the final raster position of each frame. |
| timing_gen.contract.interfaces.out.packet_beats<br>pattern_gen.contract.interfaces.in.packet_beats | assumption (oracle) | 1237500 | 1237500 |
| timing_gen.contract.interfaces.out.backpressure<br>pattern_gen.contract.interfaces.in.backpressure | answered | false | false |
| timing_gen.contract.interfaces.out.source_gaps<br>pattern_gen.contract.interfaces.in.source_gaps | answered | false | false |
| timing_gen.contract.throughput.out | assumption (oracle) | {beats_per_cycle: 1} | {beats_per_cycle: 1} |
| pattern_gen.contract.clocks.clk.max_mhz | answered | 74.25 | 74.25 |
| pattern_gen.contract.resets.rst | assumption (oracle) | {polarity: active_high, style: sync} | {polarity: active_high, style: sync} |
| pattern_gen.contract.ports.pattern_select | assumption (oracle) | {dir: in, width: 1} | {dir: in, width: 1} |
| pattern_gen.contract.data_formats.rgb12 | assumption (oracle) | {format: u12, packing: three 4-bit RGB channels} | {format: u12, packing: three 4-bit RGB channels} |
| pattern_gen.contract.data_formats.y10 | assumption (oracle) | {format: u10, packing: vertical raster coordinate} | {format: u10, packing: vertical raster coordinate} |
| pattern_gen.contract.data_formats.bit1 | assumption (oracle) | {format: u1, packing: one raster metadata bit} | {format: u1, packing: one raster metadata bit} |
| pattern_gen.contract.interfaces.in.protocol | assumption (oracle) | {protocol: axi4-stream, role: slave} | {protocol: axi4-stream, role: slave} |
| pattern_gen.contract.interfaces.out.protocol | assumption (oracle) | {protocol: axi4-stream, role: master} | {protocol: axi4-stream, role: master} |
| pattern_gen.contract.interfaces.out.tlast<br>median_filter.contract.interfaces.in.tlast | assumption (oracle) | Assert on the final raster position of each frame. | Assert on the final raster position of each frame. |
| pattern_gen.contract.interfaces.out.packet_beats<br>median_filter.contract.interfaces.in.packet_beats | assumption (oracle) | 1237500 | 1237500 |
| pattern_gen.contract.interfaces.out.backpressure<br>median_filter.contract.interfaces.in.backpressure | answered | false | false |
| pattern_gen.contract.interfaces.out.source_gaps<br>median_filter.contract.interfaces.in.source_gaps | answered | false | false |
| pattern_gen.contract.registers | assumption (oracle) | [{name: PATTERN, offset: 0, access: RW, reset: 0}] | [{name: PATTERN, offset: 0, access: RW, reset: 0}] |
| pattern_gen.contract.throughput.out | assumption (oracle) | {beats_per_cycle: 1} | {beats_per_cycle: 1} |
| pattern_gen.contract.latency.in.out | assumption (oracle) | null | null |
| median_filter.contract.resets.rst | answered | {polarity: active_high, style: sync} | {polarity: active_high, style: sync} |
| median_filter.contract.data_formats.rgb12 | assumption (oracle) | {format: u12, packing: three 4-bit RGB channels} | {format: u12, packing: three 4-bit RGB channels} |
| median_filter.contract.data_formats.y10 | assumption (oracle) | {format: u10, packing: vertical raster coordinate} | {format: u10, packing: vertical raster coordinate} |
| median_filter.contract.data_formats.bit1 | assumption (oracle) | {format: u1, packing: one raster metadata bit} | {format: u1, packing: one raster metadata bit} |
| median_filter.contract.interfaces.in.protocol | assumption (oracle) | {protocol: axi4-stream, role: slave} | {protocol: axi4-stream, role: slave} |
| median_filter.contract.interfaces.out.protocol | assumption (oracle) | {protocol: axi4-stream, role: master} | {protocol: axi4-stream, role: master} |
| median_filter.contract.interfaces.out.tlast<br>vga_output.contract.interfaces.in.tlast | assumption (oracle) | Assert on the final raster position of each frame. | Assert on the final raster position of each frame. |
| median_filter.contract.interfaces.out.packet_beats<br>vga_output.contract.interfaces.in.packet_beats | assumption (oracle) | 1237500 | 1237500 |
| median_filter.contract.interfaces.out.backpressure<br>vga_output.contract.interfaces.in.backpressure | assumption (oracle) | false | false |
| median_filter.contract.interfaces.out.source_gaps<br>vga_output.contract.interfaces.in.source_gaps | answered | false | false |
| median_filter.contract.throughput.out | answered | {beats_per_cycle: 1} | {beats_per_cycle: 1, from: in, out_per_in: 1} |
| median_filter.contract.latency.in.out | assumption (limit) | null | null |
| vga_output.contract.resets.rst | assumption (limit) | {polarity: active_high, style: sync} | {polarity: active_high, style: sync} |
| vga_output.contract.ports.red | assumption (limit) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| vga_output.contract.ports.green | assumption (limit) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| vga_output.contract.ports.blue | assumption (limit) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| vga_output.contract.ports.hsync | assumption (limit) | {dir: out, width: 1, reset_value: 0} | {dir: out, width: 1, reset_value: 0} |
| vga_output.contract.ports.vsync | assumption (limit) | {dir: out, width: 1, reset_value: 0} | {dir: out, width: 1, reset_value: 0} |
| vga_output.contract.data_formats.rgb12 | assumption (limit) | {format: u12, packing: three 4-bit RGB channels} | {format: u12, packing: three 4-bit RGB channels} |
| vga_output.contract.data_formats.y10 | assumption (limit) | {format: u10, packing: vertical raster coordinate} | {format: u10, packing: vertical raster coordinate} |
| vga_output.contract.data_formats.bit1 | assumption (limit) | {format: u1, packing: one raster metadata bit} | {format: u1, packing: one raster metadata bit} |
| vga_output.contract.interfaces.in.protocol | assumption (limit) | {protocol: axi4-stream, role: slave} | {protocol: axi4-stream, role: slave} |
| design.clocks.clk_sys | assumption (limit) | {source: board, mhz: 100, port: CLK100MHZ} | {source: board, mhz: 100, port: CLK100MHZ} |
| design.clocks.clk_video | assumption (limit) | {source: mmcm, mhz: 74.25, from: clk_sys} | {source: mmcm, mhz: 74.25, from: clk_sys} |
| design.resets.rst_sys | assumption (limit) | {from: CPU_RESETN, polarity: active_low, style:... | {from: CPU_RESETN, polarity: active_low, style:... |
| design.resets.rst_video | assumption (limit) | {from: rst_sys, polarity: active_high, style: s... | {from: rst_sys, polarity: active_high, style: s... |
| design.modules.timing_gen.window_base | assumption (limit) | 4 | 4 |
| design.modules.pattern_gen.window_base | assumption (limit) | 0 | 0 |
| design.board_ports.CLK100MHZ | assumption (limit) | {dir: in, drive: input, to: clk_sys} | {dir: in, drive: input, to: clk_sys} |
| design.board_ports.CPU_RESETN | assumption (limit) | {dir: in, drive: input, to: rst_sys} | {dir: in, drive: input, to: rst_sys} |
| design.board_ports.VGA_R[3:0] | assumption (limit) | {dir: out, drive: push-pull, from: vga_output.red} | {dir: out, drive: push-pull, from: vga_output.red} |
| design.board_ports.VGA_G[3:0] | assumption (limit) | {dir: out, drive: push-pull, from: vga_output.g... | {dir: out, drive: push-pull, from: vga_output.g... |
| design.board_ports.VGA_B[3:0] | assumption (limit) | {dir: out, drive: push-pull, from: vga_output.b... | {dir: out, drive: push-pull, from: vga_output.b... |
| design.board_ports.VGA_HS | assumption (limit) | {dir: out, drive: push-pull, from: vga_output.h... | {dir: out, drive: push-pull, from: vga_output.h... |
| design.board_ports.VGA_VS | assumption (limit) | {dir: out, drive: push-pull, from: vga_output.v... | {dir: out, drive: push-pull, from: vga_output.v... |

## pilot1_run5

Drafter repairs: pass 1 0, pass 2 {'draft': 1, 'apply': 3}. Quotes that were not in the spec (so the field was asked): 8. Questions over the pass 2 budget: 3. Fields the drafter changed without being asked: 2. Calls by role: {'drafter': 7, 'oracle': 39}.

Checks against facts fixed before the run:

| Fact | Holds | Found |
|---|---|---|
| owner choice 1: a full-raster video stream with no back-pressure (every stream link: no back-pressure, no gaps) | yes | [{'link': 'video_source.out -> median_filter.in', 'protocol': 'axi4-stream', 'backpressure': [False, False]... |
| owner choice 2: median latency H_TOTAL + 2 | no | ["median_filter: {'from': 'in', 'to': 'out', 'cycles': 1651}"] |
| owner choice 3: shell registers at window base 0x00 | yes | {'video_source': 0, 'vga_output': 4} |

Pass 1 questions:

| Question | Result | Settles |
|---|---|---|
| How should the 3 x 3 neighbourhood be formed at the active-picture edges? | defaulted | S-3 |
| Which patterns must be selectable in addition to the default colour bars? | defaulted | S-2, S-7 |
| What UART command and response format should the test shell use, including serial framing? | defaulted | S-7 |
| What are the frame counter's width, initial value, and increment point? | defaulted | S-7 |
| What colour-channel width and digital levels should be used for the VGA output and colour bars? | answered | S-2, S-3, S-5 |

Pass 2 questions (one per field the spec does not state; the fields each one settles):

| Fields | Result | Draft value | Final value |
|---|---|---|---|
| video_source.contract.resets.rst | answered | {polarity: active_high, style: sync} | {polarity: active_low, style: async} |
| video_source.contract.interfaces.out.tlast<br>median_filter.contract.interfaces.in.tlast | assumption (oracle) | End of each 1650-pixel line. | End of each 1650-pixel line. |
| video_source.contract.interfaces.out.backpressure<br>median_filter.contract.interfaces.in.backpressure | answered | false | false |
| video_source.contract.interfaces.out.source_gaps<br>median_filter.contract.interfaces.in.source_gaps | assumption (oracle) | false | false |
| video_source.contract.throughput.out | assumption (oracle) | {beats_per_cycle: 1} | {beats_per_cycle: 1} |
| median_filter.contract.resets.rst | answered | {polarity: active_high, style: sync} | {polarity: active_low, style: async} |
| median_filter.contract.interfaces.out.tlast<br>vga_output.contract.interfaces.in.tlast | assumption (oracle) | End of each 1650-pixel line. | End of each 1650-pixel line. |
| median_filter.contract.interfaces.out.packet_beats<br>vga_output.contract.interfaces.in.packet_beats | assumption (oracle) | 1650 | 1650 |
| median_filter.contract.interfaces.out.backpressure<br>vga_output.contract.interfaces.in.backpressure | assumption (oracle) | false | false |
| median_filter.contract.interfaces.out.source_gaps<br>vga_output.contract.interfaces.in.source_gaps | answered | false | false |
| median_filter.contract.throughput.in | answered | {beats_per_cycle: 1} | {beats_per_cycle: 1, from: in, out_per_in: 1} |
| median_filter.contract.throughput.out | answered | {beats_per_cycle: 1} | {beats_per_cycle: 1, from: in, out_per_in: 1} |
| vga_output.contract.resets.rst | assumption (oracle) | {polarity: active_high, style: sync} | {polarity: active_low, style: async} |
| vga_output.contract.ports.vga_r | assumption (oracle) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| vga_output.contract.ports.vga_g | assumption (oracle) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| vga_output.contract.ports.vga_b | assumption (oracle) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| vga_output.contract.ports.vga_hs | assumption (oracle) | {dir: out, width: 1, reset_value: 0} | {dir: out, width: 1, reset_value: 0} |
| vga_output.contract.ports.vga_vs | assumption (oracle) | {dir: out, width: 1, reset_value: 0} | {dir: out, width: 1, reset_value: 0} |
| vga_output.contract.ports.frame_count | assumption (oracle) | {dir: out, width: 32, reset_value: 0} | {dir: out, width: 32, reset_value: 0} |
| vga_output.contract.throughput.in | answered | {beats_per_cycle: 1} | {beats_per_cycle: 1, from: in, out_per_in: 1} |
| design.clocks.clk_sys | answered | {source: board, mhz: 100, port: CLK100MHZ} | {source: board, mhz: 100, port: CLK100MHZ} |
| design.resets.rst_pix | answered | {from: CPU_RESETN, polarity: active_high, style... | {from: BTNC, polarity: active_low, style: async} |
| video_source.contract.data_formats.x_coord | assumption (oracle) | {format: u11, packing: 'Horizontal raster coord... | {format: u11, packing: 'Horizontal raster coord... |
| video_source.contract.data_formats.y_coord | assumption (oracle) | {format: u10, packing: 'Vertical raster coordin... | {format: u10, packing: 'Vertical raster coordin... |
| video_source.contract.data_formats.rgb444 | assumption (oracle) | {format: u12, packing: 'R[3:0], G[3:0], B[3:0],... | {format: u12, packing: 'R[3:0], G[3:0], B[3:0],... |
| median_filter.contract.data_formats.x_coord | assumption (oracle) | {format: u11, packing: 'Horizontal raster coord... | {format: u11, packing: 'Horizontal raster coord... |
| median_filter.contract.data_formats.y_coord | assumption (oracle) | {format: u10, packing: 'Vertical raster coordin... | {format: u10, packing: 'Vertical raster coordin... |
| median_filter.contract.data_formats.rgb444 | assumption (oracle) | {format: u12, packing: 'R[3:0], G[3:0], B[3:0],... | {format: u12, packing: 'R[3:0], G[3:0], B[3:0],... |
| vga_output.contract.data_formats.x_coord | assumption (oracle) | {format: u11, packing: 'Horizontal raster coord... | {format: u11, packing: 'Horizontal raster coord... |
| vga_output.contract.data_formats.y_coord | assumption (oracle) | {format: u10, packing: 'Vertical raster coordin... | {format: u10, packing: 'Vertical raster coordin... |
| vga_output.contract.data_formats.rgb444 | assumption (oracle) | {format: u12, packing: 'R[3:0], G[3:0], B[3:0],... | {format: u12, packing: 'R[3:0], G[3:0], B[3:0],... |
| vga_output.contract.data_formats.frame_counter | assumption (oracle) | {format: u32, packing: 'Completed-frame count, ... | {format: u32, packing: 'Completed-frame count, ... |
| design.board_ports.CLK100MHZ | assumption (oracle) | {dir: in, drive: input, to: clk_sys} | {dir: in, drive: input, to: clk_sys} |
| design.board_ports.CPU_RESETN | answered | {dir: in, drive: input, to: rst_pix} | None |
| design.board_ports.VGA_HS | assumption (limit) | {dir: out, drive: push-pull, from: vga_output.v... | {dir: out, drive: push-pull, from: vga_output.v... |
| design.board_ports.VGA_VS | assumption (limit) | {dir: out, drive: push-pull, from: vga_output.v... | {dir: out, drive: push-pull, from: vga_output.v... |
| design.board_ports.LED[0] | assumption (limit) | {dir: out, drive: push-pull, from: clk_pix.locked} | {dir: out, drive: push-pull, from: clk_pix.locked} |

Unasked changes:

- `design.board_ports.BTNC`: {dir: in, drive: input, to: video_source.button... -> {dir: in, drive: input, to: rst_pix}
- `vga_output.contract.resets.rst`: {polarity: active_high, style: sync} -> {polarity: active_low, style: async}

## pilot1

Drafter repairs: pass 1 0, pass 2 {'draft': 2, 'apply': 2}. Quotes that were not in the spec (so the field was asked): 17. Questions over the pass 2 budget: 7. Fields the drafter changed without being asked: 6. Calls by role: {'drafter': 7, 'oracle': 57}.

Checks against facts fixed before the run:

| Fact | Holds | Found |
|---|---|---|
| owner choice 1: a full-raster video stream with no back-pressure (every stream link: no back-pressure, no gaps) | yes | [{'link': 'pattern_timing.out -> median_filter.in', 'protocol': 'axi4-stream', 'backpressure': [False, Fals... |
| owner choice 2: median latency H_TOTAL + 2 | no | ["median_filter: {'from': 'in', 'to': 'out', 'cycles': 1}"] |
| owner choice 3: shell registers at window base 0x00 | yes | {'pattern_timing': 0} |

Pass 1 questions:

| Question | Result | Settles |
|---|---|---|
| What boundary rule should the 3 x 3 filter use for neighbourhood samples beyond the active picture? | defaulted | S-3 |
| Which patterns should be selectable through the UART? | defaulted | S-2, S-7 |
| What UART command and response format should select a pattern and read the frame counter? | defaulted | S-7 |
| How should the frame counter count frames, and what width and reset behavior should it have? | defaulted | S-7 |
| What pixel-clock stability criterion should control the colour blanking and LED[0]? | defaulted | S-5, S-6 |
| What colour-channel width should be used at the VGA output? | answered | S-2, S-3 |

Pass 2 questions (one per field the spec does not state; the fields each one settles):

| Fields | Result | Draft value | Final value |
|---|---|---|---|
| pattern_timing.contract.resets.pixel_reset | assumption (oracle) | {polarity: active_low, style: sync} | {polarity: active_low, style: sync} |
| pattern_timing.contract.ports.pattern_select | assumption (oracle) | {dir: in, width: 2} | {dir: in, width: 2} |
| pattern_timing.contract.ports.frame_count | assumption (oracle) | {dir: out, width: 32, reset_value: 0} | {dir: out, width: 32, reset_value: 0} |
| pattern_timing.contract.interfaces.out.protocol | assumption (oracle) | {protocol: axi4-stream, role: master} | {protocol: axi4-stream, role: master} |
| pattern_timing.contract.interfaces.out.tdata<br>median_filter.contract.interfaces.in.tdata | assumption (oracle) | {width: 36, fields: [{name: x, bits: [35, 25], ... | {width: 48, fields: [{name: x, bits: [47, 37], ... |
| pattern_timing.contract.interfaces.out.tuser<br>median_filter.contract.interfaces.in.tuser | assumption (oracle) | null | null |
| pattern_timing.contract.interfaces.out.tlast<br>median_filter.contract.interfaces.in.tlast | assumption (oracle) | null | null |
| pattern_timing.contract.interfaces.out.packet_beats<br>median_filter.contract.interfaces.in.packet_beats | assumption (oracle) | null | null |
| pattern_timing.contract.interfaces.out.backpressure<br>median_filter.contract.interfaces.in.backpressure | answered | false | false |
| pattern_timing.contract.interfaces.out.source_gaps<br>median_filter.contract.interfaces.in.source_gaps | answered | false | false |
| pattern_timing.contract.registers | assumption (oracle) | [{name: PATTERN, offset: 0, access: RW, reset: ... | [{name: PATTERN, offset: 0, access: RW, reset: ... |
| pattern_timing.contract.throughput.out | answered | {beats_per_cycle: 1} | {beats_per_cycle: 1} |
| median_filter.contract.resets.pixel_reset | answered | {polarity: active_low, style: sync} | {polarity: active_low, style: sync} |
| median_filter.contract.interfaces.in.protocol | assumption (oracle) | {protocol: axi4-stream, role: slave} | {protocol: axi4-stream, role: slave} |
| median_filter.contract.interfaces.out.protocol | assumption (oracle) | {protocol: axi4-stream, role: master} | {protocol: axi4-stream, role: master} |
| median_filter.contract.interfaces.out.tdata<br>vga_output.contract.interfaces.in.tdata | assumption (oracle) | {width: 36, fields: [{name: x, bits: [35, 25], ... | {width: 48, fields: [{name: x, bits: [47, 37], ... |
| median_filter.contract.interfaces.out.tuser<br>vga_output.contract.interfaces.in.tuser | assumption (oracle) | null | null |
| median_filter.contract.interfaces.out.tlast<br>vga_output.contract.interfaces.in.tlast | assumption (oracle) | null | null |
| median_filter.contract.interfaces.out.packet_beats<br>vga_output.contract.interfaces.in.packet_beats | assumption (oracle) | null | null |
| median_filter.contract.interfaces.out.backpressure<br>vga_output.contract.interfaces.in.backpressure | assumption (oracle) | false | false |
| median_filter.contract.interfaces.out.source_gaps<br>vga_output.contract.interfaces.in.source_gaps | answered | false | false |
| median_filter.contract.throughput.in | answered | {beats_per_cycle: 1} | {beats_per_cycle: 1} |
| median_filter.contract.throughput.out | assumption (oracle) | {beats_per_cycle: 1} | {beats_per_cycle: 1} |
| median_filter.contract.latency.in.out | answered | null | 1 |
| vga_output.contract.resets.pixel_reset | assumption (oracle) | {polarity: active_low, style: sync} | {polarity: active_low, style: sync} |
| vga_output.contract.ports.pixel_stable | assumption (oracle) | {dir: in, width: 1} | {dir: in, width: 1} |
| vga_output.contract.ports.blank_button | assumption (oracle) | {dir: in, width: 1} | {dir: in, width: 1} |
| vga_output.contract.ports.red | assumption (oracle) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| vga_output.contract.ports.green | assumption (oracle) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| vga_output.contract.ports.blue | assumption (oracle) | {dir: out, width: 4, reset_value: 0} | {dir: out, width: 4, reset_value: 0} |
| vga_output.contract.ports.hsync | assumption (oracle) | {dir: out, width: 1, reset_value: 0} | {dir: out, width: 1, reset_value: 0} |
| vga_output.contract.ports.vsync | assumption (oracle) | {dir: out, width: 1, reset_value: 0} | {dir: out, width: 1, reset_value: 0} |
| vga_output.contract.interfaces.in.protocol | assumption (oracle) | {protocol: axi4-stream, role: slave} | {protocol: axi4-stream, role: slave} |
| vga_output.contract.throughput.in | answered | {beats_per_cycle: 1} | {beats_per_cycle: 1} |
| design.clocks.sys_clk | answered | {source: board, mhz: 100, port: CLK100MHZ} | {source: board, mhz: 100, port: CLK100MHZ} |
| design.clocks.pixel_clk | answered | {source: mmcm, mhz: 74.25, from: sys_clk} | {source: mmcm, mhz: 74.25, from: sys_clk} |
| design.resets.sys_reset | answered | {from: CPU_RESETN, polarity: active_low, style:... | {from: CPU_RESETN, polarity: active_low, style:... |
| design.resets.pixel_reset | answered | {from: sys_reset, polarity: active_low, style: ... | {from: sys_reset, polarity: active_low, style: ... |
| design.modules.pattern_timing.window_base | answered | 0 | 0 |
| pattern_timing.contract.data_formats.raster_x | assumption (oracle) | {format: u11, packing: Raster horizontal coordi... | {format: u11, packing: Raster horizontal coordi... |
| pattern_timing.contract.data_formats.raster_y | assumption (oracle) | {format: u10, packing: Raster vertical coordinate} | {format: u10, packing: Raster vertical coordinate} |
| pattern_timing.contract.data_formats.channel | assumption (oracle) | {format: u4, packing: Unsigned VGA colour channel} | {format: u8, packing: Unsigned 8-bit colour cha... |
| pattern_timing.contract.data_formats.flag | assumption (oracle) | {format: u1, packing: Boolean raster or sync flag} | {format: u1, packing: Boolean raster or sync flag} |
| median_filter.contract.data_formats.raster_x | assumption (oracle) | {format: u11, packing: Raster horizontal coordi... | {format: u11, packing: Raster horizontal coordi... |
| median_filter.contract.data_formats.raster_y | assumption (oracle) | {format: u10, packing: Raster vertical coordinate} | {format: u10, packing: Raster vertical coordinate} |
| median_filter.contract.data_formats.channel | answered | {format: u4, packing: Unsigned VGA colour channel} | {format: u8, packing: 'Each pixel is 8 bits; pi... |
| median_filter.contract.data_formats.flag | assumption (oracle) | {format: u1, packing: Boolean raster or sync flag} | {format: u1, packing: Boolean raster or sync flag} |
| vga_output.contract.data_formats.raster_x | assumption (oracle) | {format: u11, packing: Raster horizontal coordi... | {format: u11, packing: Raster horizontal coordi... |
| vga_output.contract.data_formats.raster_y | assumption (oracle) | {format: u10, packing: Raster vertical coordinate} | {format: u10, packing: Raster vertical coordinate} |
| vga_output.contract.data_formats.channel | assumption (oracle) | {format: u4, packing: Unsigned VGA colour channel} | {format: u8, packing: Unsigned 8-bit colour cha... |
| vga_output.contract.data_formats.flag | assumption (oracle) | {format: u1, packing: Boolean raster or sync flag} | {format: u1, packing: Boolean raster or sync flag} |
| design.board_ports.CLK100MHZ | assumption (limit) | {dir: in, drive: input, to: sys_clk} | {dir: in, drive: input, to: sys_clk} |
| design.board_ports.CPU_RESETN | assumption (limit) | {dir: in, drive: input, to: sys_reset} | {dir: in, drive: input, to: sys_reset} |
| design.board_ports.VGA_HS | assumption (limit) | {dir: out, drive: push-pull, from: vga_output.h... | {dir: out, drive: push-pull, from: vga_output.h... |
| design.board_ports.VGA_VS | assumption (limit) | {dir: out, drive: push-pull, from: vga_output.v... | {dir: out, drive: push-pull, from: vga_output.v... |
| design.board_ports.VGA_R[3:0] | assumption (limit) | {dir: out, drive: push-pull, from: vga_output.red} | {dir: out, drive: push-pull, from: vga_output.red} |
| design.board_ports.VGA_G[3:0] | assumption (limit) | {dir: out, drive: push-pull, from: vga_output.g... | {dir: out, drive: push-pull, from: vga_output.g... |
| design.board_ports.VGA_B[3:0] | assumption (limit) | {dir: out, drive: push-pull, from: vga_output.b... | {dir: out, drive: push-pull, from: vga_output.b... |

Unasked changes:

- `median_filter.contract.interfaces.in.tdata`: {width: 36, fields: [{name: x, bits: [35, 25], ... -> {width: 48, fields: [{name: x, bits: [47, 37], ...
- `median_filter.contract.interfaces.out.tdata`: {width: 36, fields: [{name: x, bits: [35, 25], ... -> {width: 48, fields: [{name: x, bits: [47, 37], ...
- `pattern_timing.contract.data_formats.channel`: {format: u4, packing: Unsigned VGA colour channel} -> {format: u8, packing: Unsigned 8-bit colour cha...
- `pattern_timing.contract.interfaces.out.tdata`: {width: 36, fields: [{name: x, bits: [35, 25], ... -> {width: 48, fields: [{name: x, bits: [47, 37], ...
- `vga_output.contract.data_formats.channel`: {format: u4, packing: Unsigned VGA colour channel} -> {format: u8, packing: Unsigned 8-bit colour cha...
- `vga_output.contract.interfaces.in.tdata`: {width: 36, fields: [{name: x, bits: [35, 25], ... -> {width: 48, fields: [{name: x, bits: [47, 37], ...

## pilot1_run3 (stopped, no files written)

53 model calls, 0.0463 USD provider-reported. Last line: `RuntimeError: phase 0 pass2-apply: still invalid after 3 repairs: ['reset rst_pix_cpu: comes from the board (CPU_RESETN) but no board port drives it']`
