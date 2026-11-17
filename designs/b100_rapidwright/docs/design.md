# b100_rapidwright: design note (written before the capability code; brief 100, 2026-11-17)

Stage 0 (does RapidWright work here) is done and recorded in `results/b100/s0/`; this note was written before stage 1's code. Sections 1 to 5 are
that note as written (with the block name corrected where the plan changed); section 6 lists what changed once the code met the device and why.
Facts from our own runs are marked with their file; facts from the literature are marked "(cited)" or "(from memory, unverified)".

## 1. What RapidWright is and where it sits in our flow

RapidWright is AMD Research's open Java framework (Apache 2.0 for the framework; the "API library" jar carries an AMD EULA part: see
`docs/licences.md`) that reads and writes Vivado design checkpoints (`.dcp`) and exposes the placed and routed netlist as objects: sites,
BELs, cells, nets, PIPs. Its authors describe it as a way to build custom implementations by assembling pre-implemented modules and to
write their own placers and routers (Lavin and Kaviani, "RapidWright: Enabling Custom Crafted Implementations for FPGAs", FCCM 2018;
cited). Its router, RWRoute, is a timing-driven router for UltraScale+ and Versal written in the same framework (Zhou, Lavin, Kaviani
and Moini, "RWRoute: An Open-source Timing-driven Router for Commercial FPGAs", ACM TRETS 2022; cited).

How it fits ours: **Vivado stays the synthesiser, the legaliser of record and the referee.** RapidWright works on a checkpoint between
two Vivado steps:

```
Vivado synth -> opt -> place ----------------> route -> report_timing   (Vivado alone: the baseline)
                         |                        ^
                         +--> RapidWright: move/stamp cells, route nets -+   (the new path; Vivado times the result)
```

