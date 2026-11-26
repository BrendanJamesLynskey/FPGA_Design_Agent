# Brief 215 sample50: classification of 26 disagreement runs

Counts found: group A = 15, group B = 11 (as expected). Hidden-test results use result_ext_mapped. Verdicts marked "probable" were read from the failure summary and prompt only; the hidden test source was not available.

| id | group | verdict | cause | evidence |
|---|---|---|---|---|
| cvdp_copilot_64b66b_decoder_0011 | A | spec reading differs | functional | 8 of 10 hidden tests pass; control-only and mixed-mode cases fail on the data bytes (error vs idle characters; data byte placement). Agent followed the prompt table and its example 2 literally. |
| cvdp_copilot_axis_border_gen_0014 | A | benchmark-limited | interface name or width | Hidden compile fails for all 3 parameter sets. Harness top is axis_border_gen_with_resize but the agent named the module in that file axis_image_border_gen_with_resizer (the prompt uses both spellings). |
| cvdp_copilot_bus_arbiter_0001 | A | benchmark-limited | interface name or width | Hidden compile fails. Prompt skeleton says module bus_arbiter; harness top-level is cvdp_copilot_bus_arbiter (only in the hidden env file). Agent followed the prompt. |
| cvdp_copilot_interrupt_controller_0017 | A | spec reading differs | latency or cycle timing | Hidden test: interrupt_valid not high while 2 interrupts pending. Prompt gives a 6-state FSM but no cycle counts, so the wait the test allows is not derivable. |
| cvdp_copilot_ping_pong_buffer_0001 | A | spec reading differs | functional | 3 of 6 hidden tests fail: buffer_select never toggles, empty never reported. Prompt says select toggles at end of read and also when a buffer fills (ambiguous); an X was also seen on a flag. |
| cvdp_copilot_rounding_0001 | A | benchmark-limited | functional | Hidden test expects out_data to stay at the input value when rounding overflows (expected 255, got 0). Prompt only says cout is set on overflow; wrap vs hold is not stated. |
| cvdp_copilot_apb_dsp_unit_0001 | A | benchmark-limited (probable) | other | Hidden test reads memory contents at address 100 and gets 0. Prompt says only "a 1 KB SRAM module"; the test most likely inspects the memory by an internal name or path not in the text. Not certain. |
| cvdp_copilot_axi_stream_upscale_0001 | A | benchmark-limited | protocol handshake | Hidden check expects s_axis_ready low at some point; agent drives it from m_axis_ready and the valid register. Prompt lists s_axis_ready but never gives its rule. |
| cvdp_copilot_dot_product_0005 | A | benchmark-limited | functional | Mismatches on random vectors: expected 0x01a9e45d, got 0xff9be45d. Agent treated operands as signed; the prompt says nothing on signedness. |
| cvdp_copilot_serial_in_parallel_out_0014 | A | benchmark-limited | interface name or width | Shift tests pass, then the test fails reading an instance named crc_gen inside the top. Prompt names the module crc_generator but not the instance. |
| cvdp_copilot_sync_lifo_0010 | A | benchmark-limited | functional | Reads return 0 where a value is expected. Prompt has no port list or read-timing rule (registered vs combinational data_out), only the new error/valid flags. |
| cvdp_copilot_elevator_control_0033 | A | undecided | other | Prompt is a lint-review task on an existing module; agent rewrote it. Hidden run fails iverilog for N=12,13,14,24 and the Verilator lint check. The compiler message is not in the saved log, so cannot tell RTL error from missing original source. |
| cvdp_copilot_filo_0033 | A | benchmark-limited | functional | Hidden "feedthrough" test expects the pushed value on pop (got 0). Prompt is a bug report on an existing design and does not give port list or simultaneous push/pop behaviour. |
| cvdp_copilot_galois_encryption_0001 | A | RTL wrong | functional | Output differs from the model on the first block. The prompt gives a worked example table that the agent's own bench evidently did not enforce (bench shares the agent's misreading). |
| cvdp_copilot_rgb2ycbcr_0001 | A | benchmark-limited | interface name or width | Test fails reading an internal signal named fifo_data; the bug-report prompt never names it, and the agent's FIFO uses fifo_mem. |
| cvdp_copilot_cellular_automata_0001 | B | bench wrong (probable) | latency or cycle timing | Gate: simulate, own SVA A_reset_load (out equals the previous-cycle seed) failed on 6 visits. Prompt says synchronous reset loads seed; the checker's past-value sampling is off by a cycle. Hidden test passes. |
| cvdp_copilot_single_number_0001 | B | tool/compile | other | Gate: design standards only, the architecture checker crashed (KeyError on a key in the agent's own file). Simulation was not the failing gate. Hidden test passes. |
| cvdp_copilot_complex_multiplier_0001 | B | RTL wrong | reset values | Gate: simulate, test_reset_pulse_between... Prompt says asynchronous reset; RTL resets only on the clock edge (house sync-reset rule). Hidden test only resets at edges, so passes. |
| cvdp_copilot_dbi_0001 | B | RTL wrong | reset values | Gate: simulate, test_reset_async: outputs not cleared between edges. Prompt says asynchronous reset; RTL uses sync reset; agent's own note records the mismatch. Hidden test lenient. |
| cvdp_copilot_fsm_seq_detector_0001 | B | bench wrong (probable) | other | Gates: simulate (own SVA A_match_pulse, functional bins 0 of 0) and design standards (flags the async reset that the prompt requires). Agent hand-checked the transition table as correct. Hidden test passes. |
| cvdp_copilot_perceptron_0001 | B | RTL wrong | latency or cycle timing | Gates: simulate (training result 15 vs 1) and design standards (reset style). Agent's own note: 5 cycles per later vector vs spec 6, plus sync reset. Hidden test does not probe this. |
| cvdp_copilot_dbi_0008 | B | bench wrong | reset values | Gate: simulate, test_async_reset. The short prompt never mentions an asynchronous reset; the bench demands one (inherited from the earlier spec). Hidden test passes. |
| cvdp_copilot_run_length_0007 | B | RTL wrong | reset values | Gate: simulate, test_async_reset: output stays 15 after reset. Prompt says asynchronous reset; RTL sync-only. Hidden test lenient. |
| cvdp_copilot_one_hot_address_0001 | B | RTL wrong | reset values | Gate: simulate, test_async_reset: o_ready stays 0. Prompt says active-low asynchronous reset; RTL sync-only. Hidden test lenient. |
| cvdp_copilot_scrambler_0018 | B | bench wrong | reset values | Gate: simulate, test_async_reset ("not cleared asynchronously"). The lint-review prompt gives no reset rule; bench invented asynchronous clearing. Hidden test passes. |
| cvdp_copilot_prim_max_0001 | B | undecided | latency or cycle timing | Gate: simulate, test_latency "early valid at 3". Agent's note says RTL latency (4 clocks) matches spec and the cause was never examined; bench off-by-one is likely but unproven. Hidden test passes. |

## Counts

| verdict | A (15) | B (11) |
|---|---|---|
| bench wrong (incl. probable) | 0 | 4 |
| RTL wrong | 1 | 5 |
| spec reading differs | 3 | 0 |
| benchmark-limited (incl. probable) | 10 | 0 |
| tool/compile | 0 | 1 |
| undecided | 1 | 1 |

| cause | A | B |
|---|---|---|
| interface name or width | 4 | 0 |
| latency or cycle timing | 1 | 3 |
| reset values | 0 | 6 |
| protocol handshake | 1 | 0 |
| functional | 7 | 0 |
| file/path naming | 0 | 0 |
| other | 2 | 2 |

## What this implies for a repair-feedback digest

- Group B is mostly a self-inflicted loop: 9 of 11 final RTLs pass hidden tests while the agent's gate fails, and 6 of those hit the same reset-style item. The digest should say when the same assertion has failed on 3 or more visits so the agent can ask whether the bench or a house rule contradicts the prompt, not keep patching the RTL.
- Reset style is the standout conflict: the prompt demands asynchronous reset while the design-standards gate and the agent's RTL choose synchronous. The digest should name both sources and tell the agent the prompt wins (or that a waiver is needed) instead of leaving two gates in opposition.
- Group A shows that "all own gates passed" is weak evidence: 10 of 15 failures come from facts the prompt does not state (hidden top-level or instance names, signedness, overflow value, ready rule). The digest should prompt for explicit assumptions on these items (top module name, internal names, signed/unsigned, overflow, handshake) and keep names stated in the prompt over inferred ones.
- Where the prompt gives a worked example or table (galois, 64b66b), the digest should require the bench to replay it; those two cases were the ones where the model was plausibly wrong or misread.
- Tell the model "the bench or the spec may be wrong" selectively: in about 40 percent of group B (bench wrong or tool fault) a bench or checker fault was the cause, but in group A only 4 of 15 were interface-name issues the agent could have caught. Use that wording only when the failing assertion is a self-written bench or checker check or the same failure repeats, not on every failure.
