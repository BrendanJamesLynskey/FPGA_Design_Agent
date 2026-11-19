# Brief 102: managed projects, stage 2 (records)

A placed-and-routed block imported into a managed project, relocated with RapidWright, and what Vivado says about it. The design is
[designs/b102_managed_pr](../../designs/b102_managed_pr/README.md); the concept and the rules are in
[docs/managed_projects.md](../../docs/managed_projects.md) (section "Stage 2").

## Verdict first

- **The block's internal timing is not unchanged for every placement.** With the block locked, Vivado left every cell, BEL and route of it alone in all six
  placements tried (`placements/placement_evidence_all.json`). The delay of the interconnect inside the block (Vivado's `get_net_delays`, 5,197 pin
  delays) is identical to the picosecond when the same block is re-placed at its delivered site with other surroundings (2 arms) and when it is relocated by
  exactly one clock region (60 slice rows, `p1`). It changes when it is relocated by half a clock region (`p2`: 100 of 5,197 pin delays differ, the largest by
  161 ps) or to another column (`p3`: 1,812 differ, the largest by 275 ps). The owner's tolerance in the manifest is 0 ps, so `p2` and `p3` fail it.
- **A relocated block keeps its shape and its logic.** The routing of the relocated block has the same shape as the delivered one (route strings with the coordinates
  removed) in every relocation, and the fingerprint of its logical netlist (cell, configuration properties, connections) is equal to the delivered one's.
  `eqy` on the functional netlists of `p1` was started and stopped by us after about seven minutes without a result (it matches registers by name and proves each
  cone with SAT; the same 16-bit limit as stage 1); the fingerprint is an identity check, which is stronger for the same netlists and says nothing about different ones.
- **The boundary budgets caught two placements.** The contract's `block_to_sink` budget of 3.0 ns (set before any placement was measured) is met at the delivered
  placement (2.934 ns) and exceeded at `p0y` (3.017 ns: the sink held in a pblock beside the block, the arrangement the scripted agent session writes) and at `p3` (3.007 ns).
- **`built` is reached for the placements the project adopts** (`p0`, `p0x`, `p1`: `placements/placement_evidence.json`, `passed: true`), not for the set of all six
  (`passed: false`, four problems listed first in the file).

## Records

| File | Made by | Shows |
|---|---|---|
| `block/` | `designs/b102_managed_pr/scripts/produce_block.sh` | the supplier-side implementation of the block: Vivado log, run record (WNS 0.164 ns at 4.0 ns out of context) |
| `import_check.json` | `python3 flow/managed_placed.py check designs/b102_managed_pr --sim` | interface equals the contract, licence and hash recorded, 1,155 leaf cells with fixed location and BEL, 1,158 routed nets all with fixed routing, footprint inside the keep-out region, the functional netlist matches the supplier's RTL for 597 compared cycles |
| `import_fault.json` | the same simulation after flipping one LUT INIT bit | the planted fault fails the simulation (10 mismatches) |
| `placements/placement_evidence_all.json` | `designs/b102_managed_pr/scripts/run_placements.sh`, `run_dumps.sh`, then `python3 flow/managed_placed.py compare` | all six placements: per-placement verdicts, the four problems |
| `placements/placement_evidence.json` | `compare ... --only p0,p0x,p1` | the adopted placements: passed |
| `placements/*_run.json`, `*_block.csv`, `*_budgets.txt` | `flow/managed_placement_run.tcl` | whole-design WNS and hold, routing errors, the block-internal setup paths and the boundary budgets, per placement |
| `demo_session.json` | `python3 designs/b102_managed_pr/scripts/demo_managed_session.py --rapidwright <p0_routed.dcp>` | a scripted session through the agent's real tool surface: refusals of the keep-out, and the real RapidWright tools placing owned cells around the block |
| `builds.json`, `build_base/`, `boundary.json`, `trust.json` | `flow/run_vivado.sh designs/b102_managed_pr base` and `flow/managed_import.py` | the project's own flow build (gates, resources, timing) with the block read from its checkpoint, the boundary budgets, the computed trust labels |

Placements: `p0` the block as delivered; `p0x` the same with placer directive Explore; `p0y` the same with the sink in a pblock beside the block (`scripts/sink_pblock.xdc`);
`p1` relocated to `SLICE_X29Y20` (60 rows down: one clock region); `p2` to `SLICE_X29Y50` (30 rows down); `p3` to `SLICE_X5Y170` (another column). Relocation is RapidWright's
`RelocationTools` (`flow/rw/relocate.py`); the owned logic is placed and routed by Vivado 2026.1 around the locked block, one thread, KR260's `xck26-sfvc784-2LV-c`, 4.0 ns.

| Placement | block region (slice) | interconnect delays equal | largest difference | WNS (whole design) | `block_to_sink` budget (3.0 ns) |
|---|---|---|---|---|---|
| `p0` delivered | X27..34, Y72..90 | reference | | 0.061 ns | 2.934 ns |
| `p0x` Explore | same | 5,197 of 5,197 | 0 ps | 0.061 ns | 2.934 ns |
| `p0y` sink pblock | same | 5,197 of 5,197 | 0 ps | 0.066 ns | **3.017 ns** |
| `p1` one clock region down | X27..34, Y12..30 | 5,197 of 5,197 | 0 ps | 0.061 ns | 2.934 ns |
| `p2` half a region | X27..34, Y42..60 | 5,097 of 5,197 | 161 ps | 0.046 ns | 2.934 ns |
| `p3` another column | X3..10, Y162..180 | 3,385 of 5,197 | 275 ps | **-0.057 ns** | **3.007 ns** |

The endpoint-by-endpoint data-path delays that Vivado's `report_timing` gives (`*_block.csv`) differ even at `p0y` (48 of 579 endpoints, largest 42 ps) although the block's routing is
byte-identical: the worst-slack path to an endpoint depends on the clock tree Vivado builds around the block (a different source flop became the worst path), so the gate is the
clock-independent interconnect delay, and the path delays are recorded for information.

## Reproduce

`produce_block.sh`, `run_placements.sh` and `run_dumps.sh` need Vivado 2026.1, RapidWright (`tools/rapidwright_env/setup.sh`) and a heavy slot; about 45 minutes in all at one thread. The check and compare
steps are Python only (the simulation needs the OSS CAD Suite, `FDA_OSS_CAD`, and Icarus Verilog).

## Known gaps and limits

- One block (824 LUTs, 331 FFs, 744 SLICEM and 411 SLICEL sites), one device, six placements, one run each (Vivado's placer has no seed; the arms that differ only in surroundings agree exactly).
- The tolerance and the budget are the manifest's numbers: 0 ps and 3.0 ns, written before the measurements. A different tolerance changes which relocations are adoptable; the evidence file shows the differences to judge by.
- The keep-out is the supplier's pblock rectangle (SLICE_X26Y70:SLICE_X37Y91), larger than the block's footprint (X27..34, Y72..90); Vivado's own placer fills free slices inside it with owned logic (26 cells at `p0`). The keep-out binds the agent's tools and constraints, not Vivado.
- The scripted session is not a model; no LLM-driven run was made. No board was used.
- Whole-design WNS and hold are recorded, not gated by the evidence.
