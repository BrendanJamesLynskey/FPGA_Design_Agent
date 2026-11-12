# The closure loop and the design-time timing plan

**What it is for.** A design can pass simulation and still miss its clock, its resource budget or its power budget.
The closure loop then edits the RTL, re-checks simulation, rebuilds and repeats. It stops when every goal holds, or
when it stalls; it then says which goal it could not meet, its best value, and what it tried. A separate step before
the first build, the design-time timing plan, chooses where to use DSP slices and block RAM and how many register
stages each datapath needs, so the loop starts from a design that is already close.

**What has been shown (Vivado 2026.1, Artix-7 xc7a100t, one run per case):**
- **c13_hough_lines:** a course reference that misses 100 MHz by 0.17 to 0.23 ns. The loop closed it in one iteration,
  both with and without the plan.
- **Seeded misses:** of three development designs built at a raised clock, 1 closed (c16 at 200 MHz). The other two
  improved but stopped at the 5-iteration limit.
- **Nulls:** the RTL writer working from the plan failed the hidden bench 6 times out of 6. The first with-plan loop run
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
4. **Output.** It writes `TIMING_PLAN.md`: the instructions the RTL writer follows, with the inference template for
   each primitive.

After synthesis, a planned DSP slice or block RAM that did not appear fails the gate. After routing, the planned stage
is compared with the routed path, and the comparison is written as a calibration row.

## Limits

- One run per case: the results are illustrations, not rates.
- Only the 7-series family has a delay model.
- No calibration rows have been written yet. The c13 architect named an instance that the reference RTL does not
  have; the plan check now reports that.
- Area (G3) and power (G4) strategies are listed but not offered yet. G5 (the board) is not run.
