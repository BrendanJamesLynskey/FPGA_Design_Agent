# The assurance switch: optional post-synthesis verification and reliability structures (brief 194)

Owner, 2026-11-23: "Are we including (optionally) post-synthesis verification? Things like this could be enabled via a switch, read
by the agent. The switch might cover other time-expensive items, which enhance (for example) reliability. This might lead to
structures being added like ECC, triple-redundancy voting, etc."

This page is the design note, written before the code. Measured results are added to it in the "Results" section as the runs finish
(every number there names its record under [results/b194](../results/b194/)).

## What exists today (checked 2026-11-23, not assumed)

| Piece | State |
|---|---|
| `eqy_check` ([agent/core/oss_tools.py](../agent/core/oss_tools.py), [flow/eqy_gate.py](../flow/eqy_gate.py)) | proves a netlist equivalent to the RTL (Yosys netlist, Vivado `write_verilog -mode funcsim`, RapidWright). A tool the agent may call; no role is offered it and no stage runs it. Gate `post_synth_oss_netlist_equivalent` fails only a build that already has an `oss_netlists/` directory. Primitives the suite's `cells_sim.v` does not model (RAMB, DSP48, GT, clocking) make a netlist `ERROR`, never a pass |
| Simulation sets | [project_mode_parity.md](project_mode_parity.md), row "Simulation sets": RTL simulation only (Icarus, Verilator, cocotb, xsim for portability). No post-synthesis or post-implementation simulation |
| `netlist_synth.v` | [arithmetic_pareto_plan.md](arithmetic_pareto_plan.md) uses the post-synthesis netlist of a block as the object that eqy compares; nothing runs a bench on it |
| Reliability structures | none: no ECC, TMR, safe-state FSM, parity or soft-error-mitigation support in the flow or the interview |
| Config | `spec.yaml` has no assurance field; `agent run` has no flag for it |

## The switch

One setting, three levels. It lives in `spec.yaml` as `assurance: standard | thorough | high_reliability` (the field the interview
fills) and in the run config as `agent run ... --assurance <level>` (the command line overrides the spec for that run; the level that
was used is recorded in the run summary). Levels are cumulative: each level contains the one before it. The default is `standard`, so
nothing changes for a run that does not mention it.

| Level | Adds | Cost | Changes the design? |
|---|---|---|---|
| `standard` | RTL verification as today (V0 to V3, mutation, the independent spec bench) | the baseline | no |
| `thorough` | (1) **post-synthesis functional simulation**: the design's own functional bench re-run on Vivado's `write_verilog -mode funcsim` netlist; (2) **formal equivalence** RTL against the synthesised netlist with `eqy`, as a gate where the netlist's primitives are modelled, and a recorded `unsupported` where they are not; (3) **seed sweep**: the randomised benches repeated over a set of seeds (default 8); (4) **longer formal depths** (bounded depth multiplied by 4 where the design has a formal bench); (5) **post-route timing simulation** (`write_verilog -mode timesim` plus SDF) only when the design is marked `timing_sim: true` in the spec (asynchronous or multi-clock behaviour) | minutes to tens of minutes of wall time, one or two extra Vivado runs, no extra area | no |
| `high_reliability` | everything in `thorough`, plus **structures chosen with the user**: ECC on memories, parity on internal buses, safe-state FSM encoding, TMR on chosen registers, watchdog, and a fault-injection simulation that shows what each structure catches | area, Fmax and latency, each measured (table in Results); extra verification time | yes, only where the user accepted the stated cost |

### What a user could guess wrong

- **`thorough` is not "more RTL tests".** It checks the tool's output (the netlist), not the RTL. A pass says synthesis did not change
  the function; it says nothing new about the spec.
- **The funcsim netlist has no timing.** `-mode funcsim` is zero delay. Timing faults appear only in the optional `timesim` run.
- **eqy proves the netlist text it is given.** A netlist containing a block RAM, a DSP48 or a clocking primitive is `unsupported`
  (reported as such, never as a pass). Equivalence is therefore run on the logic without the memory, and the memory is covered by the
  netlist simulation instead. This split is stated in every result.
- **`timesim` on the free Vivado tier.** The Basic simulator refuses designs above 50,000 instances; a design over the cap gets
  `timing_sim: skipped (instance cap)`, not a pass.
- **ECC does not fix a stuck-at or a wrong write.** It corrects one flipped bit per word and detects two. Inputs that are wrong before
  the write are stored faithfully with a correct code.
- **Built-in block RAM ECC corrects the output, not the array** (UG473 ch. 3 "Built-in Error Correction": the corrected value is on
  `DO`; the stored word keeps its error). A word read twice is corrected twice; a second flip in the same word before a rewrite makes it
  a double error. A design that wants scrubbing must write the corrected value back.
