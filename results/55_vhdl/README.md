# Brief 55: VHDL designs, measured

How the flow handles VHDL is in [docs/vhdl.md](../../docs/vhdl.md). This page is what was measured on 2026-11-12. Every number
comes from a file in this directory. Tools: GHDL 4.1.0, Icarus 12, cocotb 2.0.1, Vivado 2026.1, model openai/gpt-6-luna on
OpenRouter (`data_collection: deny`). Pre-registration and its dated amendments: [prereg.md](prereg.md).

## Nulls first

- **The first translations failed every board drill (0 of 5)**, all for one reason: the model wrote the shell's helper modules
  `sync2` and `reset_sync` again as VHDL entities of the same names, which clash with the shell's SystemVerilog modules (mistake
  M1). With that one name clash renamed by a script (a diagnostic, never counted), all five passed their hidden benches
  ([scores/Adiag_*](scores/)).
- **The end-to-end agent runs did not pass.** Two runs of the full agent with `--hdl vhdl` (stage 0 to 2, luna) wrote VHDL that
  built and talked to the shell but failed every hidden test on register behaviour (for example the RATE register read 0 after
  reset where the spec says 250); both stopped at the stage-2 visit limit. This is the same failure class as luna's
  SystemVerilog runs in brief 42, not a VHDL one. Two further runs with the VHDL skills in the bank (both loaded `vhdl` skills
  repeatedly; `t1_elevator_fsm`, `t1_debounce_bank`) were stopped at 04:20 in long stage-2 simulations; their VHDL built and failed
  every hidden test on the register map (design ID at window 0, reset values), again not a VHDL failure
  ([scores/agentkb_*](scores/)). Stage 2 could not pass that night in either language: its `stage_rtl` gate needs a Vivado build,
  which `run_vivado.sh` refused while other Vivado jobs ran.
- **One block translation fails as written**: the 4-phase handshake (`cdcfx_c8`) in arm A and again in arm B, on 'U' at time 0
  (mistake M2). The rule was in arm B's prompt; the model translated literally anyway.
- Code coverage of VHDL is not available (GHDL's mcode back end has none). UVVM was not run.

## The translation table

The model translated each drill's SystemVerilog reference into VHDL-2008 ([tools/vhdl_translate.py](../../tools/vhdl_translate.py)):
it saw the spec, the SystemVerilog and the boundary notes (arm A), plus three knowledge-bank VHDL skills (arm B); its only feedback
was GHDL lint. It never saw a bench. Scoring: the unchanged hidden benches through the GHDL netlist
([flow/vhdl_score.py](../../flow/vhdl_score.py)); the block drills under GHDL natively with their original cocotb tests
([tools/vhdl_block_checks.py](../../tools/vhdl_block_checks.py)); Vivado 2026.1 builds of the SystemVerilog reference and the VHDL on
the same day with the same XDC ([tools/vhdl_pair_build.py](../../tools/vhdl_pair_build.py)).

| Drill | Area | Arm A (no skills) | Arm B (notes + skills) | Vivado 2026.1, SystemVerilog reference | Vivado 2026.1, VHDL (board drills: arm B; blocks: arm A, c8 arm B) |
|---|---|---|---|---|---|
| `t1_gray_stepper` | T1 | FAIL (does not build) | PASS 9/9 | pass; 448 LUT / 386 FF; WNS +3.544 ns | pass; 442 LUT / 386 FF; WNS +3.191 ns |
| `t1_elevator_fsm` | FSM | FAIL (does not build) | PASS 9/9 | pass; 393 LUT / 343 FF; WNS +3.768 ns | pass; 379 LUT / 343 FF; WNS +3.893 ns |
| `d24_registered_outputs` | FSM drill (brief 24) | FAIL (does not build) | PASS 3/3 | pass; 387 LUT / 312 FF; WNS +4.268 ns | pass; 380 LUT / 312 FF; WNS +4.018 ns |
| `t1_sync_fifo_regs` | memory (FIFO) | FAIL (does not build) | PASS 9/9 | pass; 379 LUT / 294 FF; WNS +3.953 ns | pass; 372 LUT / 294 FF; WNS +4.117 ns |
| `t1_debounce_bank` | T1, asynchronous inputs | FAIL (does not build) | PASS 9/9 | pass; 678 LUT / 872 FF; WNS +4.131 ns | pass; 682 LUT / 872 FF; WNS +2.931 ns |
| `cdcfx_c10` | CDC (async FIFO) | PASS | not run | 34 LUT / 56 FF; WNS -0.81; CDC gate pass | 34 LUT / 56 FF; WNS -0.81; CDC gate pass |
| `cdcfx_c8` | CDC (handshake) | FAIL | FAIL | 4 LUT / 40 FF; WNS -0.101; CDC gate pass | 4 LUT / 40 FF; WNS -0.101; CDC gate pass |
| `axil_regs` | AXI4-Lite slave | PASS | not run | 57 LUT / 174 FF; WNS 1.012 | 85 LUT / 174 FF; WNS 1.012 |

Board drills: "pass" = every gate of `flow/gates.py` passed through the bitstream (base variant). Flip-flops are equal in every pair;
LUTs within 14 of the reference on the board drills (VHDL fewer in four of five); worst slack within 1.2 ns, both directions. The
brief 24 drill's pin grader ([drill_grades/d24_registered_outputs.json](drill_grades/d24_registered_outputs.json)) gives the same
verdict for both: all eight JB outputs flop-driven, lag 1 ("registered decode of the state"). Block drills are out-of-context
synthesis only ([blocks.json](blocks.json)); the negative slack of the two CDC fixtures is the same in both languages (the fixture
constrains only its crossings). The AXI4-Lite slave used 28 more LUTs in VHDL with the same flops and slack; the cause was not
investigated. The hand-fixed handshake (start values on its two output registers only,
[translations/hand_fix](translations/hand_fix/cdcfx_c8/NOTE.md)) passes its test and the CDC gate.

Design standards (`flow/standards_check.py`, read from the GHDL netlist for VHDL): the same result as the reference except
`t1_gray_stepper`, whose VHDL names its synchroniser `sync2_vh`, which the generated architecture's crossing list (written for
`sync2`) does not recognise (STD-CDC-01); the `d24_registered_outputs` and `t1_sync_fifo_regs` references fail STD-CDC-01 too, for the same reason as their translations.