Every number we claim for a RapidWright path comes from Vivado's own `report_timing` on the checkpoint RapidWright wrote, after
`route_design` has completed and checked the routing. RapidWright's own estimates are recorded where they exist but never used to claim
closure (brief 100's rule).

## 2. Stage 0 findings (measured; `results/b100/s0/`)

| Item | Result |
|---|---|
| RapidWright | 2026.1.2 (PyPI wheel, jar from AMD's GitHub release), JPype 1.7.1, Java: the JRE inside Vivado 2026.1 (Temurin 24.0.2+12) |
| Reads Vivado 2026.1 DCP, `xck26-sfvc784-2LV-c` | yes: 1167 cells, 1167 placed, 1026 nets with PIPs read; written back in 0.8 s |
| Reads Vivado 2026.1 DCP, `xc7a100tcsg324-1` | yes: 1164 cells (one unplaced cell, see gaps), 1027 nets with PIPs; written back in 0.5 s |
| Vivado 2026.1 accepts the written checkpoint | yes, both parts: `route_design` completes, 0 routing errors, DRC 0 errors, `write_bitstream` completes (ZU+ and 7-series) |
| Timing after the round trip | K26: WNS 0.218 ns before and after (same placement and routing); 7-series: the design misses its 4 ns target (-5.4 ns) before and after, the same either side to 0.04 ns |
| Memory | JVM scope peak 0.71 GiB with the readable EDIF cached (`results/b100/s0/rw_xck26_cached.time`), 2.60 GiB when RapidWright starts a Vivado to make it (`rw_xck26_peak.time`) (declared to the heavy-slot rule as 3G) |
| Run time | read 12.7 s with the EDIF cached (`rw_xck26_cached.log`; the machine was busy), 44 s on a first read (Vivado start-up plus the device file load; `rw_xck26_peak.log`) |
| Gotcha | RapidWright starts a Vivado found on `PATH` to turn the checkpoint's encrypted EDIF into a readable one. With 2025.2 first on `PATH` it fails with "created with Vivado v2026.1 and cannot be opened in this version". `scripts/rw.sh` puts the pinned Vivado first |

So RapidWright can read and write 2026.1 checkpoints for both parts and the branch goes ahead.

## 3. The three capabilities, the choices and the alternatives

The block under test is brief 96's own `pcs_tx` (encode, scramble, gearbox: about 830 LUTs and 330 FFs) and, for the chain, `mac64_tx` +
`pcs_tx` + a bare `GTHE4_CHANNEL` on the K26 (`rtl/chain_top.sv`). All RTL is 96's, unchanged.

### 3.1 Pre-implemented relocatable block

Choice: implement the block once out of context (OOC) in a pblock, lock it, save it; relocate the saved placement and routing by a
tile offset with `RelocationTools.relocate`; read it into a top design in Vivado with `read_checkpoint -cell`; Vivado places the rest,
routes the connections to the block, and times everything. Alternatives: (a) merge in RapidWright (`ModuleInst` flow): a netlist and
routing assembler of our own for the top, more code and more to get wrong; (b) Vivado's partition-pin flow without RapidWright:
cannot move a routed block. The Vivado-side read is chosen so that Vivado stays the legaliser.
What is measured: the block's internal path delays (register to register inside the block) at the original site and at the moved
sites, against Vivado implementing the same block afresh at the same sites. Repeatability is part of latency: a delay that is the
same in every build and at every site is worth a number even when it is not the smallest.

### 3.2 Latency-aware placement

Choice: take Vivado's placed (not routed) checkpoint of `chain_top`; RapidWright moves whole slices (a `SiteInst` with its LUT/FF
assignment, so the packing Vivado legalised stays legal) of the latency chain to free sites of the same type by simulated annealing on
a wire-length cost weighted towards the TXDATA registers and the GT site; Vivado routes and times. Alternatives: (a) a pblock next to the GT
in Vivado alone (a fair baseline, also run); (b) a cell-level placer: needs control-set and carry legality that Vivado already owns.
The cost is RapidWright's estimate and is never reported as a result.
Chain definition (brief 97's `latency_path` tool has not landed, so this uses the register list of `b96_kr260_10g/docs/design.md`
section 3): the MAC output registers `x_d`, `x_c`, the PCS cells (`gt_d`, the gearbox remainder `acc`, its fill `n`, the scrambler
history, and the logic between them), and the GT's TXDATA pins.

### 3.3 Routing control

Choice: (a) RWRoute, timing-driven, on the same placed checkpoints Vivado routes, compared with Vivado's `route_design` on delay, run
time and run-to-run variation; (b) fixed routes: RWRoute routes the nets on the worst paths and they are fixed (`IS_ROUTE_FIXED`),
Vivado routes the rest. Alternatives: nextpnr-xilinx and Project X-Ray/U-Ray give open place and route for 7-series, with partial
UltraScale+ coverage (from memory, unverified); they cannot produce a bitstream Vivado times, so they are not usable for the K26 here.

## 4. Fair-comparison rules (set before the runs)

- Same part, same RTL, same constraints (clock period set per run by `impl.tcl`), same Vivado 2026.1, one thread.
- "Seeds": Vivado's placer has no seed parameter (`list_param` shows none), so a Vivado seed is a clock-period dither of 0.00, 0.01, ...
  ns on the target; a RapidWright seed is the annealer's random seed. Reported as "variation over N perturbations", never as "seeds" without
  that explanation. N is stated with each table.
- The metric: WNS at a stated target period (closure claim only if WNS >= 0), the achieved period `target - WNS` for Fmax comparisons, latency
  in ns at that period (stage count times period), LUT/FF from Vivado, wall run time of each step.
- A loss to Vivado is reported plainly.

## 5. Gaps known before starting

- ZU+ (K26) only for the capabilities; the 7-series part is stage 0 only.
- The GT is a bare primitive: its clocking is not the real design's BUFG_GT path.
- No board is touched; whether a faster chain survives the GT's own latency is a board question for the planner.

## 6. What changed after the code met the tools (measured; every item has its record)

1. **The block is `pcs_unit`, not `pcs_tx`.** The plan stamped brief 96's `pcs_tx` (73 input pins) as the block. In Vivado, `route_design` on
   the stamped design failed in every copy, original site included, on one or two input pins ("Load Pin does not reach Interconnect
   fabric within 5 hops", "Expansion wavefront from Load was blocked by locked nodes"): an out-of-context block is routed without
   its input pins' last hop, and the router that stamps it later cannot always get past the block's own locked routes. It failed the same way
   whether the bus ended on LUT pins or on registers inside a wrapper (`results/b100/c1/failed_direct_ports/`). RapidWright's `PartialRouter`
   with soft preserve (the "complete" mode of `flow/rw/route.py`) routed all but 84 of 15,164 pins in 11 s but Vivado then refused 6 of them
   (same folder). A block with three input pins (`rtl/pcs_unit.sv`: pcs_tx with its own shift-register source and xor sink inside) stamps. The limit is
   written down for users: **a pre-implemented block needs a narrow interface, or its input pins may be unreachable when it is stamped.**
2. **How far a block can move depends on its footprint.** `RelocationTools.getValidRelocationOptions` lists the anchor sites a block can
   move to: the 98-slice first block could shift to ten slice columns, the 128-slice `pcs_unit` to three (X35, X38, X41). The targets are
   read from that list (`results/b100/c1/scans/`).
3. **A placed, unrouted checkpoint has no site pins on its nets**, so RapidWright's net lists were empty and the first placement run was a random
   walk (Vivado: WNS -6.07 ns, `results/b100/c23/first_pass_bugs/`). `DesignTools.createMissingSitePinInsts` fixes it. The random run is kept
   as a negative control: it shows the referee catches a bad RapidWright placement.
4. **Fixed routes on an unrouted design conflict with other pins.** RWRoute routed 71 of the nets on Vivado's worst paths and locked them; Vivado
   then refused the design ("Fixed routing constraint on net ... conflicts with pin ... The said pin is unroutable", 10 pins). The kept
   version re-routes those nets inside Vivado's own routed result and keeps every other route.
5. **The period-setting path of the chain is in the MAC, not at the GT.** In the baseline the worst path is `sh_reg -> u_mac/crc_reg` (10 LUT
   levels); the PCS and the PCS-to-GT paths have more slack (`results/b100/c23/base_s0_chain.json`). The chain given to the RapidWright
   placer is therefore the MAC and the PCS (`u_mac/*`, `u_pcs/*`), and the report gives all three slacks.
6. **The agent's `build` tool refused the KR260's part name** (`xck26-sfvc784-2LV-c`: "not a plain part name"; the pattern wanted six characters
   before the first hyphen). Fixed in `agent/core/tools.py` with a test; recorded in the agent improvement ledger by the planner.
