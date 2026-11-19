# Managed projects (brief 102)

A **managed project** is the unit the agent works on when a design is more than the agent's own files: some parts the agent
may change, some it may only read, some it must not see, some arrive as netlists made by someone else. A manifest,
`project.yaml` in the design directory, says which is which. The rules are enforced in the agent's tools (the path jail every
file tool already goes through), not in a prompt, so a model cannot talk its way past them.

Stage 1 is the manifest, ownership, scoped requests, and RTL and netlist import. Stage 2 (placed-and-routed import, relocation with
RapidWright, a keep-out) and stage 3 (a real open-licence RTL block from outside, with its provenance) are described near the end.

## The manifest

`project.yaml`, schema `fda-managed-project/1` (code: `agent/core/managed.py`; a worked file: `designs/b102_managed_fcs/project.yaml`).

| Key | Meaning |
|---|---|
| `schema`, `name`, `top` | the schema id, a name, the top module |
| `unclaimed` | `owned` (default) or `frozen`: what a file in no component is |
| `approved_contract_changes` | components whose interface contract the owner has agreed to change (see Contracts) |
| `components[]` | one entry per part, below |

Each component:

| Key | Meaning |
|---|---|
| `name`, `module`, `instance` | its name, its module, its hierarchy path from the top (`u_core/u_mac`) |
| `ownership` | `owned`, `frozen` or `excluded` |
| `level` | `rtl`, `netlist`, `placed_routed`, `vendor_ip`, `encrypted_ip` |
| `paths` | design-relative patterns (`**` any depth, a directory means everything under it) |
| `build_sources` | the repo-relative files `build.yaml` must list for it |
| `netlist` | for a `netlist`: `{file, format: edif or checkpoint, cell (checkpoint), sim_file}` |
| `reference_rtl` | RTL the netlist must be proved equivalent to |
| `interface` | the contract: `ports` (name, dir, width), `clocks`, `resets`, `timing_budgets` (`{name, dir: out or in, max_ns}`) |
| `provenance` | `origin`, `version`, `licence`, `sha256` (of the netlist file), `tests` |
| `aliases` | words a free-text request may use for it |

There is no `trust` key: a declared trust is a validation error. The label is computed (below). The interface may also be
converted from IP-XACT (IEEE 1685-2014) with `managed.ipxact_ports`. A design with no `project.yaml` is unchanged; `managed.from_design`
converts one (a single owned component covering everything).

## Ownership, enforced in the tools

`agent/core/security.PathJail` holds a `ManagedPolicy` and calls it with the resolved, design-relative path (`..` and symlinks already
resolved). Every file tool, every role's narrowed jail (`RoleJail` keeps the policy) and `list_files` go through it.

| Ownership | read | write | listing |
|---|---|---|---|
| owned, in the request's scope | yes | yes | yes |
| owned, outside the scope | yes | **refused** (`managed-scope`) | yes |
| frozen | yes | **refused** | yes |
| excluded | **refused** | **refused** | hidden |

Also: `project.yaml` is the owner's (writing it is refused; reading it returns a filtered view with excluded components removed);
`build/managed/` evidence and scope records are the flow's; a hard-linked file refuses a write (a second name could alias a frozen
file); when patterns overlap, the strictest wins, so a broad owned pattern never unlocks a frozen or excluded file; and after any tool
that runs design code (`simulate`, `build`, `formal`, ...) the policy re-hashes frozen and excluded files, and a change makes the
result a `managed-integrity` refusal.

**Excluded never means out of the build.** The flow (`flow/prepare.py`, `flow/build.tcl`, the gates) never consults the policy: the whole
design is always built and signed off. A `build.yaml` that drops any component's sources or netlist is refused at write time and at
build time (`managed-build`).

Tests: `agent/tests/test_102_managed.py` (path tricks, symlinks, hard links, overlapping claims, role jails, code that rewrites a
frozen file, build.yaml coverage).

## Scoped requests

Every request, first or refining, has a **scope**: the components it may touch.

- `--scope crc,pcs_rx` names components or hierarchy paths (the component whose `instance` is the longest prefix wins); the default is
  every owned component.
