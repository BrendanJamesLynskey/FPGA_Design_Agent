# Brief 24: FSMs as an area of expertise, measurements

Vivado 2025.2 (default), Icarus 12, Verilator 5.020 and 5.048, xsim 2025.2, SymbiYosys with z3. No board. One reference controller
(`flow/tests/fixtures/fsm_discipline`, [docs/fsm.md](../../docs/fsm.md)): 11 states and a 4-bit counter, or the same behaviour as 23 states.
The two forms are cycle-equivalent under 40,000 clocks of random inputs and resets (`equivalence.txt`).

## Nulls and surprises first

- **Folding the counter into the states was not worse.** 23 states without a counter: 23 LUT / 5 FF, 317 MHz estimate; 11 states with a counter:
  31 LUT / 8 FF, 285 MHz. Separation is for the reader, the spec table (11 rows, 13 transitions against 39) and the proof, not for area or speed.
- **`-fsm_extraction auto` did not extract the 23-state machine on xc7a100t**, but made it one-hot (23 flops) on xc7z020 and xck26 (`families/`).
- **Asynchronous against synchronous reset made no difference** to LUTs, flops or the estimated Fmax; the reset that is gated by the enable
  loses the reset (below).
- **The invariant did not shorten the induction**: with the counter's range invariants the proof closed at depth 5, as the folded machine did,
  and took about 10 s against 0.4 s (`formal.json`).
- **A `cover property` written `a |=> b` counts vacuous passes** on Verilator 5.048 (`simprobe/survey.txt`).
- Synthesis numbers are estimates with unplaced wire delay: the output paths at 2.5 ns are dominated by it. Where routed numbers exist
  they are in `impl_table.md` and `io_table.md`; where they do not, the tables say synthesis.

## Files

| File | What |
|---|---|
| `synth_table.md`, `synth_table.json`, `synth/*.kv` | every variant, synthesis only, xc7a100tcsg324-1 at 2.5 ns: separation, outputs, inputs, encoding, reset, reset with an enable, enable ratio, input from another clock |
| `families/xc7z020`, `families/xck26` | eight variants each on the Zynq-7000 PL and the K26 PL (UltraScale+): same counts, different auto extraction |
| `cdc_in0.cdc.json` ... | brief 16's CDC gate on an input from another clock: used directly (12 endpoints, unsafe U2), one register (unsafe U2), two ASYNC_REG (synchroniser) |
| `latency.txt` | clocks from input to output for combinational, registered and lookahead outputs |
| `reset_with_enable.txt` | a one-clock reset at each phase of a one-in-four enable |
| `equivalence.txt` | separated and monolithic, registered and lookahead against combinational, 40,000 clocks |
| `formal.json`, `run_formal.py` | SymbiYosys: bounded depth 40, cover, k-induction at depths 1 to 6, separated and monolithic |
| `simprobe/` | what Icarus, Verilator (two versions) and xsim give for covergroups, cover properties, code coverage |
| `coverage/` | the FSM coverage check on the I2C engine, the flash reader and the reference controller, each with one test removed |
| `impl_table.md`, `io_table.md` | routed numbers (see the report for what was run) |

Reproduce: `flow/tests/fixtures/fsm_discipline/run_all.sh <dir> 0`, `make_table.py`, `run_io.sh`, `make_coverage.py`, `run_formal.py`,
`simprobe/run_probe.sh`. Tests: `flow/tests/test_24_*.py`.
