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

### Proposed settings, confirmed in the spec interview (owner, 2026-11-23)

Before a run the agent reads the input folder and proposes the variable levers it can read, each with its source and any conflict: `agent propose <folder>`
writes `proposed_settings.yaml` (board, part, speed grade, reference clocks, I/O standards, PHYs, interfaces, suggested profile). That file is the
**interview's input**; there is no separate confirmation screen. `agent run --settings <file>` makes each setting one question of the spec
interview (`agent/graph/interview.py`, stage 0): the default is the proposed value, the reason names its source (and any conflict), and the answer
comes from the person (`--interview on`), the oracle, or the default. The interview's output is `confirmed_settings.yaml` in the design and `settings:`
in `spec.yaml`. **A run cannot leave the interview with an unconfirmed variable:** a setting nothing in the folder gave (status `ask`) has no default
and must be answered; a setting whose sources disagree is not settled by the default alone; a confirmed board that is not the run's `--board` stays
open. Each of these becomes a stage-0 gate failure (`[interview] unconfirmed variable: ...`). Missing values are asked, never guessed. Sources, in
order: `board_facts.yaml` (the design-package ingest of brief 174, `flow.package ingest`; **not merged yet, so this reads the file when it exists and
its format is assumed to be a mapping of facts, each plain or `{value, source}`**), the catalogue board named by the folder, and the spec for the
profile. An explicit `--board` or `--verif-profile` becomes the proposed value (source: the command line). The Navigator's Start page writes the
same proposals file and starts the run with `--interview on`; the questions appear on the Live page like any other question.

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

## Key results (plain words; every figure is in the tables under Results)

- **What each structure caught, in 300 seeded single-bit upsets per cell.** The plain design passed a flipped stored word to the output unflagged every
  time (300 of 300). The block RAM's built-in ECC corrected and flagged all 300 single flips and detected all 300 double flips; the fabric ECC did the same
  for single flips and detected 296 of 300 double flips (the other 4 hit check bits only). TMR on the counter corrected all 300 single-copy flips; the same
  bit flipped in two copies was outvoted (the output was wrong in 177 of 300, always flagged). Parity flagged every effective flip of the output register.
- **What nothing caught.** A flipped state register hung or corrupted the plain design in 154 of 300 trials unflagged (100 hangs, 54 silent), and every
  structure left that unchanged in RTL simulation, including the watchdog, which does not watch an idle sequencer. `fsm_safe_state` is a netlist effect
  that RTL simulation cannot show, and no netlist-level injection was run (known gap).
- **Cost, Vivado 2026.1, xc7a100t, one out-of-context run each at 5.0 ns.** Built-in ECC +0 LUT, +66 FF, Fmax estimate -7 %; fabric ECC +171 LUT, -35 %;
  TMR counter +61 LUT, +33 FF, -24 % (all three copies survived routing: 16/16/16); parity +25 LUT, -9 %; safe-state FSM +7 LUT, +3 FF, -0.1 %; watchdog
  +8 LUT, +17 FF, -5 %; all five together +100 LUT, +120 FF, -31 %. Latency +0 clocks for every structure here (3 clocks accept to output).
- **What each verification method caught of seven RTL bugs.** Lint 0; directed simulation with one seed 6; eight seeds 6; bounded formal on the control logic 3 (at
  depth 20 and at depth 80 alike: the deeper depth caught nothing more here). One bug (a length-0 burst taking the long way round) was only seen by formal, and
  four were only seen by simulation (they are outside the control module or need hundreds of clocks). No single method caught all seven.
- **Netlist checks (`thorough`).** The functional bench passed on the post-synthesis netlists and, after routing, on the timing netlist with SDF. `eqy`
  proved the plain control module equivalent and caught 3 of 3 planted faults that change logic, but **missed both dropped resets** (the bench on the
  core netlist caught them), could not read the netlist of the whole core (block RAM: `ERROR`, never a pass), and **returned FAIL on the control module with
  the watchdog** (a counterexample at step 17 in which the netlist's watchdog flag is set and the RTL's is not); the cause was not established, so do not read
  it as either a netlist defect or an eqy limit. `eqy` passed SAFE-only and TMR-only netlists.
