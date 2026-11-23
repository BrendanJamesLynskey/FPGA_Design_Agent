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

## Verification profiles (the switch, widened by the owner on 2026-11-23)

Owner: "We could more generally enable a level of verification, switching on formal when the agent is configured to use it. We could offer
'profiles': for IP development, we might suggest that full verification is used. We could offer other profiles (which enable X, disable Y) for
other trade-offs between speed and confidence."

A **profile** is a named preset of **switches**; each switch is one verification method or reliability structure with a typed value. Any switch can
be overridden on top of a profile; the run record names the profile and every override (what the profile had, what was used). The registry is
[agent/graph/profiles.py](../agent/graph/profiles.py); the three assurance levels of the first version of this note (`standard`, `thorough`,
`high_reliability`) are now three of the six profiles.

**Command line.** `agent run ... --verif-profile <name> --set <switch>=<value> ...` (repeatable). The existing `--profile` flag is per-role model
routing (brief 05f) and is unchanged, so the verification profile is `--verif-profile` (the brief wrote `--profile`; a clash would have changed
every existing run). **Spec.** `verif_profile:` and `timing_sim: true|false` in `spec.yaml`. **Interview.** With `--interview on|oracle` and no
profile given, one question proposes a profile with a reason and its measured extra time (the default follows words in the spec: "library" or
"reusable IP" gives `ip_release`, "single-event" or "must recover" gives `high_reliability`, "latency budget" gives `low_latency`, "prototype" gives
`prototype`, else `standard`). **Run record.** `summary.json` carries `verification_profile` (profile, overrides, effective switches, switches that
are only recorded, gaps against the method mix and the IP label, an advisory line, policy breaches); `runs/<id>/policy.json` is the pin.

### Switches

`wired` says whether the harness or flow runs the switch today. A switch that is only recorded is listed in the run summary as not run, so a
profile never claims a check that nothing executes.

| Switch | Values | Wired to | Wired |
|---|---|---|---|
| `lint`, `directed_sim`, `random_sim` | on / off | stage 2 lint and simulate gates | yes |
| `verif_level` | V1, V2, V3 | `cfg.verif_level` (was `--verif-level`, now an override of this switch) | yes |
| `coverage_target` | 0-100 | `flow/verif_floors.yaml` (floor 100 at V3) | yes (floor) |
| `mutation_floor` | 0-100 | `flow/verif_floors.yaml` (floor 70 at V3) | yes (floor) |
| `seeds` | 1-64 | `seeds_min` (floor 3 at V3); `flow/assurance.py` seed sweeps | yes |
| `indep_spec_test` | on / off | `cfg.spec_tests` (was `--spec-tests`) | yes |
| `post_synth_sim`, `equivalence`, `timing_sim` (off / auto / on), `fault_injection` | | `flow/assurance.py`, `flow/assurance_profiles.py` | measured here on the development design; not yet a stage of the run |
| `reliability` | none / interview | the interview chooses blocks and structures (`spec.yaml` `reliability`) | interview yes, RTL generation needs a KB prompt (known gap) |
| `board_hil` | off / smoke / full | stage 9 | yes |
| `formal_depth_scale`, `formal_induction`, `formal_pdr`, `lean_proof`, `uvm`, `latency_checks`, `repeats` | | `flow/formal.sh`, `flow/lean_tier.py`, bench briefs 112/123, `flow/latency` | recorded only |

### Profiles

| Profile | Purpose | What it sets (differences from the one above it in the list) |
|---|---|---|
| `prototype` | fastest look at an idea | lint + directed tests, stops at V1; no random tests, coverage, formal, netlist checks |
| `standard` | today's default; nothing changes for a run that names no profile | V3, constrained-random, floors (100 % bins, 70 % mutation, 3 seeds), bounded formal at the design's own depth, board smoke run |
| `thorough` | standard plus the netlist checks | 8 seeds, formal depth x4, functional simulation of the synthesised netlist, `eqy` equivalence, timing simulation where the spec says `timing_sim: true` |
| `ip_release` | what a library IP block needs for its "verified" label (decisions 24, 26) | thorough plus an independent spec bench, mutation floor 85, k-induction and PDR, a pyuvm bench |
| `high_reliability` | designs that must survive single-event upsets | thorough plus the reliability structures the interview chose and fault-injection simulation |
| `low_latency` | designs with a latency budget | standard plus the latency budget checks and the latency-path documentation rule (briefs 84, 189) |