- A free-text request is resolved to components by name, module, instance, or alias. An ambiguous request, or one that names only a
  frozen part, returns a **question** and no scope: nothing is edited until it is answered. An excluded component never matches (it
  answers like an unknown name).
- The plan lists the components it will touch (`build/managed/scope.json`: `will_touch`, `read_only`, `not_in_scope_owned`). Tools refuse
  edits outside the scope even inside owned components; widening needs a new explicit request. A refinement in a new run has its own
  scope, and the earlier ones are kept in `history`.
- The scope and the plan are in the run record (`scope.json`) and in the provenance report.

## Interface contracts at the scope boundary

A write to a file that declares a component's module is parsed (ANSI port lists, widths evaluated from parameter defaults) and compared
with the manifest's `interface.ports`. A difference is refused (`managed-contract`) and appended to `build/managed/contract_flags.jsonl`
for the owner, who approves it by listing the component under `approved_contract_changes`. The check is on the port list; a change of
behaviour behind the same ports is not a contract change here, and a non-ANSI port list is not read (a gap).

## Importing a block made elsewhere

`python3 flow/managed_import.py check designs/<d> --sim --eqy` runs, for each `level: netlist` component:

1. **interface**: the netlist's ports (EDIF or Verilog) against the contract;
2. **licence and provenance**: origin, version, licence, and the file's SHA-256 recorded and matching;
3. **simulation**: the functional netlist (Yosys netlists with the public cell models of the Yosys distribution; a Vivado post-synthesis or
   post-route netlist through `write_verilog -mode funcsim`, `managed_import.funcsim_tcl`) against a model;
4. **equivalence**: `eqy` proves the supplier's RTL equivalent to the netlist where both exist (registers matched by name).

The slot is a `(* black_box *)` module in the design and `netlists:` in `build.yaml`: an EDIF is read before `synth_design`
(`flow/build.tcl`), a checkpoint fills its cell after it (`read_checkpoint -cell`). An agent's `build.yaml` may name only the netlist
components of its own `project.yaml`. After a build, `managed_import.py boundary` filters the build's `report_cdc` rows to those touching the
slot (a crossing at the boundary), and `budget-tcl` writes the Tcl that measures the contract's boundary timing budgets on the routed
checkpoint.

## Trust labels

`documented` (origin, version, licence, hash match, a contract), `verified` (an evidence file written by the flow records the component's own
tests passing on its current content), `built` (verified, and a build in this project had every gate clean on the current content). Evidence
is in `build/managed/evidence/<component>.json`, which the agent cannot write, and names the content hash it covers: a changed file drops the label.

## Known gaps (stage 1)

- Excluded hides sources from the agent's tools, not from the reports of the whole-design build, and not the existence of the instance in
  the owned parent RTL.