- **Time.** On this design the checks of `standard` take about 9 s, `thorough` about 131 s (14 x), `high_reliability` about 177 s (19 x), plus a
  separate 72 s for the opt-in timing simulation. These are the checks only (no model time, no independent spec bench, no board), on a design of
  about 100 LUTs: the ratios say where the time goes (synthesis and `eqy` dominate), not what a large design would cost.
- **SEM.** The SEM IP (`sem` 4.1, `tmr_sem` 1.0) generates on the free Basic tier for the 7-series part; it was not synthesised or run on a board.

## Results

Generated by `python3 -m flow.assurance_report --write` from the JSON records in [results/b194](../results/b194/).

<!-- b194-results:start -->
### Fault injection (what each structure catches)

Seeded, 300 trials per cell, seed 1. Each cell: **masked / corrected / detected / silent / hang** (counts of trials). `corrected` = output right and a flag raised; `detected` = output wrong or no completion, flag raised; `silent` = wrong output, no flag; `hang` = no completion, no flag.

| fault | u | ecc_fabric | ecc_prim | par | safe | tmr | wd | all |
|---|---|---|---|---|---|---|---|---|
| one bit of a stored word | 0 / 0 / 0 / **300** / 0 | 0 / 300 / 0 / **0** / 0 | 0 / 300 / 0 / **0** / 0 | 0 / 0 / 0 / **300** / 0 | 0 / 0 / 0 / **300** / 0 | 0 / 0 / 0 / **300** / 0 | 0 / 0 / 0 / **300** / 0 | 0 / 300 / 0 / **0** / 0 |
| two bits of a stored word | 0 / 0 / 0 / **300** / 0 | 0 / 4 / 296 / **0** / 0 | 0 / 0 / 300 / **0** / 0 | 0 / 0 / 0 / **300** / 0 | 0 / 0 / 0 / **300** / 0 | 0 / 0 / 0 / **300** / 0 | 0 / 0 / 0 / **300** / 0 | 0 / 0 / 300 / **0** / 0 |
| one bit of the state register | 51 / 0 / 95 / **54** / 100 | 51 / 0 / 95 / **54** / 100 | 51 / 0 / 87 / **57** / 105 | 51 / 0 / 95 / **54** / 100 | 51 / 0 / 95 / **54** / 100 | 51 / 0 / 95 / **54** / 100 | 51 / 0 / 95 / **54** / 100 | 51 / 0 / 87 / **57** / 105 |
| one bit of the remaining counter | 123 / 0 / 0 / **18** / 159 | 123 / 0 / 0 / **18** / 159 | 102 / 0 / 0 / **17** / 181 | 123 / 0 / 0 / **18** / 159 | 123 / 0 / 0 / **18** / 159 | 0 / 300 / 0 / **0** / 0 | 108 / 0 / 171 / **21** / 0 | 0 / 300 / 0 / **0** / 0 |
| same bit in two TMR copies | - | - | - | - | - | 0 / 123 / 177 / **0** / 0 | - | 0 / 108 / 192 / **0** / 0 |
| one bit of the output register or parity | 153 / 0 / 0 / **147** / 0 | 153 / 0 / 0 / **147** / 0 | 142 / 0 / 0 / **158** / 0 | 152 / 1 / 147 / **0** / 0 | 153 / 0 / 0 / **147** / 0 | 153 / 0 / 0 / **147** / 0 | 153 / 0 / 0 / **147** / 0 | 139 / 3 / 158 / **0** / 0 |

Variants: `u` = ; `ecc_fabric` = ECC=1; `ecc_prim` = ECC=2; `par` = PAR=1; `safe` = SAFE=1; `tmr` = TMR=1; `wd` = WD=1; `all` = ECC=2, PAR=1, SAFE=1, TMR=1, WD=1.


### Area, Fmax and latency of each structure

xc7a100tcsg324-1, Vivado 2026.1, out of context, one run per variant. one out-of-context run per variant, a fixed 5.0 ns clock constraint; Fmax = 1 / (period - WNS) from the routed setup slack at that constraint (an estimate, not a closure search).

