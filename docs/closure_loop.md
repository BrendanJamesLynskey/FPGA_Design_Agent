# The closure loop and the design-time timing plan

**What it is for.** A design can pass simulation and still miss its clock, its resource budget or its power budget.
The closure loop then edits the RTL, re-checks simulation, rebuilds and repeats. It stops when every goal holds, or
when it stalls; it then says which goal it could not meet, its best value, and what it tried. A separate step before
the first build, the design-time timing plan, chooses where to use DSP slices and block RAM and how many register
stages each datapath needs, so the loop starts from a design that is already close.

**What has been shown (Vivado 2026.1, Artix-7 xc7a100t, one run per case):**
- **c13_hough_lines:** a course reference that misses 100 MHz by 0.17 to 0.23 ns. The loop closed it in one iteration,
  both with and without the plan.
- **Seeded misses:** of three development designs built at a raised clock, 1 closed: c16_montgomery_mult at 200 MHz. The other two
  improved but stopped at the 5-iteration limit.
- **Nulls:** the Designer working from the plan failed the hidden bench 6 times out of 6. The first with-plan loop run
  accepted a design that synthesis had removed; it is not counted, and it led to the synthesis guard described below.

The numbers and caveats are in [results/62a_closure/README.md](../results/62a_closure/README.md).

## Try it

The loop on a benchmark task's RTL needs Vivado, Icarus and an OpenRouter key; G1 is the task's hidden bench:

```
python3 -m agent.graph.closure_task benchmark/course/tasks/c13_hough_lines \
    --rtl agent/tests/fixtures/closure/c13_orig/rtl --case c13_try --max-iter 3 --max-usd 0.50
```

A seeded timing miss is the same task's reference built at a faster clock:

```
python3 -m agent.graph.closure_task benchmark/course/tasks/c16_montgomery_mult \
    --rtl benchmark/course/tasks/c16_montgomery_mult/ref/rtl --case c16_try --clock-mhz 200
```

A seeded area or power miss gives the task a budget it misses (`lut ff bram dsp io power_w`):

```
python3 -m agent.graph.closure_task benchmark/course/tasks/c13_hough_lines \
    --rtl benchmark/course/tasks/c13_hough_lines/ref/rtl --case c13_bram1 --budget bram=1
```

The plan for an `architecture.yaml` that lists `datapaths` needs no tools, but needs the knowledge bank's delay model:

```
python3 -m flow.timing_plan <design dir>
```

In the agent graph both steps are off by default:

```
python -m agent run <spec.md> --design-plan --closure on
```

`--closure on` runs the loop as stage 6. That path is tested with fakes only: no live graph run has used it yet.

On a shared build machine, set `FDA_BUILD_LOCK_CMD` to a command that takes a build lock (see
`agent/graph/closure_task.py`). Without it, each build starts at once.

## Terms

- **WNS / WHS:** worst negative slack for setup / hold, the worst timing margin of the routed design. Both must be 0 or
  more.
- **Logic levels:** the LUTs and carry cells in series on a timing path.
- **DSP48E1 A/B, M and P registers:** a DSP slice's operand, product and output registers. They cost no fabric
  flip-flops, and a multiply only reaches the slice's full speed when they are used.
- **Goals G1 to G5:** each holds or not, with a value.
  - G1: simulation passes the independent bench, and synthesis agrees with simulation.
  - G2: timing.
  - G3: resources, within the spec's budget, else 80 % of the part.
  - G4: power, within the spec's budget, else the board limit.
  - G5: the board checks (not run yet).
- **Goal vector:** the five goals' values and verdicts, recorded before and after every iteration.
- **Shortfall:** how far an unmet goal is from its target, normalised (negative slack over the clock period; over-use
  over the budget). The loop works on the unmet goal with the largest shortfall that still has a strategy.
- **Strategy class:** a kind of repair, for example map a multiply to a DSP slice, add a register stage, balance an
  adder tree, or replicate a high-fanout register. The reports pick it, and the model writes the change.
- **Stall rule:** a strategy class is given up after two tries with no progress on its goal. When every class is given
  up, the loop stops and reports.
- **Delay model:** a per-family table of measured delays (a LUT level, an adder per bit, the DSP and block RAM stages).
  The timing plan uses it. The 7-series model was measured with `flow/delay_calib/` and lives in the knowledge bank;
  each number is good to about +/- 0.5 ns.

## How one iteration works

1. The controller reads the build's reports and digests them (`flow/digest/`): the worst path's cells, each net's
   fanout and the RTL register names at its two ends; utilisation and power by hierarchy; and synthesis messages.
2. It picks the goal and strategy (`agent/graph/closure_playbook.py`). A strategy whose usual cost would break another
   goal's budget is skipped. For example, no DSP mapping without DSP headroom.
3. One model call writes the change, and the independent bench runs (G1). A failure gets one repair call, then the
   change is undone.
