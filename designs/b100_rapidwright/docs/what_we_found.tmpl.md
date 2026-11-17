# What we found (brief 100: RapidWright in the agent, 2026-11-17)

Vivado 2026.1 is the referee for every number below: each is Vivado's `report_timing`/`route_design` result on a checkpoint, read from a
committed record in `results/b100/` (the table values are rendered from `results/b100/summary.json`; nothing is typed). RapidWright's own
estimates are in the logs and are never used as a result. Part `xck26-sfvc784-2LV-c`, one Vivado thread, no board.

## In one paragraph

RapidWright 2026.1.2 reads and writes Vivado 2026.1 checkpoints for the K26 and the Artix-7 100T, and Vivado accepts what it writes (route,
DRC, bitstream). **Pre-implemented relocatable blocks work and are the useful part**: a block implemented once and stamped at other sites keeps
nearly all of its internal delays, where the same logic implemented again by Vivado at the same sites does not. **Our own placement and
RWRoute routing both lost to Vivado on timing** in every run, on one chain, with a first-cut annealing placer; RWRoute was several times faster than Vivado's
router. **The agent given the tools did not do better than the agent without them**: neither beat the as-built result, and the tool run showed
what the agent still lacks (a per-path timing breakdown, and a build that returns in minutes).

## Stage 0: does it work here (`results/b100/s0/`)

- Versions: RapidWright 2026.1.2 (PyPI wheel, AMD GitHub release jar), JPype 1.7.1, the JRE inside Vivado 2026.1 (Temurin 24.0.2+12).
- K26: a Vivado-routed checkpoint with WNS {{v:stage0.xck26.vivado_wns_ns}} ns, read and written by RapidWright, then `route_design`d by Vivado: WNS
  {{v:stage0.xck26.after_rapidwright_wns_ns}} ns, 0 routing errors, bitstream written. Artix-7 100T: WNS {{v:stage0.xc7a100t.vivado_wns_ns}} ns before and
  {{v:stage0.xc7a100t.after_rapidwright_wns_ns}} ns after (the 4 ns target is missed on that part either way), bitstream written.
- Memory: the JVM's scope peak was {{v:stage0.jvm_peak_gib_first_read}} GiB on a first read (it includes the Vivado RapidWright starts to make the checkpoint's
  EDIF readable) and under 1 GiB when that EDIF is cached. Declared to the heavy-slot rule as 3G.
- One gotcha: RapidWright runs the first `vivado` on `PATH`; with the 2025.2 install first it refuses 2026.1 checkpoints. `scripts/rw.sh` and
  `flow/rapidwright_pin.py` put 2026.1 first.

## Capability 1: pre-implemented relocatable block

The block is `pcs_unit` (brief 96's `pcs_tx` with its own source and sink), implemented once out of context in a pblock, relocated by RapidWright to
three other sites (`results/b100/c1/rw_mv_*.log`: nets with routing before and after are equal), and stamped with the original into one design,
against the same four-copy design implemented by Vivado alone with the pblock moved by the same offsets. The numbers compare every endpoint register of copy 1, 2 and 3
with the same endpoint of copy 0, by Vivado's data-path delay. "Seeds" here are the target period perturbations in the run name (3.40 and 3.41 ns); Vivado's placer has no seed.

{{table:c1}}

{{table:c1_whole}}

What it says: the stamped copies keep their internal delays (most endpoints identical to the picosecond; the rest differ where the device differs: other
columns, other clock-region rows), and the worst internal path is the same in every copy and in every build of the stamp. The Vivado-alone copies
differ from each other everywhere (almost no endpoint equal) and their worst path differs by tens of picoseconds between copies and between builds.
The stamp's whole-design runs took less Vivado time because the block's implementation (one out-of-context run, `results/b100/c1/blk_p0_run.json`) is paid once.
Limits: a block needs a narrow interface (design.md section 6), only a few columns accept a 128-slice block, and the stamped design still fails its 3.4 ns target
(the block itself is a 3.5 ns block, so that is expected).

## Capabilities 2 and 3: placement and routing of the transmit chain

`chain_top` is brief 96's `mac64_tx` and `pcs_tx` (unchanged) feeding the TXDATA pins of a bare `GTHE4_CHANNEL_X0Y6`. In the Vivado-alone baseline the period is set by the MAC's
CRC logic (10 LUT levels, route about three quarters of the delay), not by the PCS or the wire to the GT. Arms, per period perturbation:
`base` Vivado alone; `place` our annealer re-places the MAC and PCS slices (`flow/rw/place_chain.py`) and Vivado routes; `placew` the same with the nets on Vivado's worst
paths weighted ten times; `rwr` RWRoute routes Vivado's placement and Vivado does not route; `fixed` RWRoute re-routes the worst-path nets inside Vivado's routed result and locks them.
"Achieved period" is the target minus WNS; the 2-clock latency is the chain's two registers at that period. Brief 100 asked for latency at the block's own Fmax; this is it.

{{table:c23_arms}}

{{table:c23_rows}}

What it says, plainly: RapidWright's placement and routing are worse than Vivado's on timing in these runs. Reasons we can name (not proven): the annealer's cost is wire length, Vivado's
placer is timing-driven; RWRoute's delay estimate is not Vivado's; the MAC CRC path is logic depth, which placement cannot remove. RWRoute's speed is real:
see the RapidWright time column against Vivado's route time. Nothing here supports using our placer or RWRoute for closure on this design.

## Stage 2: the agent with and without the tools

Same design (copy of `chain_top` and 96's modules, clock 3.2 ns), same task text, model, turn cap and wall cap; arm A also has `rw_status`, `rw_relocate_block`, `rw_place_chain`, `rw_route`, `rw_referee`.
Claude Sonnet 5.5 through the Claude Code arm, Max plan.

{{table:agent}}

- Both arms measured the same baseline: WNS -0.759 ns at 3.2 ns (achieved period about 3.96 ns), set by the MAC's CRC loop. Neither improved on it.
- Arm A tried the RapidWright placement twice (the PCS alone, then the MAC and PCS) and had Vivado judge both with `rw_referee`: both were worse than the baseline (-0.965 and -0.804 ns). It reported that placement cannot
  remove the CRC logic depth. Arm B wrote a pblock; its build took 31 minutes and the tool call timed out in the agent, so the agent never saw the result. The finished build (read by us afterwards)
  has WNS -0.778 ns: no gain. Neither arm had a per-path breakdown for the TXDATA and MAC-to-PCS paths in the baseline: only `rw_referee` gives it (arm A got it for its own runs). That is the gap brief 97's `latency_path` tool is for.
- Two bugs in the agent were found by the first runs and fixed on this branch: the `build` tool refused the KR260's part name ("not a plain part name"), and the RapidWright tools did not find Vivado 2026.1 on `PATH`.

## What did not work, and what we would try next

- Direct input pins on a pre-implemented block (73 of them) were unreachable in every copy; RapidWright's soft-preserve completion did not rescue it; the block needs a narrow interface.
- Our first placement run was a random walk because a placed checkpoint has no site pins on its nets; the referee caught it (WNS -6.07 ns, kept as `results/b100/c23/first_pass_bugs/`).
- Fixed routes laid on an unrouted design took wires other pins needed; Vivado refused the design. The kept variant re-routes inside Vivado's result.
- Next: a timing-driven placer (criticality from Vivado's report each round), block-level relocation of the MAC's CRC cone, RWRoute with Vivado's delay model, a 7-series run of the same comparison.
