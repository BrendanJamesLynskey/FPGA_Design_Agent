# Brief 24: FSMs as an area of expertise, measurements

Measured on 2025.2. The controller variants (synthesis and routed) are superseded by `results/24_fsm_2026_1`; the I/O study, the family runs, the drills and the simulator survey were not re-run; the simulator survey is repeated in `results/24_fsm_2026_1/simprobe/`.
Still current: `drills/`, `coverage/`, `equivalence.txt`, `formal.json` (agent runs, simulations and proofs; no Vivado).

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
| `drills/` | the drill references graded on their routed checkpoints, run A1 graded, run B1 interim (below), `PREREG.md` |
| `impl_table.md`, `impl/` | routed numbers (opt, place, route) for the main variants, out of context |
| `io_table.md`, `io/` | the controller on real pins, routed: what drives each pad, whether the flop is in the I/O block, clock-to-pad |
| `summary.json`, `make_summary.py` | the numbers the site's FSM drawer quotes |

Reproduce: `flow/tests/fixtures/fsm_discipline/run_all.sh <dir> 0`, `make_table.py`, `run_io.sh`, `make_coverage.py`, `run_formal.py`,
`simprobe/run_probe.sh`. Tests: `flow/tests/test_24_*.py`.

## Drill runs (development arm, no brief 24 skills in the pinned bank)

Pre-registration: `drills/PREREG.md` (3 seeds a drill planned). **Run: 1 seed of the first drill, 1 of the second, the second not finished.** Each run holds the
heavy slot for its whole length (about an hour when it goes well), so three seeds each was not possible in the session.

| Run | Drill | Result | What the design chose |
|---|---|---|---|
| A1 `20261111-063438-bc8f` | `d24_registered_outputs` | **pass**: hidden bench 3/3, lag 1, all 8 JB pins flop-driven in the routed checkpoint (`drills/run_a1.json`); 61 min, plan estimate $3.1, reached V2 | registered decode of the state (one clock late); 11-state enum (extracted sequential) with a separate 3-bit counter; its own tests include the timeout |
| B1 `20261111-073532-07cd` | `d24_no_extra_latency` | **not complete**: still in stage 2 after 2 h because three of its `simulate` calls timed out at 1800 s (unbounded `while` waits in its own cocotb bench). The RTL it had written passes the hidden bench (lag 0), graded interim (`drills/run_b1_interim.json`) | combinational Moore decode with a Mealy `cmd_ack` (the right choice; it did not register the outputs) |

Both references: `reference_d24_*.json` (hidden bench passes, mutants killed, routed through `ref_build.py`: WNS +4.24 and +3.54 ns, the grader reads the pin drivers: all flops for the first, all LUTs for the second).
One seed each says nothing about a rate; it says the drills are gradeable and that the agent without the new skills picked the registered decode when the spec said flip-flops and the
combinational/Mealy form when the spec said no added latency.

## Reproduce

The commands are the `Reproduce:` line above. The controller variants need Vivado and a heavy slot (superseded: use
`results/24_fsm_2026_1`); `make_coverage.py`, `run_formal.py` (SymbiYosys with z3), `equivalence.txt` and `simprobe/run_probe.sh`
need no Vivado. The drill runs were paid agent runs and are not regenerated from the repository.

## Known gaps and limits

- The Vivado variant tables are superseded by `results/24_fsm_2026_1`; do not cite their numbers from this folder.
- Drills: one seed of the first drill, one of the second (not finished); three seeds each were planned. They were run without the brief's new skills and say nothing about a rate.
- Routed numbers for encodings, reset styles and the other-clock input were not run (synthesis only); the Zynq-7000 and K26 probes are synthesis only, with no I/O-block flop probe on UltraScale+.
- Formal and latency figures are one run each on a loaded machine; one controller, one tool version.
- The coverage check is evidence only: not an agent tool, not on by default, and the agent does not write `verif/fsm.yaml`; the agent's own V2 coverage was not graded for run A1.
- xsim cover-property hit counts were not found in its report tool.
