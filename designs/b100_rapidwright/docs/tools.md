# The RapidWright agent tools: datasheet (brief 100)

Code: `agent/core/rapidwright_tools.py`; scripts: `flow/rw/`. Tests: `agent/tests/test_100_rapidwright.py`. Registered with the other flow tools
(schema version 1.13.0). **Offered to a role only with `FDA_RAPIDWRIGHT=1` and RapidWright installed** (`enabled()`); the MCP server lists
all registered tools but a stage's tool list decides what a role sees, and the stage lists do not include these, so earlier briefs' golden
requests are unchanged. The stage 2 runs name the tools explicitly.

## Common behaviour (what a user could guess wrong)

- **Inputs** are checkpoint **file names** (`^[A-Za-z0-9_-]{1,60}\.dcp$`) inside `build/<variant>/` (the flow writes `post_synth.dcp`, `post_route.dcp`);
  a path, `..`, or a missing file is refused (`refused: true`). **Outputs** are written to `build/<variant>/rw/<name>.dcp`; `build/` is read-only for
  `write_file`, so an agent cannot edit them.
- **Nothing here returns a RapidWright estimate as a result.** `rw_place_chain` prints RapidWright's own cost (`estimate_before`, `estimate_after`) marked
  "not a result"; the only tool that returns timing is `rw_referee`, which runs Vivado.
- **No tool takes a command, Tcl, a script or a path outside the design.** argv is fixed in the tool; cell patterns and net names are matched against
  an allow-list of characters.
- **Without RapidWright** (CI, a machine without the venv) every `rw_*` tool returns `ok: false` with the reason and runs nothing; `rw_status` says why.
- **Cost:** a call starts a JVM (about 1 GiB; about 3 GiB the first time it reads a checkpoint, because RapidWright starts a Vivado to make the
  checkpoint's EDIF readable). The caller's heavy-slot rule applies; the tools do not take a slot themselves.
- **Vivado on PATH:** the tools put the pinned Vivado (`flow/version_pin.py`) first on `PATH` for RapidWright. With another release first RapidWright refuses the
  checkpoint ("created with Vivado v2026.1 and cannot be opened in this version").
- **Run time** (K26, chain of 1.8k LUTs): `rw_place_chain` 15 to 75 s, `rw_route` full 13 s, `rw_referee` with `route=true` 3 to 5 min.

## Tools

| Tool | Arguments | Returns | Notes |
|---|---|---|---|
| `rw_status` | none | whether RapidWright is usable, versions | runs nothing |
| `rw_relocate_block` | `checkpoint`, `output`, `target_site` (`SLICE_X<n>Y<n>`) | `ok`, tile offset, bounding boxes, nets with routing before and after | moves the **whole checkpoint** as one block so that its anchor slice lands on `target_site`; `ok: false` when RapidWright says the column pattern at the target does not match. Targets that work are the anchor sites `getValidRelocationOptions` lists for the block |
| `rw_place_chain` | `checkpoint`, `output`, `cells` (fnmatch patterns), `anchor` (a GT channel or slice), `window_cols`, `window_rows`, `seed`, `iterations` | slices moved, nets un-routed, RapidWright's own cost (not a result) | moves whole slices (their LUT/FF packing kept) to free sites of the same type inside the window; slices with carry, LUT RAM or shift-register cells stay; nets of moved slices (clock and static nets too) lose their routing, the rest keep theirs; **the output needs `rw_referee` with `route=true`** |
| `rw_route` | `checkpoint`, `output`, `mode` (`full` or `nets`), `nets` | RWRoute wall time, nets with routing | `full` routes every net of a placed checkpoint with RWRoute, timing driven by its own delay estimate; `nets` un-routes and re-routes the named nets, then **locks only those that are fully routed** and leaves the others un-routed for Vivado |
| `rw_referee` | `checkpoint` (an `rw/` output or a flow checkpoint), `route` | worst setup and hold slack, LUT/FF, route status, DRC, and for the chain design the slack of three path classes | `route=true` runs Vivado's `route_design` first (needed after `rw_place_chain`); reports are written beside the checkpoint |

## Known limits

- `rw_relocate_block` stamps a block into the checkpoint it was implemented in; putting the moved block into a bigger design is a Vivado step
  (`read_checkpoint -cell`), done by the experiment scripts (`designs/b100_rapidwright/scripts/stamp.tcl`), not by a tool.
- A block with a wide input bus can be unstampable (input pins unreachable past the block's locked routes); see `design.md` section 6.
- `rw_referee`'s chain slacks assume the cell names of `chain_top` (`u_mac`, `u_pcs`, `u_gt`) and are omitted for other designs.
- Net names in `rw_route nets` must be RapidWright's: a few nets named in a Vivado report (for example `u_pcs/acc_reg[23]_0`) are not found and are listed in `missing`.