4. The design is rebuilt. The change is kept only if an unmet goal improved and no goal got worse; otherwise the files
   go back to the copy taken before the change.
5. Every iteration is written to `history.jsonl`: the goal vector before and after, the strategy and why it was chosen,
   the diff, the change on every goal, and the cost.

**Synthesis guard.** Simulation alone cannot show that the built design is the simulated one. Example: two `always_ff`
blocks that drive one register pass in Icarus, but Vivado ties the register to ground and removes the logic behind it.
G1 therefore also fails when a change introduces new multi-driven nets, or makes synthesis remove instances that the
starting design kept. A RAM or ROM that synthesis already removed from the starting design does not count.

## The joint loop: area, power, checks, and going back to any stage

Since the second phase the loop works on every goal at once instead of one goal per iteration
(`agent/graph/closure_plan.py`; `--joint off` gives the one-goal loop of the first phase).

1. **One build, every report.** The flow already writes timing, utilisation, power, DRC and methodology from one routed
   checkpoint (`flow/build.tcl`). The digest reads them all. A new goal, **CHK**, holds when the routed DRC and
   methodology reports have no Error and no Critical Warning.
2. **One diagnosis.** `violations()` lists every problem of the build: setup and hold slack, each resource over its
   budget, latches, RAM built in registers, a planned DSP or BRAM that was not inferred, power, and each blocking DRC or
   methodology rule.
3. **One plan.** `plan()` takes the unmet goals worst first and picks at most one strategy for each. It skips a fix
   that would:
   - spend a resource that is over budget, or whose headroom is below a reserve (128 LUT, 64 FF, half a BRAM tile,
     1 DSP);
   - add power while the power goal fails;
   - cost slack while timing fails, or while the slack is under 0.3 ns;
   - push a DSP, BRAM or tight resource the opposite way to a fix already chosen.

   Among the fixes the reports support equally, one that uses a hard resource (DSP slice, block RAM, SRL, carry chain)
   ranks first. Every skipped fix is recorded with its reason. The chosen fixes go to the Designer in one prompt and one
   change.
