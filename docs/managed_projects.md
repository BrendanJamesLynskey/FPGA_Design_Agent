# Managed projects (brief 102)

A **managed project** is the unit the agent works on when a design is more than the agent's own files: some parts the agent
may change, some it may only read, some it must not see, some arrive as netlists made by someone else. A manifest,
`project.yaml` in the design directory, says which is which. The rules are enforced in the agent's tools (the path jail every
file tool already goes through), not in a prompt, so a model cannot talk its way past them.

Stage 1 (this page) is the manifest, ownership, scoped requests, and RTL and netlist import. Stage 2 (placed-and-routed import with
RapidWright) and stage 3 (integrating an open-licence block from outside) are planned at the end.

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
- `placed_routed`, `vendor_ip` and `encrypted_ip` levels validate and are enforced the same way but have no import path yet.

## Stage 2 plan: placed-and-routed import (after brief 100 merges)

Goal: import a placed-and-routed block, relocate it with RapidWright, and show its internal timing is unchanged across placements, with the
agent allowed to place around it and never inside it.

1. Component `level: placed_routed`, `netlist: {format: checkpoint, file: <routed .dcp>, cell}`; stage 1's import checks apply unchanged to
   the block's own interface and licence.
2. Lock it: `lock_design -level routing` on the block's checkpoint before it is read into the top (`read_checkpoint -cell`); the manifest
   records the lock level and the placement anchor (the site or Pblock). Frozen ownership already refuses edits to its files; the lock stops
   Vivado from changing its placement and routing.
3. Relocate with RapidWright (brief 100's tools): move the block to two or three other legal sites, re-read, route the rest.
4. Evidence: the block's internal paths (`report_timing -from/-to` cells inside it) are identical across placements (same delay to the
   picosecond, the same routing nodes hash from the brief 33 result-hash), and eqy (brief 101) proves the relocated netlist equals the original.
5. Agent policy: add a `pblock` keep-out to the contract, so placement tools may use the surrounding area and never the block's sites; a tool
   that moves a cell inside a placed-and-routed component is refused (`managed` rule, same jail path, applied to the RapidWright tool's arguments).
6. Trust: `built` requires the timing-unchanged evidence file for every placement tried.

## Stage 3 plan: integrating others' work

Goal: one real external block under Apache-2.0, MIT or BSD, with a provenance report that lists exactly what was theirs and what was ours; the
path for the recorded-demo intake (`docs/demo_intake.md`).

1. Choose a small, well-documented open block (a UART, a CRC or Ethernet MAC core, or a small RISC-V peripheral) whose licence permits redistribution
   and whose repository has tests; state the licence and cite the project, version and commit hash; copy it into `ext/` unmodified, with its
   licence text, as a frozen `rtl` component (or build it into a netlist with the stage 1 recipe).
2. Write its contract from its documentation (ports, clocks, resets, register map, in IP-XACT where the project ships it), run its own tests in
   this project (a `verified` label only if they pass here), and add the wrapper we own.
3. The provenance report (`managed.write_provenance`) already separates theirs from ours with hashes; stage 3 adds a line-count and file diff
   against the upstream commit (nothing of theirs modified) and the third-party notice in `THIRD_PARTY_NOTICES.md`.
4. The agent runs a task on the owned wrapper only; the report shows every file touched, and the managed refusals.
5. Never open an issue or PR on the upstream project without the owner's yes (house rule on third-party repositories).