## The board run

[board/t1_gray_stepper__vhdl.json](board/t1_gray_stepper__vhdl.json): the VHDL gray stepper on the Nexys A7-100T, SRAM only,
programmed by cable serial; power check, identify (DESIGN_ID and BUILD_STAMP), the task's self-check over the UART shell and
still-alive all passed. Conditions over JTAG before and after, including the XADC's min/max registers since configuration: die
24.98 to 28.05 C, VCCINT 1.0042 to 1.0078 V, VCCAUX 1.7812 to 1.7966 V, VCCBRAM 1.0042 to 1.0078 V, alarm flags 0000: **inside the
recommended operating conditions** (Artix-7 -1) and the board's 85 C limit. The XADC cannot see nanosecond droop.

## Mutation on VHDL

[mutation_t1_sync_fifo_regs_vhdl.json](mutation_t1_sync_fifo_regs_vhdl.json): `flow/mutate.py` on the VHDL FIFO with the task's
development bench as the design's test (host, a demonstration of the VHDL operators, not a V3 result): 5 sampled mutants, 4 killed,
1 survived (`push_i = '1'` to `'0'` in the write condition: the survivor was not analysed).

## The model's VHDL mistakes and the rules they produced

| # | Where | Mistake | Rule (where it lives now) |
|---|---|---|---|
| M1 | arm A, 5 of 5 board drills | re-wrote the shell's `sync2`/`reset_sync` as VHDL entities of the same names | no VHDL entity may take a shell module's name; use the shell's module through a component or rename (`vhdl-mixed-language-boundary`; the lint refuses it; boundary notes) |
| M2 | arms A and B, `cdcfx_c8` | output registers with no reset and no start value: 'U' until the first edge, where Verilog's X-to-1 posedge hid it | give a start value to every register a test may read early (`vhdl-types-drivers-and-numeric-std`, `vhdl-ghdl-and-xsim`; boundary notes) |
| M3 | end-to-end agent run | its cocotb bench passed `BUILD_STAMP=0` (an integer) to a `std_logic_vector(31 downto 0)` generic; GHDL 4.1 synthesis crashed with an internal error; 7 simulate calls were lost to it | the flow converts such values (`flow/vhdl.py` `fit_generics`) and names the crash; generic values must suit the type (`vhdl-records-arrays-generics-generate`) |
| M4 | hand fix of M2 | moving output registers to internal signals renamed `dout_reg` to `dout_r_reg`; the fixture's XDC (`get_cells {dout_reg[*]}`) then matched nothing and Vivado stopped | constraints that name cells tie a translation to the original's signal names: keep them (`vhdl-mixed-language-boundary`, "Translating from SystemVerilog") |

M3 and M4 are not model VHDL style errors as such: M3 is a GHDL crash on a value a SystemVerilog-minded bench passes, M4 was ours.
Two flow defects were found and fixed on the way: the lint fed back the tail of GHDL's output (a cascade could hide the first
error), and the standards checker read a VHDL signal with an initial value as a derived clock (GHDL writes it as
`always @* x = y`).

## Cost

Translations: 14 runs, $0.0325 provider-reported. Agent runs: $0.2528 and $0.1558 (two full runs), two runs stopped at start with
no cost recorded, and the two runs with the VHDL skills $0.165 and $0.0812 (finished roles). Total $0.6873 provider-reported against the $10 cap. Ledger: [../spend_ledger.csv](../spend_ledger.csv).