- Hard links are refused only on write; an integrity re-hash catches changes by design code afterwards, it does not prevent them
  (a test running as the agent's own code can still write a frozen file before the re-hash; it is caught, not blocked).
- Code the agent wrote (tests, benchmarks, cocotb) runs as host code: it is not confined, so it can read an excluded file or write a frozen one;
  the re-hash after code-running tools (now also of `project.yaml` and the scope file) detects a write and refuses the result, it does not prevent
  or revert it, and nothing detects a read. The code-running tool list is kept by hand (`registry.CODE_RUNNING_TOOLS`).
- Evidence files are plain JSON in `build/managed/`: the agent's tools cannot write them, but code it ran could forge one. They are not signed.
- Constraints (`design.xdc`) are agent-owned: a false path over an excluded block's boundary is a timing exception the existing exceptions check
  reports, not something the managed policy forbids.
- A tool that answers "not available" for an excluded path and "no such file" for an absent one tells the agent which excluded paths exist.
- Free-text resolution is name and alias matching, not understanding; an unfamiliar phrasing gets a question.
- Interface checks cover port names, directions and widths; clock and reset contracts are recorded, and checked at the boundary only through
  the CDC filter. IP-XACT is converted for ports only (not bus interfaces or register maps).
- `vendor_ip` and `encrypted_ip` levels validate and are enforced the same way but have no import path yet (`placed_routed` has one since stage 2).

## Stage 2: a placed-and-routed block

A block can arrive already placed and routed: a checkpoint made outside the project and locked with `lock_design -level routing`. The
component is `level: placed_routed`, always `frozen` (the validator refuses `owned`), and carries a `placement` key next to its `netlist`:

```yaml
- name: blk
  ownership: frozen
  level: placed_routed
  module: pcs_unit
  instance: u_blk
  netlist: {file: ext/pcs_unit_p0.dcp, format: checkpoint, cell: u_blk}      # build.yaml netlists: fills the black-box slot after synthesis
  placement:
    lock: routing                                   # lock_design -level routing: placement and routing both fixed
    region: SLICE_X26Y70:SLICE_X37Y91               # the keep-out: slice columns and rows, inclusive
    anchor: SLICE_X29Y80                            # the anchor slice RapidWright relocates from
    timing_tolerance_ps: 0                          # the owner's number for "internal timing unchanged" across placements
```

**The build.** The flow already fills a black-box slot from a checkpoint after synthesis (`read_checkpoint -cell`, stage 1). Vivado then places
and routes the rest around the locked cells and nets: nothing new is needed in `flow/build.tcl`.

**The import check** (`python3 flow/managed_placed.py check designs/<d> [--sim]`, which runs `flow/managed_placed_check.tcl` in Vivado):

1. the checkpoint's ports equal the contract (name, direction, width) and the licence, version, origin and SHA-256 are recorded and match;
2. the lock is complete: every placeable leaf cell (GND and VCC have no site) has a fixed location and a fixed BEL, every routed signal net has
   fixed routing, nothing is unplaced or unrouted;
3. the footprint: every slice the block occupies is inside `placement.region`;
4. with `--sim`, the checkpoint's functional netlist (`write_verilog -mode funcsim`, flattened by Yosys with its public Xilinx primitive models) is
   simulated against the supplier's RTL (`reference_rtl`) on the same random stimulus, cycle by cycle; a run where the output never goes high does not pass.

**Keep-out, enforced in the tools.** A constraints file the agent writes (any `*.xdc`, checked in `ManagedPolicy.check_content`) is refused
(`managed-keepout`) if it has a pblock slice range or a `LOC` overlapping the region, or a placement property (`LOC`, `BEL`, `PBLOCK`, `IS_*_FIXED`,
`FIXED_ROUTE`, `DONT_TOUCH`) or `add_cells_to_pblock` on a cell of the block's instance. The RapidWright tools check their arguments: a cell pattern
for `rw_place_chain` that could select a cell inside the instance (including `*`) is refused, the script itself refuses a pattern that selects one of the
real cells and never targets a site inside the region, `rw_route mode full` is refused (RWRoute may re-route locked nets), a net inside the instance
is refused, and `rw_relocate_block` takes a `component` (the block as a whole, a candidate placement written under `build/<variant>/rw/`, the target
refused if it would cover another block's region), not a checkpoint that might contain the block. A change of the block's placement is the owner's:
the agent cannot write `project.yaml`.

**Placement evidence** (`designs/b102_managed_pr/scripts/run_placements.sh`, `flow/managed_placed.py compare`). For each placement tried the block is
the delivered checkpoint or one RapidWright relocated (`flow/rw/relocate.py`), the owned logic is placed and routed by Vivado around it
(`flow/managed_placement_run.tcl`), and the evidence records, from Vivado: that no cell of the block moved and no internal net's route string changed
(before `opt_design` against after `route_design`, then again from the written checkpoint, `flow/managed_block_dump.tcl`); that no cell of the rest of
the design sits in the keep-out region (moved with the block); that the relocated routing has the same shape as the delivered one (route strings
with coordinates removed); every block-internal path delay against the delivered placement's, in picoseconds; the boundary timing budgets; and that
`eqy` proves the relocated netlist equal to the delivered one. `passed` needs every check at every placement, with the delay differences inside
`timing_tolerance_ps`.

**Trust.** `built` needs the placement evidence for the current content, covering at least two placements, as well as the clean build. A changed
file drops the evidence.

## Known gaps (stage 2)

- The keep-out binds the agent's constraints and RapidWright arguments, not Vivado's placer: the region is the supplier's pblock rectangle, bigger than the
  block's footprint, and Vivado places owned logic in the free slices inside it. Clock-region pblocks, `LOC` on non-slice sites (DSP, block RAM) inside the
  rectangle, and Tcl that builds names or objects indirectly are not evaluated; the xdc check refuses a variable that captures the block's cells or nets and any
  wildcard that could select them, but it is a pattern check, not a Tcl interpreter. Vivado itself cannot move a locked cell.
- A cell pattern for `rw_place_chain` that names only leaf cells (`*/sh_reg*`) cannot be judged in Python; `flow/rw/place_chain.py` refuses it against the real cell names.
- `lock_problems` compares counts (fixed against routed); a net that is routed but not fixed could be hidden by one that is fixed but unrouted when the totals match.
- The import simulation compares the functional netlist with the supplier's RTL on random stimulus (597 compared cycles), not exhaustively; `eqy` was too slow on this block.
- Interconnect delays are compared at six placements of one block on one part; the tolerance is the owner's number and relocation off a clock-region multiple changes delays.
- The scripted session is not a model: no LLM-driven run on a managed project yet.

## Stage 3: a third-party RTL block

One real block from outside is a frozen `rtl` component: Alex Forencich's `lfsr.v` from verilog-ethernet (MIT), the parallel CRC/LFSR
that project's own FCS modules use, instantiated at CRC-32 settings inside our adapter. The design is `designs/b102_managed_ext`; the records
are in `results/102_stage3/`.

**What a third-party component carries.** A component whose `provenance` names `upstream_url` is asked for more than origin, version and licence
(`agent/core/managed.py` `third_party_gaps`; any gap makes the label `none`):

| `provenance` key | Meaning |
|---|---|
| `spdx` | the licence's SPDX id; only `Apache-2.0`, `MIT`, `BSD-2-Clause`, `BSD-3-Clause` are accepted |
| `upstream_url`, `commit` | the project and the exact 40-hex commit the files came from |
| `licence_file` | the licence text in the tree (the file's own header carries the copyright line too) |
| `files` | SHA-256 of every file of the component as received; each must equal the file now, and no file may be in the component without one |
| `upstream_paths` | where each file lives in the upstream, so the hashes can be re-checked against the source |

**What is vendored, and where.** Files are copied byte for byte under `third_party/<project>/` with the licence and authors files, and get a row in
`THIRD_PARTY_NOTICES.md`. Nothing of the supplier's is edited: our adapter (`rtl/crc32_d16.sv`, owned) adds the register, the restart and the enable
and gives the block the port list the sequencer uses. The Verilator lint warnings the unmodified file raises are waived for that file alone in
`lint/third_party.vlt`.

**The import check** (`python3 flow/managed_rtl_import.py check designs/<d> --upstream <clone of the upstream> --eqy`) runs the provenance checks; compares each file with
`git show <commit>:<path>` in a clone; checks the module's ports against the contract at the parameters the design instantiates it with
(`interface.parameters`); simulates the block alone against a Python model of one CRC-32 step at widths 8, 16, 32 and 64, and the adapter plus the
block against the register model; plants a fault in a copy of the block and requires both simulations to reject it; and, with `--eqy` (null here: it did not finish in 600 s), asks `eqy` to
prove the adapter plus the block equal to our own specification (`reference/crc32_d16.sv`, written without the block). A pass writes `verified`
evidence. Trust `built` then needs a clean build, as for any component.

**Not done by the import check.** The block's own upstream tests are not run: the only ones that cover it are MyHDL co-simulations of the Ethernet modules
that use it (`tb/test_axis_eth_fcs_*.py`), which need MyHDL's Icarus plug-in built from source. Our own simulations stand in for them.

Never open an issue or PR on the upstream project without the owner's yes (house rule on third-party repositories).