### How profiles relate to what exists (nothing is duplicated; nothing is removed)

- **`--verif-level V1|V2|V3`** stays. It is the switch `verif_level`: a profile sets it, and giving the flag is an override that is recorded as one.
  Default behaviour with no profile and no flag is exactly today's (`standard`, V3).
- **`--spec-tests`** likewise is the switch `indep_spec_test`.
- **V3 floors** (`flow/verif_floors.yaml`): a profile may raise `mutation_floor`, `seeds` and `coverage_target`, and `resolve` refuses a value below the
  floor at V3. The floors stay the minimum; the agent never writes that file.
- **Required method mix** (`flow/method_mix_policy.yaml`, brief 143a, decision 25): decides when a requirement is `verified`. Profiles do not change
  it. `method_mix_gap` lists methods a profile leaves off that the policy names, so the planner can see that `prototype` cannot produce `verified`
  for a safety requirement (it has neither formal nor a board run).
- **IP library label** (VERIFIED.md, decisions 24 and 26, briefs 137-144): the label needs `ip_release` or stronger; `ip_release_ok` returns what a
  profile lacks. The label's own record is written by the library briefs, not here.
- **Brief 189's advisory checks** are `latency_checks` and the netlist-level methods; they stay advisory (`enforced: false`) in every profile.
  *Planner and owner decide before anything is removed:* a later step could retire `--verif-level` in favour of profiles; this brief keeps both.

### The variables, and what the model may decide

[docs/agent_levers.md](agent_levers.md) classifies every input that changes the agent's behaviour as a variable (fixed by the user, pinned for the run,
never changed by the model), LLM judgement, or hybrid (the model proposes, the user pins). The profile and its switches are variables: they are
written to `policy.json` outside the design directory at the start of the run, and any disagreement (a `spec.yaml` naming another profile, a
changed setting) is logged as a policy breach in the run summary while the pin wins.

### Proposed settings, confirmed before the run (owner, 2026-11-23)

Before a run the agent reads the input folder and proposes the variable levers it can read, each with its source and any conflict:
`agent propose <folder>` writes `proposed_settings.yaml` (board, part, speed grade, reference clocks, I/O standards, PHYs, interfaces, suggested
profile). The sources, in order: `board_facts.yaml` (the design-package ingest of brief 174, `flow.package ingest`; **not merged yet, so this reads
the file when it exists and its format is assumed to be a mapping of facts, each plain or `{value, source}`**), the catalogue board named by the
folder, and the spec for the profile. A value nothing in the folder gives is empty with status `ask`; nothing is guessed. The user confirms or edits
every value (`agent settings confirm <file>`, or edit the file and set `status: confirmed`); `agent run --settings <file>` refuses a file with an
unconfirmed or empty value, and refuses a `--board` or `--verif-profile` that disagrees with it. The Navigator's Start page has the same step.

## What the first version of this note proposed for the netlist checks

- **`post_synth_sim`:** the design's own functional bench re-run on Vivado's `write_verilog -mode funcsim` netlist (zero delay, unisims).
- **`equivalence`:** `eqy` RTL against the synthesised netlist, as a gate where the netlist's primitives are modelled; `unsupported` is recorded where they are not.
- **`timing_sim`:** post-route `write_verilog -mode timesim` plus SDF, opt-in per design (asynchronous or multi-clock behaviour); the free simulator refuses more than 50,000 instances.
- **seed sweep and formal depth** as switches of the same profiles.

### What a user could guess wrong

