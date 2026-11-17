# What we found (brief 100: RapidWright in the agent, 2026-11-17)

Vivado 2026.1 is the referee for every number below: each is Vivado's `report_timing`/`route_design` result on a checkpoint, read from a
committed record in `results/b100/` (the table values are rendered from `results/b100/summary.json`; nothing is typed). RapidWright's own
estimates are in the logs and are never used as a result. Part `xck26-sfvc784-2LV-c`, one Vivado thread, no board.

## In one paragraph

RapidWright 2026.1.2 reads and writes Vivado 2026.1 checkpoints for the K26 and the Artix-7 100T, and Vivado accepts what it writes (route,
DRC, bitstream). **Pre-implemented relocatable blocks work and are the useful part**: a block implemented once and stamped at other sites keeps
most of its internal delays, where the same logic implemented by Vivado at the same sites does not (it differs by hundreds of picoseconds at almost every
endpoint), and a stamped design gave the same result at both period perturbations. **Our own placement and RWRoute routing both lost to Vivado on timing**
in every paired run (two per arm), on one chain, with a first-cut annealing placer; RWRoute was five to seven times faster than Vivado's router on the same
placement but left hold violations. **The agent given the tools did no better than the agent without them**: neither beat the as-built result, and the runs showed
what the agent still lacks (a per-path timing breakdown, and a build that returns within the tool timeout).

## Stage 0: does it work here (`results/b100/s0/`)

- Versions: RapidWright 2026.1.2 (PyPI wheel, AMD GitHub release jar), JPype 1.7.1, the JRE inside Vivado 2026.1 (Temurin 24.0.2+12).
- K26: a Vivado-routed checkpoint with WNS {{v:stage0.xck26.vivado_wns_ns}} ns, read and written by RapidWright, then `route_design`d by Vivado: WNS
  {{v:stage0.xck26.after_rapidwright_wns_ns}} ns, 0 routing errors, bitstream written. Artix-7 100T: WNS {{v:stage0.xc7a100t.vivado_wns_ns}} ns before and
  {{v:stage0.xc7a100t.after_rapidwright_wns_ns}} ns after (the 4 ns target is missed on that part either way), bitstream written.
- Memory: the JVM's scope peak was {{v:stage0.jvm_peak_gib_first_read}} GiB on a first read (it includes the Vivado RapidWright starts to make the checkpoint's
  EDIF readable) and {{v:stage0.jvm_peak_gib_cached}} GiB when that EDIF is cached. Declared to the heavy-slot rule as 3G.
- One gotcha: RapidWright runs the first `vivado` on `PATH`; with the 2025.2 install first it refuses 2026.1 checkpoints. `scripts/rw.sh` and
  `flow/rapidwright_pin.py` put 2026.1 first.

## Capability 1: pre-implemented relocatable block

The block is `pcs_unit` (brief 96's `pcs_tx` with its own source and sink), implemented once out of context in a pblock, relocated by RapidWright to
three other sites (`results/b100/c1/rw_mv_*.log`: nets with routing before and after are equal), and stamped with the original into one design,
against the same four-copy design implemented by Vivado alone with the pblock moved by the same offsets. The numbers compare every endpoint register of copy 1, 2 and 3
with the same endpoint of copy 0, by Vivado's data-path delay. "Seeds" here are the target period perturbations in the run name (3.40 and 3.41 ns); Vivado's placer has no seed.

{{table:c1}}

{{table:c1_whole}}

What it says:

- The stamped copies keep the original's internal delays at most endpoints (the first table: identical to the picosecond at 351 to 504 of 579 endpoints, mean difference 4 to 39 ps, largest 114 to
  345 ps). The differences grow with distance from the original and with crossing to another column: copy 1 is in the same column as the original, copies 2 and 3 are in the other. We have
  not isolated the cause (tile types and clock-region rows are the likely ones).
- The Vivado-alone copies differ from copy 0 at almost every endpoint (mean 226 to 281 ps, largest 1.2 to 1.6 ns), because each copy is placed and routed afresh; the endpoints common to both copies are 451 of 579, so the
  comparison is over those.
- The stamped runs at 3.40 and 3.41 ns gave identical block results and the same whole-design WNS; the Vivado-alone runs did not (WNS and worst internal path both moved). The 0.01 ns step is therefore a perturbation for
  the alone arm only: the locked blocks hold the stamp steady. That is the repeatability this capability buys.
- Whole-design timing: the stamped design is a little better than the alone design at both perturbations (second table), and at 3.40 ns the worst path of both designs is inside a block (`*_timing.rpt`). Hold slack is positive in these four runs.
  The worst internal path of a stamped copy is 3.50 ns against 3.60 to 3.65 ns for the alone copies; the stamped block was implemented once on its own, so this is not a like-for-like Fmax claim, only that a good
  implementation is kept.
