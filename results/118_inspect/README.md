# Brief 118: inspect any implementation

`python -m flow inspect designs/<name> [--variant V] [--stage synth|opt|place|route] [--open] [--verify] [--rtl] [--schematic MODULE ...]`
([flow/inspect_build.py](../../flow/inspect_build.py), [flow/inspect_views.py](../../flow/inspect_views.py), tests
[flow/tests/test_118_inspect.py](../../flow/tests/test_118_inspect.py)) turns a finished build into something a person can open, with Vivado
(a project plus one `open_<stage>.tcl` per checkpoint) or without it (static HTML). It reads the build and writes only into
`build/<variant>/inspect/`; it never rebuilds and never programs a board.

## What it writes

| File | What |
|---|---|
| `INSPECT.md` | build stamp, build ID, git commit, staleness warning, the checkpoints, the exact commands, which Vivado view answers which question |
| `vivado_project/<design>_<variant>_<stamp>.xpr` | sources, constraints, IP (`.xci` of the build), the build's generics and part, one simulation set per `tb_*.sv`, `INSPECT_STAMP.txt` under Utility Sources |
| `open_<stage>.tcl` | opens the project, prints the staleness warning, `open_checkpoint`, then `start_gui` |
| `index.html`, `src/`, `schematics/` | hierarchy with utilisation, the worst setup and hold paths cell by cell, RTL pages with line anchors, module schematics |
| `make_project.tcl`, `verify.tcl`, `verify.json`, `inspect.json` | the project script, the proof it loads, a record |

## Checkpoints cannot be attached to the project (Vivado 2026.1, tested)

`add_files post_route.dcp` into a project makes it a source (file type Design Checkpoint). Then `launch_runs synth_1` fails with "No Verilog or VHDL
sources found in project" and `open_run synth_1` with "Run 'synth_1' has not been launched": there is no run to attach it to. What works, and what the
generated scripts do: with the project open, `open_checkpoint <dcp>` opens the checkpoint as its own design (about 38 s and 3.5 GB resident for the
10G design's routed checkpoint). Every view of the GUI then works on it.

## Stamp honesty

The stamp and the git commit come from `run.json`; the per-file SHA-256 from `manifest.json` are compared with the tree now, and the stamp is recomputed
over the same file list as `flow/prepare.py`. A difference, a commit change or a build made from a dirty tree gives a warning on the command line, in
`INSPECT.md`, at the top of `index.html`, on the source pages of the files that differ, in `INSPECT_STAMP.txt` and when `open_<stage>.tcl` runs.

## `post_opt.dcp` and `post_place.dcp`

`FDA_INSPECT_CKPTS=1 flow/run_vivado.sh designs/<name>` writes them (`flow/build.tcl`, procedure `fda_inspect_ckpt`; the place checkpoint is after
`phys_opt_design`). Unset, a build is unchanged: same files, same stamp, same stage times. One consequence: `flow/build.tcl` is covered by the build ID
(`flow/manifest.py`), so the build ID of every design changes once, as it does with any edit of `build.tcl`; stamps do not.
Cost, measured on `b2_mic_pdm` (Artix-7, 2 threads, 211 s build): `FLOW-INSPECT-CKPT post_opt 0.2s 292555 bytes`, `post_place 0.3s 458774 bytes`.
Not measured on the 10G design; the checkpoints there are 21 MB (synth) and 25 MB (route), so expect a few seconds and about 20 to 25 MB each.

## Trials (Vivado 2026.1, heavy slot held; `--verify --rtl`)

| Design | Checkpoints | Project | RTL elaborated | WNS per checkpoint |
|---|---|---|---|---|
| `b96_kr260_10g/rm_gp_bypass` (build of 2026-11-20 17:11, other worktree, not rebuilt) | synth, route | 71 files, 8 sim sets | OK | synth 0.684 ns, route 0.118 ns (matches `timing_worst_setup.rpt`) |
| `b2_mic_pdm` (built here with `FDA_INSPECT_CKPTS=1 FDA_XPROBE=1`) | synth, opt, place, route | 12 files, 1 sim set | OK | 5.330, 5.330, 4.354, 2.850 ns (route matches `timing_summary.rpt`) |

`open_place.tcl` (without `start_gui`) was run in batch: `INSPECT-OPEN-OK place checkpoint_post_place`. The GUI launch (`--open`) started Vivado
with the script but no screenshot could be taken on this machine, so the GUI itself is not verified.

## Browser views

`index.html`: stamp and staleness, checkpoints, hierarchy tree (largest first, filter box, module names link to the RTL line), worst setup and hold
paths with every cell and the module's RTL line, the ten worst paths of the timing summary, `xprobe.json` cross-probe and device map when the build
has it, schematics, RTL pages. No script or style from outside; one small inline script for the filter. Checked at 1100 px and 390 px: no page error,
no horizontal overflow. Static files rather than a navigator page: the navigator's token gate would add nothing to a read-only file.

Schematics: Yosys with the slang front end through `flow/checks/elab.py` (XPM macros, AMD primitives and IP become boxes), one level deep, drawn by
`netlistsvg` when installed (`FDA_NETLISTSVG`, `PATH`, or `~/.local/opt/netlistsvg`; it is not installed in a fixed place, install it with
`npm install netlistsvg`) and otherwise by a plain built-in drawing. Modules over 400 cells at one level are not drawn. It is the module as written in
today's tree with default parameters, not the netlist Vivado made.

## Records

- `b2_mic_pdm/` and `b96_rm_gp_bypass/`: for each trial, `INSPECT.md` (what each checkpoint holds and which Vivado view answers which question),
  `INSPECT_STAMP.txt` (build stamp, build ID and git commit the checkpoints came from), `verify.json` and `verify.log` (the batch run that loaded every
  checkpoint and elaborated the RTL, with the WNS read from each).

## Reproduce

```
python -m flow inspect designs/b2_mic_pdm --verify --rtl           # needs a finished build and a heavy slot for the Vivado part
python -m flow inspect designs/b96_kr260_10g/rm_gp_bypass --no-project   # browser views only, no Vivado
python -m pytest -q flow/tests/test_118_inspect.py
```

Any Vivado use takes a heavy slot (`FDA_HEAVY_SLOT` naming a held lock file, honouring `FDA_VIVADO_MAX`) and runs in a 6 GB scope.

## Known gaps and limits

- Vivado 2026.1 does not attach a `.dcp` to a project as a run result (tested); the generated `open_<stage>.tcl` scripts open each checkpoint with the
  project open instead (about 38 s and 3.5 GB for the 10G routed checkpoint).
- The GUI launch (`--open`) is not verified (no screen capture on this machine).
- `netlistsvg` has no fixed install location; without it a plain built-in drawing is used. Schematics are of today's RTL, one level deep, default
  parameters; modules over 400 cells at one level are skipped.
- A build-cache hit or a resume keeps the earlier build's checkpoints. `FDA_INSPECT_CKPTS=1` (post_opt and post_place checkpoints) was timed only on
  `b2_mic_pdm`.