| variant | LUT | FF | RAMB36 | RAMB18 | WNS at 5.0 ns | Fmax est. (MHz) | latency (clocks) |
|---|---|---|---|---|---|---|---|
| u | 120 | 104 | 1 | 0 | +0.423 | 218.5 | 3 |
| ecc_fabric | 291 | 170 | 1 | 0 | -2.094 | 141.0 | 3 |
| ecc_prim | 120 | 170 | 1 | 0 | +0.062 | 202.5 | 3 |
| par | 145 | 170 | 1 | 0 | -0.042 | 198.3 | 3 |
| safe | 127 | 107 | 1 | 0 | +0.419 | 218.3 | 3 |
| tmr | 181 | 137 | 1 | 0 | -0.981 | 167.2 | 3 |
| wd | 128 | 121 | 1 | 0 | +0.177 | 207.3 | 3 |
| all | 220 | 224 | 1 | 0 | -1.631 | 150.8 | 3 |

| structure | variant | LUT | FF | block RAM tiles | Fmax | latency |
|---|---|---|---|---|---|---|
| ecc | ecc_prim | +0 | +66 | +0.0 | -7.3 % | +0 |
| ecc_fabric | ecc_fabric | +171 | +66 | +0.0 | -35.5 % | +0 |
| parity | par | +25 | +66 | +0.0 | -9.2 % | +0 |
| safe_fsm | safe | +7 | +3 | +0.0 | -0.1 % | +0 |
| tmr | tmr | +61 | +33 | +0.0 | -23.5 % | +0 |
| watchdog | wd | +8 | +17 | +0.0 | -5.1 % | +0 |
| all | all | +100 | +120 | +0.0 | -31.0 % | +0 |

### What each verification method catches

Seven RTL bugs planted one at a time in the plain design (`designs/b194_assurance/tests/mutants.py`). `yes` = the method reported a failure on the mutant; the unmutated design passes every method.

| mutant | lint | directed, 1 seed | 8 seeds | formal depth 20 | formal depth 80 |
|---|---|---|---|---|---|
| m1_last_word: the sequencer stops accepting one word early: the last word of every burst is never taken | no | yes | yes | yes | yes |
| m2_checksum_clear: the checksum is not cleared by start: the second burst adds to the first | no | yes | yes | no | no |
| m3_early_done: done is signalled without waiting for the FIFO and the output stage to drain | no | yes | yes | yes | yes |
| m4_count_low_byte: the remaining count is decremented in its low byte only: wrong across a multiple of 256 (bursts above 256 words) | no | yes | yes | no | no |
| m5_len_zero: a burst of length 0 is not special-cased: the sequencer waits for words that never come | no | no | no | yes | yes |
| m6_double_pop: the FIFO is read again while a read is in flight: a word is overwritten in the output register under back-pressure | no | yes | yes | no | no |
| m7_wrap_pointer: the write pointer wraps at 500 instead of 512: wrong only when the FIFO holds more than 500 words | no | yes | yes | no | no |
| **caught of 7** | 0 | 6 | 6 | 3 | 3 |

Netlist-level faults. Left: one fault planted in the Vivado post-synthesis netlist of the control module, checked by `eqy` against the RTL. Right: one fault planted in the netlist of the whole core (it holds a block RAM, which `eqy` cannot read), checked by the functional bench in xsim. The two netlists are different, so the rows pair kinds of fault, not the same fault.

| kind | fault in the control netlist | eqy | fault in the core netlist | functional bench |
|---|---|---|---|---|
| lut_init | flipped INIT bit 0 of LUT \FSM_sequential_g_plain.sq[0]_i_1: 000000004F4A4540 -> 000000004f4a4541 | FAIL | flipped INIT bit 0 of LUT \checksum[63]_i_1: B -> a | not caught |
| lut_init | flipped INIT bit 21 of LUT \FSM_sequential_g_plain.sq[1]_i_3: 0000000100000000 -> 0000000100200000 | FAIL | flipped INIT bit 21 of LUT \FSM_sequential_g_plain.sq[1]_i_1: EE6A6A6A00000000 -> ee6a6a6a00200000 | not caught |
| swap_regs | swapped the D inputs of registers \FSM_sequential_g_plain.sq_reg[0] and \FSM_sequential_g_plain.sq_reg[1] | FAIL | swapped the D inputs of registers bus_v_reg and \checksum_reg[0] | caught |
| reset_drop | register \g_single.r_reg[0]: reset pin R tied low | PASS | register \checksum_reg[0]: reset pin R tied low | caught |
| reset_drop | register \g_single.r_reg[11]: reset pin R tied low | PASS | register \checksum_reg[11]: reset pin R tied low | caught |

