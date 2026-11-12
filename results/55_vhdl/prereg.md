# Brief 55 VHDL translations: pre-registration (written 2026-11-12 00:40, before the first model call)

## What is measured

Whether openai/gpt-6-luna (OpenRouter, `data_collection: deny`) writes VHDL-2008 that passes the **same hidden tests** and the
**same Vivado gates** as the SystemVerilog reference of each development drill, and what it gets wrong.

## Drills (development only; nothing held out is read)

| id | area | source | tests that score it |
|---|---|---|---|
| t1_gray_stepper | T1 | `benchmark/tasks/t1_gray_stepper/ref/rtl` | hidden bench (cocotb, shell), Vivado build |
| t1_elevator_fsm | FSM | `benchmark/tasks/t1_elevator_fsm/ref/rtl` | hidden bench, Vivado build |
| d24_registered_outputs | FSM (brief 24 drill) | `benchmark/drills/d24_registered_outputs/ref/rtl` | hidden bench + `lib/grade_fsm.py` pin drivers, Vivado build |
| t1_sync_fifo_regs | memory | `benchmark/tasks/t1_sync_fifo_regs/ref/rtl` | hidden bench, Vivado build |
| t1_debounce_bank | T1 (asynchronous inputs) | `benchmark/tasks/t1_debounce_bank/ref/rtl` | hidden bench, Vivado build |
| cdcfx_c10 | CDC (asynchronous FIFO, Gray pointers) | `flow/tests/fixtures/cdc_mutants/rtl/cdcfx_c10.sv` | the fixture's own cocotb test (GHDL native), Vivado synthesis + the brief 16 CDC gate |
| cdcfx_c8 | CDC (4-phase handshake) | `flow/tests/fixtures/cdc_mutants/rtl/cdcfx_c8.sv` | as cdcfx_c10 |
| axil_regs | AXI4-Lite slave | knowledge bank `tools/axi_examples/axil_regs.v` (ours, brief 17) | the bank's AXI-Lite cocotb tests (GHDL native), Vivado out-of-context synthesis |

## Arms and runs

- **A (baseline):** `tools/vhdl_translate.py` with no knowledge-bank skill: the spec (board drills), the SystemVerilog, and the language
  boundary notes of `flow/vhdl.py` only. One run per drill. Feedback: GHDL lint only, at most 3 rounds, $0.30 cap per drill.
- **B (with the skills):** the same tool with the new `vhdl-design` skills passed in, run only on drills that fail in A (or whose A
  output shows a rule-worthy mistake), after the mistakes of A are written into the skills. One run per such drill.
- **Agent (end to end):** `python -m agent run <spec.md> --hdl vhdl --stop-after 2 --verif-level V1 --max-usd 0.75` on two board
  drills (t1_gray_stepper, t1_sync_fifo_regs), to show the roles take `language: vhdl`; scored by the hidden bench.

## Scoring (no model scores anything)

- Hidden bench: `python -m flow.vhdl_score <task> --rtl <out>/rtl` (GHDL netlist of the VHDL + the frozen `run_task.run`), Icarus,
  seed 1. Pass = every test passes.
- Vivado 2026.1 build of each passing board design through `flow/run_vivado.sh` (base variant): every gate of `flow/gates.py`
  compared with the SystemVerilog reference's build of the same day (LUT, FF, BRAM, WNS, gate pass).
- Block drills: Vivado synthesis (out of context) and, for CDC, the brief 16 CDC structure gate on the VHDL.

## Stopping rules

- Brief cap $10 by provider-reported cost; stop new runs at $9.
- No re-run of a passing drill. A failure in B is reported as a failure.

## Amendments (dated, before the runs they affect)

1. **2026-11-12 00:05, after arm A, before arm B.** Arm A's prompt carried the boundary notes of `flow/vhdl.py` as they were then.
   Arm B's prompt carries the notes as amended from A's mistakes (a bullet on the shell's `sync2`/`reset_sync` names, a bullet on
   start values) **and** three skills of the new `vhdl-design` unit (`vhdl-mixed-language-boundary`, `vhdl-types-drivers-and-numeric-std`,
   `vhdl-processes-resets-and-fsms`). So B measures "notes + skills" together, not the skills alone. B was run on all five board
   drills (all failed in A) and on `cdcfx_c8` (failed in A); `cdcfx_c10` and `axil_regs` passed in A and were not re-run.
2. **Diagnostic, not a scored arm.** `translations/A_diag/` holds arm A's board translations with the colliding entities renamed by a
   script (`sync2` -> `sync2_vh`, `reset_sync` -> `reset_sync_vh`), scored to see whether anything beyond the name clash failed
   (`scores/Adiag_*`). It is never counted as a pass.
3. **Hand fix, not a scored arm.** `translations/hand_fix/cdcfx_c8/` is arm B's `cdcfx_c8` with start values added by hand to its two
   output registers, used by the tests to show that rule M2 is the whole difference.
4. **The lint feedback kept the tail of GHDL's output** in the A and B runs (a cascade of follow-on errors can hide the first one);
   from 00:15 the tool keeps the head. Only B's `t1_elevator_fsm` needed a second round.
