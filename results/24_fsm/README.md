# Brief 24: FSMs as an area of expertise, measurements

Vivado 2025.2 (default), Icarus 12, Verilator 5.020 and 5.048, xsim 2025.2, SymbiYosys with z3. No board. One reference controller
(`flow/tests/fixtures/fsm_discipline`, [docs/fsm.md](../../docs/fsm.md)): 11 states and a 4-bit counter, or the same behaviour as 23 states.
The two forms are cycle-equivalent under 40,000 clocks of random inputs and resets (`equivalence.txt`).

## Nulls and surprises first

- **Folding the counter into the states was not worse.** Routed: 23 states without a counter (`auto` made it one-hot) 24 LUT / 23 FF, 310 MHz; with
  `-fsm_extraction sequential` 22 LUT / 5 FF (synthesis); 11 states with a counter 29 LUT / 8 FF, 264 MHz. Separation is for the reader, the spec table
  (11 rows, 13 transitions against 39) and the proof, not for area or speed.
- **A correction made during the brief.** The first synthesis batch of the monolithic variants used a version whose wait states were stepped with
  `st + 1`; under `auto` Vivado did not extract it (5 flops, no Synth 8-802 line), which looked like a difference from xc7z020 and xck26 (one-hot).
  It was the RTL: with an explicit arm per state the same machine is extracted as one-hot on all three parts. The batch was re-run on the final RTL
  and the family row was dropped. The `st + 1` form itself was seen once and not re-measured.
- **Asynchronous against synchronous reset made no difference** to LUTs, flops or the estimated Fmax; the reset that is gated by the enable loses the reset.
- **The invariant did not shorten the induction**: with the counter's range invariants the proof closed at depth 5, as the folded machine did, and
  took about 10 s against 0.4 s (`formal.json`).
- **A `cover property` written `a |=> b` counts vacuous passes** on Verilator 5.048 (`simprobe/survey.txt`).
- **Vivado did not pack registered outputs into the I/O block by itself**: 0 of 8 output flops in OLOGIC without `IOB = TRUE`, 8 of 8 with it (`io_table.md`).
- Synthesis-only numbers carry unplaced wire delay (`synth_table.md`); the routed ones are in `impl_table.md` and `io_table.md`. The routed runs are out of
  context for the FSM variants and on real pins for the I/O study.

## Files

| File | What |
|---|---|
| `synth_table.md`, `synth_table.json`, `synth/*.kv` | every variant, synthesis only, xc7a100tcsg324-1 at 2.5 ns: separation, outputs, inputs, encoding, reset, reset with an enable, enable ratio, input from another clock |
| `families/xc7z020`, `families/xck26` | eight variants each on the Zynq-7000 PL and the K26 PL (UltraScale+), synthesis only: the same LUT, flop and control-set counts as xc7a100t |
| `cdc_in0.cdc.json` ... | brief 16's CDC gate on an input from another clock: used directly (12 endpoints, unsafe U2), one register (unsafe U2), two ASYNC_REG (synchroniser) |
| `latency.txt` | clocks from input to output for combinational, registered and lookahead outputs |
| `reset_with_enable.txt` | a one-clock reset at each phase of a one-in-four enable |
| `equivalence.txt` | separated and monolithic, registered and lookahead against combinational, 40,000 clocks |
| `formal.json`, `run_formal.py` | SymbiYosys: bounded depth 40, cover, k-induction at depths 1 to 6, separated and monolithic |
| `simprobe/` | what Icarus, Verilator (two versions) and xsim give for covergroups, cover properties, code coverage |
| `coverage/` | the FSM coverage check on the I2C engine, the flash reader and the reference controller, each with one test removed |
| `impl_table.md`, `impl/` | routed numbers (opt, place, route) for the main variants, out of context |
| `io_table.md`, `io/` | the controller on real pins, routed: what drives each pad, whether the flop is in the I/O block, clock-to-pad |
| `summary.json`, `make_summary.py` | the numbers the site's FSM drawer quotes |

Reproduce: `flow/tests/fixtures/fsm_discipline/run_all.sh <dir> 0`, `make_table.py`, `run_io.sh`, `make_coverage.py`, `run_formal.py`,
`simprobe/run_probe.sh`. Tests: `flow/tests/test_24_*.py`.
