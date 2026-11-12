# VHDL designs: what was measured

**Result.** A model's first VHDL translations failed all five board tasks on one naming mistake. With that mistake written into
its guidance, all five passed the same hidden tests and Vivado 2026.1 gates as the SystemVerilog references, within 14 LUTs of
them, and one ran on the board. The end-to-end agent writing VHDL from the spec passed 0 of 4 runs. One of three block designs
still fails as translated.

How the flow handles VHDL is in [docs/vhdl.md](../../docs/vhdl.md). Every number here comes from a file in this directory.

Terms used below:

- **Model:** openai/gpt-6-luna, a low-cost model on OpenRouter (`data_collection: deny`), called "luna" in the project.
- **Task:** a development task of the benchmark (never a held-out one). A **board task** has a spec, a reference design in
  SystemVerilog and a **hidden test**: a cocotb test bench the design's author never sees, run through the board pins and the
  UART test shell against a Python model. "T1" is the benchmark's first tier (small single-function designs).
- **Block design:** a module without the shell: two clock-domain-crossing (CDC) fixtures and an AXI4-Lite slave. They are scored
  by their own test benches and out-of-context synthesis only, not by hidden tests or the full gates.
- **Arm A:** the model saw the spec, the SystemVerilog and the flow's notes on the VHDL boundary. **Arm B:** the same, plus notes
  amended from arm A's mistakes and three of the knowledge bank's VHDL skills. Arm B was made after arm A's mistakes were known,
  so it is exploratory, not a pre-registered confirmation ([plan and its timing](prereg.md)).

Tools: GHDL 4.1.0, Icarus 12, cocotb 2.0.1, Vivado 2026.1.

## Nulls first

- **Arm A: 0 of 5 board tasks.** All five failed for one reason (mistake M1, below): the model re-wrote the shell's helper modules
  `sync2` and `reset_sync` as VHDL entities of the same names, which clash with the shell's SystemVerilog modules. With only that
  clash renamed by a script (a diagnostic, never counted), all five passed ([scores/Adiag_*](scores/)).
- **The end-to-end agent: 0 of 4.** The agent writes the spec file, the plan, a model, tests and the RTL itself; it never sees the
  reference ([agent_runs/](agent_runs/)).
  - Two runs without the VHDL skills ended at the stage-2 visit limit (the stage that writes and verifies the RTL). Their VHDL
    built and talked to the shell, then failed every hidden test on register behaviour (for example a rate register read 0 after
    reset where the spec says 250). The same model's SystemVerilog runs fail the same way.
  - Two runs with the VHDL skills in the bank (each called `load_skill` 17 to 22 times, the `vhdl` section among them) were stopped by the executor in long stage-2
    simulations. Their VHDL also built and failed every hidden test on the register map (the design ID at register 0, reset
    values).
  - Separately, stage 2 could not end with a pass in either language while other Vivado jobs ran on the build machine: its exit
    needs a Vivado elaboration (`stage_rtl`), which the build runner refused while two Vivado jobs were already running.
- **One block fails as written:** the 4-phase handshake (`cdcfx_c8`) in both arms, on 'U' at time 0 (mistake M2). The rule was in
  arm B's prompt; the model translated literally anyway.