- **TMR only helps if the copies survive.** Vivado merges registers with identical inputs unless told not to; the copies carry
  `DONT_TOUCH` (UG901 ch. 2 "DONT_TOUCH", forwarded to place and route), and the flow checks the post-implementation netlist for all
  three copies (a result of "3 copies found" is a measurement, not an assumption).
- **TMR does not protect the voter, the clock or the inputs.** A fault in the voter output register shows as one wrong cycle.
- **`fsm_safe_state` only acts on an FSM that synthesis extracted** (UG901 ch. 3 "FSM_SAFE_STATE"). `fsm_encoding = none` removes it.
- **Configuration-memory upsets** (LUT contents, routing) are not fixed by any of these; the soft-error-mitigation core does that (below).
- **Single-event faults in simulation are modelled bit flips**, not particle physics. The fault-injection table says what the structures
  catch against that model; it is not a failure-rate figure.

## What `high_reliability` can add, and what we checked first

| Structure | Approach (AMD guidance first) | Where it is checked |
|---|---|---|
| ECC on block RAM | the primitive's built-in ECC (RAMB36E1 simple dual port, 512 x 64 data + 8 check bits, `EN_ECC_READ`/`EN_ECC_WRITE`, `SBITERR`/`DBITERR`: UG473 ch. 3). Where the primitive does not fit (width, UltraRAM, a family without it), a fabric SECDED code (Hamming(72,64) with an overall parity bit) | fault injection in xsim (primitive: `INJECTSBITERR`/`INJECTDBITERR` at write, UG473 table "Block RAM ECC port names"); fabric: bit flips in the array in Icarus; area and Fmax OOC |
| Parity or CRC on internal buses | one even-parity bit per 64-bit word across a pipeline register; a sticky error flag. CRC where a burst error model matters (not built here) | fault injection |
| Safe-state FSM | `(* fsm_safe_state = "auto_safe_state" *)` on the state register (UG901 ch. 3 "FSM_SAFE_STATE"; skill `artix7-safe-fsm-and-seu`). The measured effect on the netlist is recorded, because the skill marks the interaction with extraction as unconfirmed | synthesis log and utilisation; fault injection |
| TMR with voters | three copies of a register group, a bitwise majority voter, the voted value fed back to all three (a flipped copy is repaired on the next clock), `DONT_TOUCH` on the copies and voter | post-implementation netlist check that three registers per bit exist; fault injection |
| Watchdog | a counter that must be kicked by the control path; expiry forces the FSM to its reset state and sets a sticky flag | fault injection (hang case) |
| Configuration-memory soft errors | the 7-series SEM IP (PG036; UltraScale and UltraScale+ use PG187) built on readback CRC and ECC of configuration frames (UG470 ch. 8). **Not assumed available:** whether our licence tier generates it is checked in this brief and recorded; if it cannot be generated, the interview says so and offers readback CRC (`POST_CRC`, a bitstream option) only | licence check in Results |

The interview asks which blocks need each structure, and the agent states the measured cost (area, Fmax, latency, from the table in
Results for that structure on the same family) before applying it. A block the user does not name is not changed.

## How the agent reads the switch

1. **Clarify (stage 0).** If the level is not set, one question with a proposed default (`standard`) and its reason. At `thorough`: one
   question only if the spec has more than one clock (asks whether to run `timesim`). At `high_reliability`: one question per candidate
   block class found in the spec (memories, state machines, counters and registers that must not corrupt, internal buses), each with
   the measured cost as its reason and a default of "protect" for memories and FSMs and "do not protect" otherwise.
2. **Plan.** `agent/graph/assurance.py` turns the level and the answers into a plan: the flow checks enabled and the structures to add.
3. **Flow.** `flow/assurance.py` runs the enabled checks (funcsim netlist, bench re-run, eqy, seed sweep, timesim) and writes
   `assurance.json` in the build directory.
4. **Run summary.** The summary carries `assurance`: the level, the plan, each check's status and wall time, and an advisory line
   ("thorough adds N minutes; high_reliability costs X % area ..."), so the user sees what the switch bought.

## Development design and method

`designs/b194_assurance/` (a development design, not a held-out task): a burst sequencer (a five-state FSM with three unused codes),
a 512 x 64 FIFO on block RAM, a pipeline register with an accumulating checksum, and a 16-bit remaining-words counter. Variants by
parameter: `u` (none), `ecc`, `par`, `safe`, `tmr`, `all`. Cost is measured OOC on Vivado 2026.1, one run each, `xc7a100tcsg324-1`
(the run's own clock search is not used: a fixed 5.0 ns constraint, then Fmax estimated from WNS at that constraint, stated as such).
Fault injection: seeded single bit flips at random cycles in the state register, the RAM words, the protected counter copies and the
bus register, over a fixed workload, classified per trial as masked, corrected, detected, silent corruption or hang.

## Results

(filled in as the runs complete)