Equivalence of the unmodified netlists (`eqy`, strategy auto):

| netlist | status | seconds |
|---|---|---|
| whole core, plain (block RAM inside) | ERROR | 0.5 |
| control module, plain | PASS | 62.4 |
| control module, SAFE + TMR + WD | FAIL | 23.2 |
| control module, SAFE only | PASS | 24.2 |
| control module, TMR only | PASS | 18.6 |
| control module, WD only | FAIL | 38.0 |

Functional bench on the unmodified post-synthesis netlists (xsim, unisims): u pass (17.0 s), ecc_prim pass (17.9 s), all pass (17.9 s); eight seeds on `u`: pass (131.1 s). Post-route timing simulation with SDF of `u`: pass (10 bursts, 18.9 s).

### Time per profile

Wall time of each profile's checks on the development design, summed from the per-method times below (this PC, one run each, not a benchmark; model time and the independent spec bench are not included).

| profile | checks | seconds | against standard |
|---|---|---|---|
| prototype | lint, directed tests, 1 seed | 0.2 | 0.0x |
| standard | lint, directed tests, 1 seed, random tests, 3 seeds, bounded formal, design's own depth, mutation sweep (7 mutants, 1 seed each) | 9.1 | 1.0x |
| thorough | lint, directed tests, 1 seed, random tests, 8 seeds, bounded formal, depth x4, mutation sweep (7 mutants, 1 seed each), post-synthesis netlist: synthesis, post-synthesis netlist: simulation, equivalence (eqy, control module) | 130.8 | 14.4x |
| ip_release | lint, directed tests, 1 seed, random tests, 8 seeds, bounded formal, depth x4, mutation sweep (7 mutants, 1 seed each), post-synthesis netlist: synthesis, post-synthesis netlist: simulation, equivalence (eqy, control module) | 130.8 | 14.4x |
| high_reliability | lint, directed tests, 1 seed, random tests, 8 seeds, bounded formal, depth x4, mutation sweep (7 mutants, 1 seed each), post-synthesis netlist: synthesis, post-synthesis netlist: simulation, equivalence (eqy, control module), fault injection (variant all, 6 targets x 300 trials) | 176.9 | 19.4x |
| low_latency | lint, directed tests, 1 seed, random tests, 3 seeds, bounded formal, design's own depth, mutation sweep (7 mutants, 1 seed each) | 9.1 | 1.0x |

| method | seconds | source |
|---|---|---|
| lint | 0.1 | methods_rtl.json: Verilator lint of the RTL |
| directed tests, 1 seed | 0.2 | methods_rtl.json: tb_func, 40 bursts, Icarus |
| random tests, 3 seeds | 0.7 | methods_rtl.json: 3 x the per-seed time |
| random tests, 8 seeds | 1.8 | methods_rtl.json: 8 seeds |
| bounded formal, design's own depth | 0.6 | methods_rtl.json: SymbiYosys, depth 20, z3 |
| bounded formal, depth x4 | 3.7 | methods_rtl.json: depth 80 |
| mutation sweep (7 mutants, 1 seed each) | 7.6 | methods_rtl.json: stand-in for the agent's mutation run |
| post-synthesis netlist: synthesis | 38.0 | costs.json: Vivado out-of-context synthesis, u |
| post-synthesis netlist: simulation | 17.0 | methods_netlist.json: tb_func on the funcsim netlist, xsim |
| equivalence (eqy, control module) | 62.4 | methods_netlist.json: eqy_gate auto, PASS |
| fault injection (variant all, 6 targets x 300 trials) | 46.1 | faults.json: xsim |
| timing simulation (opt-in) | 71.9 | costs.json impl_s + methods_netlist.json timesim_u (10 bursts) |
<!-- b194-results:end -->