4. **Back to the earliest stage the plan changes.** Each strategy names the stage it changes:
   - RTL and constraints (the design's XDC) fixes are made inside the loop;
   - a spec fix (for example fewer I/O pins) or an architecture fix (re-plan the datapath once every RTL strategy for a
     goal is used up) is not made by the loop. The loop stops, and the report carries `reentry`: the agent graph's
     state for that stage (`stage`, `note`, `note_role`, `owners`, the shape `agent/graph/pickup.py` uses to resume).
     In the agent graph, stage 6 hands this to the graph, which goes back to that stage; every later stage then runs
     again.
5. **The early check after synthesis.** Each change that passes the bench is first synthesised only. It is undone
   before any implementation run when synthesis already shows that it fails:
   - a BRAM or DSP count over a budget that was met (these counts do not change in implementation);
   - an area fix that did not lower the resource it was for;
   - LUT or FF more than 10 % over a budget that was met;
   - new multi-driven nets or newly removed instances;
   - a planned primitive missing.

   The post-synthesis timing and power are estimates. They are recorded, never used to reject. A change that passes
   is then built in full: the full build resumes from the synthesis checkpoint.
6. **The sign-off.** When every goal holds, the loop:
   - runs the independent bench again;
   - rebuilds if `build/` holds another attempt;
   - requires every gate of the flow's gates.json to pass on exactly the accepted files.

   Only then does the summary say `closure_claimed: true`. Without a sign-off step (in tests, or `--signoff off`)
   closure is never claimed.

### Area and power strategies

| Goal | Strategy | Stage | Hard resource | Offered when |
|---|---|---|---|---|
| G3 | `a_ram` infer block RAM instead of registers | RTL | yes | RAM built in registers, or one instance holds 256 or more FFs while LUT or FF is over budget |
| G3 | `a_dsp` multiplies from LUTs to DSP slices | RTL | yes | LUT over budget, 24 or more CARRY4, DSP headroom |
| G3 | `a_srl` delay lines into SRLs | RTL | yes | FF over budget |
| G3 | `a_bram_merge` both ports of one block RAM, or memories sharing one | RTL | yes | BRAM over budget |
| G3 | `a_lutram` a small memory into LUT RAM | RTL | no | BRAM over budget, LUT headroom of 256 or more |
| G3 | `a_dsp_share` time-multiplex one DSP slice | RTL | no | DSP over budget |
| G3 | `a_lut_mult` a small multiply in LUTs | RTL | no | DSP over budget, LUT headroom (not while timing fails) |
| G3 | `a_narrow`, `a_unused`, `a_latch` | RTL | no | LUT, FF or BRAM over budget; a latch |
| G3 | `a_io` fewer pins | spec | no | IO over budget (gated) |
| G4 | `p_bram_en` enable a BRAM only when it is used | RTL | yes | BRAM is 10 % or more of the dynamic power |
| G4 | `p_gate` gate data on valid | RTL | no | signals and logic are 30 % or more of the dynamic power |
| G4 | `p_ce` clock enables | RTL | no | clocks 20 % or more, or signals and logic 30 % or more |
| G4 | `p_dsp` a LUT multiply onto a DSP slice | RTL | yes | arithmetic in LUTs, DSP headroom |
| G4 | `p_clock` a lower clock | constraints | no | only when spec.yaml gives `min_freq_mhz` (gated) |
| CHK | `c_constraints`, `c_rtl_check` | constraints, RTL | no | a blocking DRC or methodology row |
| G2, G3, G4 | `x_replan_*` re-plan the architecture | architecture | no | the last resort, below every RTL class |

The timing strategies are as in the first phase. Power is Vivado's vectorless estimate unless the build reads a SAIF.

### Action log (data for choosing closure strategies)

Every attempt writes one line to `closure_actions.jsonl` beside `history.jsonl`, schema `fda.closure_action/1`:

| Field | What it holds |
|---|---|
| `design` | tags from spec.yaml and the RTL: top, part, clocks, budgets given, file and line counts, multiplies, memories, `ram_style`, a hash of the RTL |
| `features` | the build before the change: WNS, WHS, TNS, failing endpoints, the worst path's logic levels, carry chain and runs, fanout, route share, DSP or BRAM on the path; each resource used, its ratio to the budget and to the part; power total, dynamic and by type; latches, RAM in registers; DRC and methodology counts |
| `goals_before` | each goal's met flag and shortfall |
| `violations` | the diagnosis (goal, kind, value, target) |
| `actions` / `skipped` | the fixes chosen (id, class, goal, stage, hard, reason, predicted effects) and the ones left out, each with its reason |
| `target_stage` | the earliest stage the plan changes |
| `result` | `accept` or `revert`, the reason, whether the early check rejected it and its estimate, each goal after, the goals improved, and the build's features after |
| `cost` | model cost in USD (provider-reported), tokens, synthesis and build seconds |

A record is written for every attempt, kept or undone, so each line is a labelled example: what the reports showed,
what was tried, and what happened.

### What a user could guess wrong

- **"All goals met" is not "closure claimed".** Read `closure_claimed`. It is true only after the sign-off: bench
  again, a build of the accepted files, every flow gate passing.
- **CHK `met: None`** means the build reported no DRC or methodology summary (an old or trimmed build). The sign-off's
  gates still check both.
- **The early check never rejects on timing or power after synthesis.** Those are estimates. It rejects only on counts
  synthesis knows, on the synthesis guard and on the plan.
- **A loop-back stops the closure run.** The loop does not change the spec or the architecture itself. `reentry` says
  where to go back and why; the agent graph acts on it, and the task driver only reports it.
- **One change may carry several fixes.** A joint change is kept or undone as a whole. Each fix's stall counter moves
  with the result for its own goal.
- **The power goal is an estimate.** It uses Vivado's vectorless toggle rates (12.5 % on inputs) unless a SAIF is read.
  A power fix that is real on the board may not show in it, and the other way round.

## The design-time plan

`architecture.yaml` may list `datapaths`: the arithmetic chains on the critical paths, as a list of operations
(`mul`, `add`, `compare`, `table`, `mux`, `memory`, `delay`, `fifo`, `logic`, `shift`, or `ip` for an IP-library entry).
`flow/timing_plan.py` then works through four steps.

1. **Resource.** It maps each operation to a resource, hard resources first: multiplies on DSP slices, memories in
   block RAM, short delays in shift registers. It falls back to logic only with a stated reason (operand too small,
   budget used up).
2. **IP-library entries.** For an `ip` operation it calls the library's measured-variant chooser (`flow/ipvariants.py`,
   [docs/ip_variants.md](ip_variants.md)). If no variant is known to fit at that point, it plans the operation's
   `fallback` operations instead.
3. **Pipeline depth.** It estimates each piece's delay from the delay model and places registers so each stage fits
   70 % of the period. A DSP slice's own registers are always used.
4. **Output.** It writes `TIMING_PLAN.md`: the instructions the Designer follows, with the inference template for
   each primitive.

After synthesis, a planned DSP slice or block RAM that did not appear fails the gate. After routing, the planned stage
is compared with the routed path, and the comparison is written as a calibration row.

## Limits

- One run per case: the results are illustrations, not rates.
- Only the 7-series family has a delay model.
- No calibration rows have been written yet. The c13 architect named an instance that the reference RTL does not
  have; the plan check now reports that.
- G5 (the board) is not run by the loop yet.
- The early check and the sign-off need the task driver's or the graph's build functions. In the graph the sign-off is
  the stage gates after stage 6, not the loop's own sign-off step.
- Implementation directives and parallel implementation strategies are not offered (`t_impl`, phase `later`).