- Vivado times are not comparable between rows: other sessions loaded the machine and identical-size runs differed three-fold (the stamp's block implementation, one out-of-context run, is in `results/b100/c1/blk_p0_run.json`).
- Limits: a block needs a narrow interface (design.md section 6); only three slice columns accept this 128-slice block; the block runs at about 3.5 ns, so both whole designs fail the 3.4 ns target.

## Capabilities 2 and 3: placement and routing of the transmit chain

`chain_top` is brief 96's `mac64_tx` and `pcs_tx` (unchanged) feeding the TXDATA pins of a bare `GTHE4_CHANNEL_X0Y6`. In the Vivado-alone baseline the worst path is the MAC's CRC cone in the first run (`baseref_s0_timing.rpt`: 3.69 ns, 55 % routing) and the MAC-to-PCS path in the second
(`baseref_s1_timing.rpt`); the paths from the PCS to the GT's TXDATA pins keep 0.9 to 1.9 ns of slack in every run. Arms, per period perturbation:
`base` Vivado alone; `place` our annealer re-places the MAC and PCS slices (`flow/rw/place_chain.py`) and Vivado routes; `placew` the same with the nets on Vivado's worst
paths weighted ten times; `rwr` RWRoute routes Vivado's placement and Vivado does not route; `fixed` RWRoute re-routes the worst-path nets inside Vivado's routed result and locks them.
"Achieved period" is the target minus WNS; the 2-clock latency is the chain's two registers at that period. Brief 100 asked for latency at the block's own Fmax; this is it.

{{table:c23_arms}}

{{table:c23_rows}}

What it says, plainly:

- Vivado alone moves by 0.35 ns between two period targets 0.01 ns apart (first and second rows of the table). That scatter is larger than the gap between most arms, so two runs per arm say little about a
  small difference; they do say the RapidWright arms are worse than their own baseline in both paired seeds, by 0.3 to 2.3 ns.
- `place` and `placew` (our annealer, with and without Vivado's critical nets weighted) lose in both seeds; weighting did not help. `fixed` (RWRoute on the worst-path nets inside Vivado's routing) loses in both seeds.
  `rwr` (RWRoute for everything) loses by the most and leaves hold violations in both seeds (WHS negative).
- Reasons we can name, not proven: the annealer's cost is wire length while Vivado's placer is timing-driven; RWRoute's delay estimate is not Vivado's; the first RapidWright run was a random walk until we fixed a bug
  (design.md section 6).
- RWRoute's speed is real: it routed the whole chain in 12.5 s and 58.4 s (the machine was loaded in the second run) against Vivado's 70.6 s and 396.7 s route step on the same placements. Speed without timing is not a
  closure tool here.
- LUT and FF counts are identical in every arm: RapidWright moved and routed, it did not change the netlist.
- Nothing here supports using our placer or RWRoute for closure on this design. What would change that is listed under "next".

## Stage 2: the agent with and without the tools

Same design (copy of `chain_top` and 96's modules, clock 3.2 ns), same task text, model, turn cap and wall cap; arm A also has `rw_status`, `rw_relocate_block`, `rw_place_chain`, `rw_route`, `rw_referee`.
Claude Sonnet 5.5 through the Claude Code arm, Max plan.

{{table:agent}}

- Both arms measured the same baseline, WNS -0.759 ns at 3.2 ns (achieved period about 3.96 ns), set by the MAC's CRC loop. Arm A's build record is `results/b100/agent/a/baseline_build_run.json`
  and `timing_summary.rpt`; arm B's first build was overwritten by its second, so its baseline is the number in its final message (`agent/b/result.json`). Neither improved on it.
- Arm A tried the RapidWright placement twice (the PCS alone, then the MAC and PCS) and had Vivado judge both with `rw_referee`: both were worse than the baseline (-0.965 and -0.804 ns; `agent/a/*_run.json`). It reported
  that placement cannot remove the CRC logic depth.
- Arm B wrote a pblock for the MAC and PCS in one clock region; its build took 1,880 s (`agent/b/completed_build_run.json`) and the tool call was abandoned by the agent after 1,800 s, so the agent never saw the result. We read the
  finished build afterwards: WNS -0.778 ns (`agent/b/completed_build_timing_summary.rpt`), no gain. The agent chose a clock region without checking where the GT is.
- Neither arm could get a per-path breakdown for the TXDATA and MAC-to-PCS paths of the baseline: only `rw_referee` gives it, and arm A used it only on its own re-placements. That is what brief 97's `latency_path` tool is for.
- The tool run found a real difference in the agent's reach: arm A could try a physical idea in a few minutes per attempt (a RapidWright step of tens of seconds plus a Vivado route of about four minutes), arm B's only physical lever (a pblock in the XDC) cost
  a full flow build of half an hour.
- Two bugs in the agent were found by the first runs and fixed on this branch: the `build` tool refused the KR260's part name ("not a plain part name"), and the RapidWright tools did not find Vivado 2026.1 on `PATH`.

## What did not work, and what we would try next

- Direct input pins on a pre-implemented block (73 of them) were unreachable in every copy; RapidWright's soft-preserve completion did not rescue it; the block needs a narrow interface.
- Our first placement run was a random walk because a placed checkpoint has no site pins on its nets; the referee caught it (WNS -6.07 ns, kept as `results/b100/c23/first_pass_bugs/`).
- Fixed routes laid on an unrouted design took wires other pins needed; Vivado refused the design. The kept variant re-routes inside Vivado's result.
- Next: a timing-driven placer (criticality from Vivado's report each round), block-level relocation of the MAC's CRC cone, RWRoute with Vivado's delay model, a 7-series run of the same comparison.