- **The netlist checks are not "more RTL tests".** They check the tool's output. A pass says synthesis did not change the function; nothing new about the spec.
- **The funcsim netlist has no timing.** Timing faults appear only in the optional `timesim` run.
- **eqy proves the netlist text it is given.** A netlist with a block RAM, a DSP48 or a clocking primitive is `ERROR` (reported as unsupported, never as a pass). Equivalence is therefore run on the logic without the memory, and the memory is covered by the netlist simulation instead; every result states the split.
- **ECC does not fix a stuck-at or a wrong write.** It corrects one flipped bit per word and detects two. A word written wrong is stored faithfully with a correct code.
- **Built-in block RAM ECC corrects the output, not the array** (UG473 ch. 3): the stored word keeps its error until it is rewritten, so a second flip makes a double error.
- **TMR only helps if the copies survive**, and it does not protect the voter, the inputs or the clock. Two copies flipped together outvote the good one (measured below).
- **`fsm_safe_state` acts only on an FSM synthesis extracted** (UG901). It is invisible to RTL simulation: the RTL's own default arc is what RTL simulation sees. The netlist is where it shows.
- **The watchdog only watches while the sequencer is busy.** A fault that lands the FSM in idle before the burst is a hang it does not see (measured below).
- **Single-event faults in simulation are modelled bit flips**, not a failure rate.
- **Configuration-memory upsets** (LUT contents, routing) are not fixed by any of these; the soft-error-mitigation core does that (below).
- **A profile's extra time is the time of its checks on the development design, without model time.** It scales with the design and the machine.

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

## How the agent reads the profile

1. **Start.** `agent run` resolves `--verif-profile` and `--set` (an unknown switch, a bad value or a value below a floor stops the command before anything
   runs), pins the result in `policy.json` and records who set it in `build/who_did_what.json`.
2. **Clarify (stage 0).** If no profile was given and the interview is on, one question proposes one (default from the spec's words, reason, expected extra
   time). If the profile asks for structures (`reliability: interview`), one question per block class found in the spec (memories, state machines,
   counters, internal buses) states the measured cost of the structure and proposes "protect" for memories and state machines and "do not protect" for the
   rest. The answers go into `spec.yaml` (`verif_profile`, `reliability`); a block the user does not name is not changed.
3. **Flow.** `flow/assurance.py` and `flow/assurance_profiles.py` run the netlist checks and the cost and fault measurements. They run on the
   development design here; wiring them in as a run stage is the follow-up (a stage needs a gate and a heavy slot).
4. **Run summary.** `verification_profile` in `summary.json`: the profile, every override, the effective switches, the switches that are only recorded,
   the gaps against the method mix and the IP label, an advisory line and any policy breach.

## Development design and method

`designs/b194_assurance/` (a development design, not a held-out task): `a194_ctrl` (a four-state burst sequencer in a 3-bit state register, with the
remaining-words counter and an optional watchdog), `a194_fifo` (512 x 64 on block RAM), and `a194_core` (output register with optional parity, running
checksum, AXI4-Stream handshakes). Variants by parameter: `u` (none), `ecc_fabric` (Hamming(72,64) in LUTs), `ecc_prim` (RAMB36E1 built-in ECC),
`par`, `safe` (`fsm_safe_state = auto_safe_state`), `tmr` (three `DONT_TOUCH` copies of the counter, bitwise voter, voted value fed back), `wd`, `all`
(`ecc_prim` + `par` + `safe` + `tmr` + `wd`). Benches: `tb/tb_func.sv` (ports only: runs on RTL and on netlists), `tb/tb_fault.sv` (RTL, fault
hooks compiled in with `-DA194_FI`; the hooks are constant zero otherwise), `tb/tb_lat.sv` (latency). Cost is measured out of context on Vivado 2026.1,
`xc7a100tcsg324-1`, one run per variant at a fixed 5.0 ns constraint; Fmax is estimated from the routed slack at that constraint, which is an estimate and
not a closure search. Fault injection: seeded single-event upsets at one random clock of each trial's burst; the injection point for a stored word is
the write of that word (the block RAM primitive's own injection inputs act on a write, so the other variants are made to do the same).

## Results

Generated by `python3 -m flow.assurance_report --write` from the JSON records in [results/b194](../results/b194/).

<!-- b194-results:start -->
<!-- b194-results:end -->