- No code coverage for VHDL (GHDL's mcode back end has none). UVVM was not run.

## The translation table

The model translated each task's SystemVerilog reference into VHDL-2008 ([tools/vhdl_translate.py](../../tools/vhdl_translate.py));
its only feedback was GHDL lint, and it never saw a test. Scoring: the unchanged hidden tests through the GHDL netlist
([flow/vhdl_score.py](../../flow/vhdl_score.py)); the blocks natively under GHDL with their own cocotb tests
([tools/vhdl_block_checks.py](../../tools/vhdl_block_checks.py)); Vivado 2026.1 builds of the reference and the VHDL with the same
constraints ([tools/vhdl_pair_build.py](../../tools/vhdl_pair_build.py)).

| Task | Area | Arm A | Arm B | Vivado 2026.1, SystemVerilog reference | Vivado 2026.1, VHDL |
|---|---|---|---|---|---|
| `t1_gray_stepper` | T1 | FAIL (does not build) | PASS 9/9 | pass; 448 LUT / 386 FF; WNS +3.544 ns | pass; 442 LUT / 386 FF; WNS +3.191 ns |
| `t1_elevator_fsm` | FSM | FAIL (does not build) | PASS 9/9 | pass; 393 LUT / 343 FF; WNS +3.768 ns | pass; 379 LUT / 343 FF; WNS +3.893 ns |
| `d24_registered_outputs` | FSM drill (registered outputs) | FAIL (does not build) | PASS 3/3 | pass; 387 LUT / 312 FF; WNS +4.268 ns | pass; 380 LUT / 312 FF; WNS +4.018 ns |
| `t1_sync_fifo_regs` | memory (FIFO) | FAIL (does not build) | PASS 9/9 | pass; 379 LUT / 294 FF; WNS +3.953 ns | pass; 372 LUT / 294 FF; WNS +4.117 ns |
| `t1_debounce_bank` | T1, asynchronous inputs | FAIL (does not build) | PASS 9/9 | pass; 678 LUT / 872 FF; WNS +4.131 ns | pass; 682 LUT / 872 FF; WNS +2.931 ns |
| `cdcfx_c10` | CDC (async FIFO), block | PASS | not run | 34 LUT / 56 FF; WNS -0.81; CDC gate pass | 34 LUT / 56 FF; WNS -0.81; CDC gate pass |
| `cdcfx_c8` | CDC (handshake), block | FAIL | FAIL | 4 LUT / 40 FF; WNS -0.101; CDC gate pass | 4 LUT / 40 FF; WNS -0.101; CDC gate pass |
| `axil_regs` | AXI4-Lite slave, block | PASS | not run | 57 LUT / 174 FF; WNS 1.012 | 85 LUT / 174 FF; WNS 1.012 |

The last column is arm B for the board tasks and `cdcfx_c8`, arm A for `cdcfx_c10` and `axil_regs` (arm B ran only where arm A
failed). WNS is the worst setup slack.

**Board tasks.** "pass" means every gate of `flow/gates.py` passed, through the bitstream. Flip-flops are equal in every pair.
LUTs are within 14 of the reference, and the VHDL is smaller in four of five. Slack is within 1.2 ns either way. The registered-
outputs drill's pin grader ([drill_grades](drill_grades/d24_registered_outputs.json)) gives both languages the same verdict: all
eight output pins flop-driven, one clock behind the state table.

**Block designs.** Out-of-context synthesis only ([blocks.json](blocks.json)). The two CDC fixtures have the same negative slack in
both languages (the fixture constrains only its crossings), and both pass the flow's structural CDC check. The AXI4-Lite slave
takes 28 more LUTs in VHDL, with the same flip-flops and slack; the cause was not investigated. The hand-fixed handshake (start
values on its two output ports only, [hand_fix](translations/hand_fix/cdcfx_c8/NOTE.md)) passes its test and the CDC check.

**Design standards** (`flow/standards_check.py`; for VHDL it reads the GHDL netlist). The rule STD-CDC-01 checks that every
crossing the design's `architecture.yaml` lists is instantiated. The `architecture.yaml` used for these builds is generated, and
it names the shell's `sync2` for each asynchronous input. That is why the rule fails for:

- the `d24_registered_outputs` and `t1_sync_fifo_regs` references and their translations, which synchronise those inputs
  without `sync2`;
- the `t1_gray_stepper` translation, which names its synchroniser `sync2_vh`.

Every other rule passes on both sides.

**Provenance.** The Vivado builds and the board run used a working tree at commit `c3885a0` with uncommitted changes (the
board record says `git_dirty: true`). The RTL, constraints and flow files they read are the ones committed here. The
standards fields in `vivado/*.json` were re-derived afterwards with the final checker. That step is simulation-only, and it
changed nothing.

## The board run

[board/t1_gray_stepper__vhdl.json](board/t1_gray_stepper__vhdl.json): the VHDL gray stepper on the Nexys A7-100T, programmed into
SRAM over JTAG by cable serial. The power check, identify (design ID and the build stamp the VHDL generic received), the task's
self-check over the UART shell and still-alive all passed.

Operating conditions were read over JTAG before and after, including the XADC's min/max registers since configuration:

- die temperature 24.98 to 28.05 C;
- VCCINT 1.0042 to 1.0078 V, VCCAUX 1.7812 to 1.7966 V, VCCBRAM 1.0042 to 1.0078 V;
- alarm flags 0000.

That is **inside the recommended operating conditions** (Artix-7, -1 speed grade) and the board's 85 C limit. The XADC samples
at about 1 MSPS and cannot see nanosecond droop.

## Mutation on VHDL

`flow/mutate.py` changes one operator at a time in the RTL and checks that the design's own tests fail.

- [mutation_cdcfx_c10_vhdl_container.json](mutation_cdcfx_c10_vhdl_container.json): the VHDL async FIFO in the sandbox container
  (`fda-sim:2-ghdl`), simulated natively by GHDL, with the fixture's own test copied into the design
  ([mutation_design](mutation_design/)). 12 mutants: 10 killed, 2 timed out (the simulation hung), 0 invalid.
- [mutation_t1_sync_fifo_regs_vhdl.json](mutation_t1_sync_fifo_regs_vhdl.json): an earlier run on the host with a task's test
  as the design's test: 5 mutants, 4 killed, 1 survived (`push_i = '1'` to `'0'`; not analysed).

Both are demonstrations of the VHDL operators, not a verification-stage result. The container run was added after a review
found that the VHDL compile check failed inside the container (fixed: its work library now sits in the mounted design tree).

## The model's VHDL mistakes and the rules they produced

| # | Where | Mistake | Rule (where it lives now) |
|---|---|---|---|
| M1 | arm A, 5 of 5 board tasks | re-wrote the shell's `sync2`/`reset_sync` as VHDL entities of the same names | no VHDL entity may take a shell module's name; use the shell's module through a component, or rename (KB skill `vhdl-mixed-language-boundary`; the lint refuses it; the flow's boundary notes) |
| M2 | arms A and B, `cdcfx_c8` | output registers with no reset and no start value: 'U' until the first clock edge, which Verilog's X-to-1 edge at time 0 had hidden | give a start value to every register a test may read early (`vhdl-types-drivers-and-numeric-std`, `vhdl-ghdl-and-xsim`; boundary notes) |
| M3 | end-to-end agent run | its test passed `BUILD_STAMP=0` (an integer) to a `std_logic_vector(31 downto 0)` generic; GHDL 4.1 synthesis crashed with an internal error, and 7 simulation calls were lost to it | the flow converts such values and names the crash (`flow/vhdl.py` `fit_generics`, also in the lint); generic values must suit the type (`vhdl-records-arrays-generics-generate`) |
| M4 | our own first hand fix of M2 | moving output registers into internal signals renamed `dout_reg`; the fixture's constraints (`get_cells {dout_reg[*]}`) then matched nothing and Vivado stopped | constraints that name cells tie a translation to the original's signal names: keep them (`vhdl-mixed-language-boundary`, "Translating from SystemVerilog") |

M3 is a GHDL crash on a value a SystemVerilog-minded test passes, and M4 was ours, so neither is a VHDL style error by the model.
Defects in the flow found on the way, all fixed:

- the lint fed back the end of GHDL's output, so a cascade could hide the first error;
- the standards checker read a VHDL signal with an initial value as a derived clock (GHDL writes it as `always @* x = y`);
- the lint let any unbound component pass, not only the shell;
- the VHDL compile check of the mutation tool failed inside the sandbox container.

## Cost

Provider-reported, $0.6873 in total ([../spend_ledger.csv](../spend_ledger.csv)):

- translations: 14 runs, $0.0325;
- the four end-to-end agent runs: $0.2528, $0.1558, $0.165 and $0.0812 (the last two counted for their finished roles only).

Two further agent launches were stopped within a minute of starting because they pointed at the wrong knowledge-bank path. No
model role finished in them, and they are not counted as runs.
