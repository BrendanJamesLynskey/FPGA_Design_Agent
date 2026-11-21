#!/usr/bin/env python3
"""Open a design's implementation: the Vivado state at each stage, and browser views for people without Vivado (brief 118).

    python -m flow inspect designs/<name> [--variant base] [--stage synth|opt|place|route] [--open] [--verify] [--rtl]
                           [--schematic MODULE ...] [--no-project] [--no-views] [--out DIR]

``flow/build.tcl`` already writes ``post_synth.dcp`` and ``post_route.dcp`` into ``designs/<name>/build/<variant>/`` (and, with
``FDA_INSPECT_CKPTS=1``, ``post_opt.dcp`` and ``post_place.dcp``). This command reads that build and writes, next to it, in
``build/<variant>/inspect/`` (default; git-ignored with the build):

* ``INSPECT.md``: what each checkpoint holds, which Vivado view answers which question, the exact commands, the build stamp and the
  git commit the checkpoints came from, and a staleness warning;
* a Vivado project ``vivado_project/<design>_<variant>_<stamp>.xpr`` (sources, constraints, IP, simulation sets, the build's generics
  and part), made by running Vivado in batch mode (``--no-project`` writes only the Tcl);
* ``open_<stage>.tcl``: opens that project and that stage's checkpoint, prints the staleness warning (``--open`` runs it in the GUI);
* ``index.html`` and its pages (no Vivado needed, no network, no script from outside): hierarchy with utilisation, the worst timing
  paths with their cells, RTL source pages with line anchors, and schematics of chosen modules.

Checkpoints cannot be attached to a project as run results: Vivado 2026.1 accepts a ``.dcp`` as a source but then has no RTL for
``launch_runs`` and no run to open (tested, ``results/118_inspect/README.md``). So the project holds the design, and each stage is one
``open_checkpoint`` away; the generated scripts do exactly that.

A checkpoint is a snapshot of the commit that built it, not of today's RTL: the stamp and commit are recorded and the sources are
compared (per-file SHA-256 from the build manifest) with the working tree, in INSPECT.md, in the project (``INSPECT_STAMP.txt``,
the project's name) and in what ``open_<stage>.tcl`` prints.

Vivado use (project generation, ``--verify``, ``--open``) is a heavy job: take a slot first
(``_handoff/take_heavy_slot.sh --env "<prefix>: ..."``) and ``export FDA_HEAVY_SLOT=$HEAVY_LOCK``; the command refuses without it, refuses when
``FDA_VIVADO_MAX`` Vivado jobs already run, and runs Vivado in a 6 GB scope. It never programs a board.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

#: stage name -> (checkpoint file, what it holds)
STAGES = {
    "synth": ("post_synth.dcp", "the netlist after synth_design, with the constraints and the scoped XPM CDC constraints applied; not placed"),
    "opt": ("post_opt.dcp", "after opt_design (only builds made with FDA_INSPECT_CKPTS=1); not placed"),
    "place": ("post_place.dcp", "after place_design and phys_opt_design, before routing (only builds made with FDA_INSPECT_CKPTS=1); "
                                "net delays are estimates"),
    "route": ("post_route.dcp", "placed and routed: the design the bitstream was written from; timing is final"),
}
SRC_EXT = (".sv", ".v", ".svh", ".vh", ".vhd", ".vhdl")
VERSION = "1"


class InspectError(RuntimeError):
    pass


# --- locating the build ---------------------------------------------------------------------------------------------------------------
def _tcl_items(text: str) -> list[str]:
    return re.findall(r"\{([^{}]*)\}", text)


def parse_inputs_tcl(path: Path) -> dict[str, list[str] | str]:
    """The ``set name value`` lines of inputs.tcl (flow/prepare.py): lists as lists of strings, anything else as the raw text."""
    out: dict[str, list[str] | str] = {}
    for line in path.read_text().splitlines():
        m = re.match(r"set (\w+) (.*)$", line)
        if not m:
            continue
        name, val = m.groups()
        val = val.strip()
        if val.startswith("[list"):
            out[name] = _tcl_items(val)
        elif val.startswith("{") and val.endswith("}") and "{" not in val[1:-1]:
            out[name] = val[1:-1]
        else:
            out[name] = val
    return out


class Build:
    """One finished build directory and what it says about itself."""

    def __init__(self, design: str | Path, variant: str = "base"):
        p = Path(design)
        cands = [p] if p.is_absolute() else [Path.cwd() / p, Path(__file__).resolve().parents[1] / p, Path(__file__).resolve().parents[1] / "designs" / p]
        found = next((c for c in cands if (c / "build" / variant / "prepare.json").is_file()), None)
        if found is None:
            raise InspectError(f"no finished build for {design!r} variant {variant!r}: looked for build/{variant}/prepare.json under "
                               + ", ".join(str(c) for c in cands) + ". Build it first: flow/run_vivado.sh designs/<name>")
        self.dir = found.resolve() / "build" / variant
        self.variant = variant
        self.prep = json.loads((self.dir / "prepare.json").read_text())
        self.design_rel = self.prep["design"]
        # the repo root is the design directory with its repo-relative path taken off
        d = found.resolve()
        self.root = d
        for _ in Path(self.design_rel).parts:
            self.root = self.root.parent
        self.design_dir = d
        self.name = Path(self.design_rel).name
        self.run = json.loads((self.dir / "run.json").read_text()) if (self.dir / "run.json").is_file() else {}
        self.manifest = json.loads((self.dir / "manifest.json").read_text()) if (self.dir / "manifest.json").is_file() else {}
        self.inputs = parse_inputs_tcl(self.dir / "inputs.tcl") if (self.dir / "inputs.tcl").is_file() else {}
        self.tool = {}
        if (self.dir / "tool.txt").is_file():
            for ln in (self.dir / "tool.txt").read_text().splitlines():
                k, _, v = ln.partition(" ")
                self.tool[k] = v

    # the build-time absolute path of a file -> its path in this tree (the build may have been made in another worktree)
    def remap(self, p: str) -> Path:
        out_t = self.inputs.get("out")
        if isinstance(out_t, str):
            build_root = Path(out_t)
            for _ in Path(self.design_rel).parts + ("build", self.variant):
                build_root = build_root.parent
            try:
                return self.root / Path(p).relative_to(build_root)
            except ValueError:
                pass
        return Path(p)

    def listed(self, key: str) -> list[Path]:
        v = self.inputs.get(key, [])
        return [self.remap(x) for x in v] if isinstance(v, list) else []

    @property
    def stamp(self) -> str:
        return self.prep.get("build_stamp", "")

    @property
    def tag(self) -> str:
        return f"{self.name}_{self.variant}_{self.stamp}"

    def checkpoints(self) -> dict[str, dict]:
        out = {}
        for st, (fn, what) in STAGES.items():
            f = self.dir / fn
            out[st] = {"file": f, "what": what, "exists": f.is_file(), "bytes": f.stat().st_size if f.is_file() else 0,
                       "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime)) if f.is_file() else ""}
        return out


# --- stamp honesty --------------------------------------------------------------------------------------------------------------------
def _git(root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _sha(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def stamp_report(b: Build) -> dict:
    """The recorded stamp and commit, the current ones, which input files differ, and warnings. Pure reading; no Vivado."""
    rec_commit = b.run.get("git_commit")
    head = _git(b.root, "rev-parse", "HEAD")
    changed, missing = [], []
    for rel, h in (b.manifest.get("inputs") or {}).items():
        cur = _sha(b.root / rel)
        if cur is None:
            missing.append(rel)
        elif cur != h:
            changed.append(rel)
    # prepare.py's stamp over the same file list, recomputed
    cur_stamp = None
    files = b.prep.get("files") or []
    if files and all((b.root / f).is_file() for f in files):
        h = hashlib.sha256()
        for f in files:
            h.update(f.encode() + b"\0" + (b.root / f).read_bytes() + b"\0")
        cur_stamp = h.hexdigest()
    n_between = None
    if rec_commit and head and rec_commit != head:
        n = _git(b.root, "rev-list", "--count", f"{rec_commit}..{head}")
        n_between = int(n) if n and n.isdigit() else None
    warns = []
    if not b.manifest:
        warns.append("the build has no manifest.json: per-file comparison is not possible, only the stamp")
    if changed or missing:
        warns.append(f"{len(changed)} input file(s) differ from the build and {len(missing)} are missing in this tree: the checkpoints do not "
                     "show today's RTL (" + ", ".join((changed + missing)[:6]) + (" ..." if len(changed + missing) > 6 else "") + ")")
    elif cur_stamp and b.prep.get("sources_sha256") and cur_stamp != b.prep["sources_sha256"]:
        warns.append("the sources' stamp differs from the build's (the file list or contents changed)")
    if rec_commit and head and rec_commit != head:
        warns.append(f"the build was made at commit {rec_commit[:10]}, this tree is at {head[:10]}"
                     + (f" ({n_between} commit(s) later)" if n_between is not None else " (the build's commit is not in this tree's history)"))
    if b.run.get("git_dirty"):
        warns.append("the build was made from a tree with uncommitted changes: the commit alone does not reproduce it; the manifest's file hashes do")
    return {"build_stamp": b.stamp, "sources_sha256": b.prep.get("sources_sha256"), "build_id": b.run.get("build_id") or b.manifest.get("build_id"),
            "recorded_commit": rec_commit, "recorded_dirty": bool(b.run.get("git_dirty")), "current_commit": head, "commits_later": n_between,
            "changed_files": changed, "missing_files": missing, "stamp_matches_tree": bool(cur_stamp and cur_stamp == b.prep.get("sources_sha256")),
            "vivado": b.run.get("vivado_version") or b.tool.get("version"), "warnings": warns, "stale": bool(changed or missing)}


# --- the project ----------------------------------------------------------------------------------------------------------------------
def _braced(p: object) -> str:
    return "{" + str(p) + "}"


def sim_benches(b: Build) -> list[dict]:
    """The design's simulation benches: every ``tb_*.sv`` under sim/ and tests/ (of the design and of the design it is nested in), each with
    the non-bench files of its sim/ folder (first definition of a module wins, so alternative models do not clash)."""
    dirs = [b.design_dir]
    par = b.design_dir.parent
    if par.name != "designs" and (par / "build.yaml").is_file():
        dirs.append(par)
    benches = []
    for d in dirs:
        helpers = []
        for sub in ("sim",):
            helpers += sorted(f for f in (d / sub).glob("*.sv") if not f.name.startswith("tb_")) if (d / sub).is_dir() else []
        for sub in ("sim", "tests"):
            for tb in sorted((d / sub).glob("tb_*.sv")) if (d / sub).is_dir() else []:
                text = tb.read_text(errors="replace")
                m = re.search(r"^\s*module\s+(\w+)", text, re.M)
                if not m:
                    continue
                files, seen = [tb], {m.group(1)}
                for h in helpers:
                    mods = set(re.findall(r"^\s*module\s+(\w+)", h.read_text(errors="replace"), re.M))
                    if mods and not (mods & seen):
                        files.append(h)
                        seen |= mods
                benches.append({"name": tb.stem, "top": m.group(1), "files": files})
    return benches


def project_tcl(b: Build, out: Path, benches: list[dict]) -> str:
    srcs = [p for p in b.listed("sources")]
    xdc = b.listed("constraints")
    xci = sorted((b.dir / "ip").rglob("*.xci")) if (b.dir / "ip").is_dir() else []
    data = [b.root / f for f in b.prep.get("files", [])
            if not f.endswith(SRC_EXT + (".xdc", ".tcl", ".xci")) and (b.root / f).is_file()]
    gens = b.inputs.get("generics", [])
    proj_dir = out / "vivado_project"
    L = [f"# Generated by flow/inspect_build.py (brief 118) from {b.dir}.",
         f"# Build stamp {b.stamp}, git commit {b.run.get('git_commit')}{' (uncommitted changes)' if b.run.get('git_dirty') else ''}, Vivado {b.run.get('vivado_version')}.",
         "# A project of the design as built: sources, constraints, IP, simulation sets. The checkpoints are opened with open_<stage>.tcl.",
         f"create_project -force {b.tag} {_braced(proj_dir)} -part {b.prep['part']}",
         "set_property target_language Verilog [current_project]",
         "set_property source_mgmt_mode All [current_project]"]
    for f in srcs:
        L.append(f"add_files -norecurse -fileset sources_1 {_braced(f)}")
        if f.suffix == ".sv":
            L.append(f"set_property file_type SystemVerilog [get_files {_braced(f)}]")
        elif f.suffix in (".vhd", ".vhdl"):
            L.append(f"set_property file_type {{VHDL 2008}} [get_files {_braced(f)}]")
    for f in xci:
        L.append(f"add_files -norecurse -fileset sources_1 {_braced(f)}")
    for f in data:
        L.append(f"add_files -norecurse -fileset sources_1 {_braced(f)}")
    for f in xdc:
        L.append(f"add_files -norecurse -fileset constrs_1 {_braced(f)}")
    L.append(f"set_property top {b.prep['top']} [get_filesets sources_1]")
    if gens:
        L.append("set_property generic " + _braced(" ".join(gens)) + " [get_filesets sources_1]")
    L.append("update_compile_order -fileset sources_1")
    # the stamp travels with the project: a utility file, and the project's own name
    L.append(f"add_files -norecurse -fileset utils_1 {_braced(out / 'INSPECT_STAMP.txt')}")
    for i, bn in enumerate(benches):
        sset = "sim_1" if i == 0 else f"sim_{bn['name']}"
        if i:
            L.append(f"create_fileset -simset {sset}")
        for f in bn["files"]:
            L.append(f"add_files -norecurse -fileset {sset} {_braced(f)}")
            L.append(f"set_property file_type SystemVerilog [get_files -of_objects [get_filesets {sset}] {_braced(f)}]")
        L.append(f"set_property top {bn['top']} [get_filesets {sset}]")
    L.append("# the IP in the build was made by the design's ip_tcl (flow/build.tcl); the .xci above is that output")
    L.append("puts \"INSPECT-PROJECT-OK [current_project]\"")
    L.append("close_project")
    return "\n".join(L) + "\n"


def open_tcl(b: Build, out: Path, stage: str, st: dict, gui: bool) -> str:
    xpr = out / "vivado_project" / f"{b.tag}.xpr"
    commit = b.run.get("git_commit") or ""
    L = [f"# Generated by flow/inspect_build.py (brief 118): open the project and the {stage} checkpoint of {b.design_rel} ({b.variant}).",
         f"#   vivado -mode tcl -source {out}/open_{stage}.tcl      (batch proof: vivado -mode batch -source ... )",
         f"# Build stamp {b.stamp}, git commit {commit[:10]}. The checkpoint is that build's snapshot, not today's RTL.",
         "set fda_cp " + _braced(st["file"]),
         "set fda_commit " + _braced(commit),
         "set fda_root " + _braced(b.root),
         "if {[catch {exec git -C $fda_root rev-parse HEAD} fda_head]} { set fda_head unknown }",
         f"puts \"INSPECT: {stage} checkpoint of build stamp {b.stamp} (git $fda_commit)\"",
         "if {$fda_commit ne \"\" && $fda_head ne $fda_commit} { puts \"INSPECT-WARNING: this tree is at [string range $fda_head 0 9]; the checkpoint was built from [string range $fda_commit 0 9]. Read INSPECT.md before comparing it with today's RTL.\" }",
         f"open_project {_braced(xpr)}",
         "open_checkpoint $fda_cp",
         f"puts \"INSPECT-OPEN-OK {stage} [current_design]\""]
    if gui:
        L.append("start_gui")
    return "\n".join(L) + "\n"


QUESTIONS = [
    ("What is the netlist after synthesis, as a schematic?", "synth (or any later stage)", "Open the checkpoint, then Netlist > the top > Schematic, or select a cell and press F4. Flow Navigator > Synthesis > Schematic."),
    ("Which module uses the area?", "route", "Report Utilization > Hierarchical (also in the browser view, Hierarchy). In the GUI: Netlist window, columns for LUT/FF/BRAM."),
    ("Where did the placer put it?", "place or route", "Window > Device. Select a module in the Netlist window, then Mark (Ctrl+M); Windows > Floorplanning > Clock regions."),
    ("What are the worst paths, with their cells and nets?", "route", "Report Timing Summary, then double-click a path; Properties shows each cell's LOC, file and line. The browser view lists the same paths with RTL links."),
    ("Is the placed estimate close to the routed result?", "place and route", "Report Timing Summary on each; compare WNS. Estimated net delay at the place stage is pessimistic or optimistic by design (UG949 ch. 6)."),
    ("Which clock crossings are unsafe or unconstrained?", "synth or route", "Report CDC (full detail), Report Clock Interaction, Report Exceptions; the build's cdc*.rpt are the same reports."),
    ("What did the constraints reach?", "synth", "Report Timing Summary > Check Timing; Constraints Wizard; the build's check_timing*.rpt."),
    ("What does the RTL elaborate to (before any mapping)?", "project (RTL)", "In the project: Flow Navigator > RTL Analysis > Open Elaborated Design > Schematic."),
    ("Does the design simulate?", "project", "Flow Navigator > Simulation; the sim sets are the design's own benches. The tests under tests/ are the reference recipe."),
]


def inspect_md(b: Build, out: Path, cps: dict, st: dict, benches: list[dict], proj_made: bool, verify: dict | None, views: dict | None) -> str:
    L = [f"# Inspecting {b.design_rel} ({b.variant})", "",
         "Generated by `python -m flow inspect` (brief 118). Read-only: it never rebuilds, never programs a board.", "",
         "## Which build this is", "",
         f"- build stamp `{st['build_stamp']}` (first 8 hex digits of the SHA-256 over the build's sources), build ID `{st['build_id']}`",
         f"- git commit `{st['recorded_commit']}`{' with uncommitted changes' if st['recorded_dirty'] else ''}",
         f"- Vivado {st['vivado']}, part {b.prep['part']}, top `{b.prep['top']}`, board `{b.prep.get('board')}`",
         f"- build directory `{b.dir}`", ""]
    L += ["## Is it still today's RTL?", ""]
    if st["warnings"]:
        L += [f"**WARNING: {w}**" for w in st["warnings"]]
        L += [""]
    else:
        L += ["Yes: every input file matches the build's manifest and the tree is at the same commit.", ""]
    L += [f"- sources' stamp recomputed over the current tree matches the build's: {st['stamp_matches_tree']}", ""]
    L += ["A checkpoint is a snapshot of the commit that built it. Where this says the tree has changed, schematics and source pages made from",
          "the current tree show different RTL from what the checkpoint holds; trust the checkpoint for what was built.", ""]
    L += ["## The checkpoints", "", "| Stage | File | Holds | Size | Written |", "|---|---|---|---|---|"]
    for s, c in cps.items():
        L.append(f"| {s} | `{c['file'].name}` | {c['what']} | " + (f"{c['bytes'] / 1e6:.1f} MB | {c['mtime']} |" if c["exists"] else "not in this build | |"))
    if not (cps["opt"]["exists"] and cps["place"]["exists"]):
        L += ["", "`post_opt.dcp` and `post_place.dcp` are written only by builds made with `FDA_INSPECT_CKPTS=1 flow/run_vivado.sh ...` (an ordinary build is "
              "unchanged: same stamp, same time). A build that was a cache hit or a resume keeps the checkpoints of the build it came from."]
    L += ["", "## Open it", "", "A heavy job (Vivado): take a slot first.", "", "```",
          'eval "$(/home/brendan/Claude_sandbox/_handoff/take_heavy_slot.sh --env "<prefix>: inspect, <start>, expected end <hh:mm>, peak 4G")"',
          "export FDA_HEAVY_SLOT=$HEAVY_LOCK", f"python -m flow inspect {b.design_rel} --variant {b.variant} --stage route --open", "```", "",
          "That runs the generated script in the GUI. By hand:", "", "```"]
    for s, c in cps.items():
        if c["exists"]:
            L.append(f"vivado -mode tcl -source {out}/open_{s}.tcl     # {s}: opens the project, then the {s} checkpoint, then the GUI")
    L += ["```", "", "The script opens the project and then the checkpoint (`open_checkpoint`); Vivado shows the checkpoint as a separate design next to the project's "
          "own runs. **Attaching a checkpoint to the project as a run result is not possible in 2026.1**: a `.dcp` added as a source leaves `launch_runs synth_1` "
          "with \"No Verilog or VHDL sources found\" and `open_run` with \"has not been launched\" (tested). Memory: about 3.5 GB resident for the route checkpoint of the 10G design.", ""]
    L += ["## The project", ""]
    if proj_made:
        L += [f"`vivado_project/{b.tag}.xpr`: sources ({len(b.listed('sources'))} files), constraints, the IP (`.xci` from the build), the build's generics "
              f"(`{' '.join(b.inputs.get('generics', []))}`), top `{b.prep['top']}`, and `INSPECT_STAMP.txt` under Utility Sources."]
    else:
        L += [f"Not generated this time. `make_project.tcl` makes it: `vivado -mode batch -source {out}/make_project.tcl` (heavy slot)."]
    L += ["", "Simulation sets (one per bench; each lists the bench and the non-bench files of its `sim/` folder, the first definition of a module winning, so a "
          "project's set may differ from the recipe in the design's tests, which stay the reference):", ""]
    L += [f"- `{bn['name']}` (top `{bn['top']}`): " + ", ".join(f"`{f.name}`" for f in bn["files"]) for bn in benches] or ["- none found"]
    L += ["", "## Which view answers which question", "", "| Question | Stage | Where |", "|---|---|---|"]
    L += [f"| {q} | {s} | {w} |" for q, s, w in QUESTIONS]
    L += ["", "## Without Vivado", "", f"Open `{out}/index.html` in a browser: hierarchy and utilisation, worst setup and hold paths with their cells, RTL source pages, "
          "schematics. Static files, no network, nothing to run; read-only. Regenerate with `python -m flow inspect ... --no-project`.", ""]
    if views:
        L += [f"- reports read: {', '.join(views['reports'])}", f"- schematics: " + (", ".join(views["schematics"]) or "none"),
              *(f"- schematic note: {n}" for n in views.get("notes", []))]
    if verify:
        L += ["", "## Proof that it loads", "", f"`--verify` ran at {verify['at']} in Vivado {verify['vivado']}: "
              + "; ".join(f"{k}: {v}" for k, v in verify["results"].items()) + f". Log: `{verify['log']}`."]
    L += ["", "## What this is not", "", "- Not a rebuild: no result changes, no new build stamp.",
          "- Not a way to edit the design: edits in the project do not reach the repository's flow.",
          "- The project's runs (synth_1, impl_1) are Vivado's project flow, not the repository's non-project flow (flow/build.tcl): re-running them can give a different result.", ""]
    return "\n".join(L)


# --- running Vivado (a heavy job) -----------------------------------------------------------------------------------------------------
def vivado_path() -> str:
    try:
        r = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "version_pin.py"), "--vivado"], capture_output=True, text=True, timeout=60)
        p = r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        p = ""
    p = os.environ.get("VIVADO") or p
    if not p or not Path(p).is_file():
        raise InspectError("Vivado not found: set VIVADO to the Vivado binary (python3 flow/version_pin.py --vivado prints the pinned path)")
    return p


def vivado_guard() -> None:
    """The heavy-slot rules, in code: a slot held (FDA_HEAVY_SLOT names its lock file), a free Vivado seat, memory."""
    lock = os.environ.get("FDA_HEAVY_SLOT", "")
    if not lock or not Path(lock).is_file():
        raise InspectError("Vivado is a heavy job: take a slot first (_handoff/take_heavy_slot.sh --env \"<prefix>: ...\") and export FDA_HEAVY_SLOT=$HEAVY_LOCK")
    mx = os.environ.get("FDA_VIVADO_MAX", "1")
    mx = min(2, max(1, int(mx))) if mx.isdigit() else 1
    if os.environ.get("FDA_TEST_VIVADO_RUNNING"):
        n = int(os.environ["FDA_TEST_VIVADO_RUNNING"])
    else:
        ps = subprocess.run(["pgrep", "-af", "unwrapped/lnx64.o/vivado"], capture_output=True, text=True).stdout.splitlines()
        # the real binary only: argv[0] is .../unwrapped/lnx64.o/vivado (a shell that merely mentions the path, as a waiting loop does, is not one)
        n = sum(1 for ln in ps if "task_worker.tcl" not in ln and ln.split(None, 1)[1:] and ln.split(None, 1)[1].split()[0].endswith("unwrapped/lnx64.o/vivado"))
    if n >= mx:
        raise InspectError(f"{n} Vivado job(s) running, limit FDA_VIVADO_MAX={mx} on this PC")
    avail = 0
    for ln in Path("/proc/meminfo").read_text().splitlines():
        if ln.startswith("MemAvailable:"):
            avail = int(ln.split()[1])
    if avail < 7 * 1024 * 1024:
        raise InspectError(f"only {avail // 1024} MiB available, need 7 GiB")


def run_vivado(tcl: Path, log: Path, mode: str = "batch", timeout: int = 3600) -> int:
    vivado_guard()
    cmd = ["systemd-run", "--user", "--scope", "-p", "MemoryMax=6G", "nice", "-n", "15", vivado_path(), "-mode", mode, "-nojournal", "-nolog", "-source", str(tcl)]
    if mode == "tcl":
        r = subprocess.run(cmd, stdin=None)
        return r.returncode
    with log.open("w") as fh:
        r = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, timeout=timeout)
    return r.returncode


def verify_tcl(b: Build, out: Path, cps: dict, rtl: bool) -> str:
    xpr = out / "vivado_project" / f"{b.tag}.xpr"
    L = [f"open_project {_braced(xpr)}", "puts \"INSPECT-VERIFY project [current_project] top=[get_property top [current_fileset]] files=[llength [get_files -quiet]] sims=[llength [get_filesets -filter {FILESET_TYPE==SimulationSrcs}]]\""]
    if rtl:
        L += ["if {[catch {synth_design -rtl -rtl_skip_ip -name rtl_1} e]} { puts \"INSPECT-VERIFY rtl FAIL $e\" } else { puts \"INSPECT-VERIFY rtl OK cells=[llength [get_cells -hier -filter {IS_PRIMITIVE==0} -quiet]]\"; close_design }"]
    for s, c in cps.items():
        if c["exists"]:
            L += [f"if {{[catch {{open_checkpoint {_braced(c['file'])}}} e]}} {{ puts \"INSPECT-VERIFY {s} FAIL $e\" }} else {{",
                  f"  puts \"INSPECT-VERIFY {s} OK design=[current_design] part=[get_property PART [current_design]] cells=[llength [get_cells -hier -filter {{IS_PRIMITIVE==0}} -quiet]]\"",
                  "  set wns [lindex [get_property SLACK [get_timing_paths -max_paths 1 -setup -quiet]] 0]",
                  f"  puts \"INSPECT-VERIFY {s} WNS=$wns\"", "  close_design }"]
    L += ["close_project"]
    return "\n".join(L) + "\n"


# --- the command ----------------------------------------------------------------------------------------------------------------------
def inspect(design: str, variant: str = "base", stage: str | None = None, out: Path | None = None, project: bool = True, views: bool = True,
            verify: bool = False, rtl: bool = False, schematics: list[str] | None = None, open_gui: bool = False) -> dict:
    b = Build(design, variant)
    out = (out or (b.dir / "inspect")).resolve()
    out.mkdir(parents=True, exist_ok=True)
    cps = b.checkpoints()
    present = [s for s, c in cps.items() if c["exists"]]
    if not present:
        raise InspectError(f"{b.dir} has no checkpoint (post_synth.dcp / post_route.dcp): the build did not reach synthesis")
    if stage and stage not in STAGES:
        raise InspectError(f"--stage must be one of {', '.join(STAGES)}")
    if stage and not cps[stage]["exists"]:
        raise InspectError(f"this build has no {STAGES[stage][0]} (present: {', '.join(present)})"
                           + ("; make one with FDA_INSPECT_CKPTS=1 flow/run_vivado.sh" if stage in ("opt", "place") else ""))
    st = stamp_report(b)
    for w in st["warnings"]:
        print(f"inspect: WARNING: {w}", file=sys.stderr)
    benches = sim_benches(b)
    (out / "INSPECT_STAMP.txt").write_text(
        f"design {b.design_rel} variant {b.variant}\nbuild stamp {st['build_stamp']}\nbuild id {st['build_id']}\ngit commit {st['recorded_commit']}"
        f"{' (uncommitted changes)' if st['recorded_dirty'] else ''}\nVivado {st['vivado']}\nsources sha256 {st['sources_sha256']}\n"
        + "".join(f"WARNING {w}\n" for w in st["warnings"]) + "The checkpoints are a snapshot of that build, not of today's RTL.\n")
    (out / "make_project.tcl").write_text(project_tcl(b, out, benches))
    for s in present:
        (out / f"open_{s}.tcl").write_text(open_tcl(b, out, s, cps[s], gui=True))
    proj_made = False
    verify_rec = None
    xpr = out / "vivado_project" / f"{b.tag}.xpr"
    if project:
        shutil.rmtree(out / "vivado_project", ignore_errors=True)
        rc = run_vivado(out / "make_project.tcl", out / "make_project.log")
        proj_made = rc == 0 and xpr.is_file()
        if not proj_made:
            raise InspectError(f"Vivado did not make the project (exit {rc}); see {out / 'make_project.log'}")
    elif xpr.is_file():
        proj_made = True
    if verify:
        if not proj_made:
            raise InspectError("--verify needs the project: run without --no-project first")
        (out / "verify.tcl").write_text(verify_tcl(b, out, cps, rtl))
        rc = run_vivado(out / "verify.tcl", out / "verify.log")
        text = (out / "verify.log").read_text(errors="replace")
        res = {}
        for m in re.finditer(r"(?m)^INSPECT-VERIFY (\S+) (.*)", text):
            res.setdefault(m.group(1), []).append(m.group(2).strip())
        verify_rec = {"at": time.strftime("%Y-%m-%d %H:%M"), "vivado": st["vivado"], "exit": rc, "log": str(out / "verify.log"),
                      "results": {k: " ".join(v) for k, v in res.items()}}
        (out / "verify.json").write_text(json.dumps(verify_rec, indent=1))
    vinfo = None
    if views:
        from flow import inspect_views
        vinfo = inspect_views.write_views(b, out, cps, st, schematics or [])
    (out / "INSPECT.md").write_text(inspect_md(b, out, cps, st, benches, proj_made, verify_rec, vinfo))
    (out / "inspect.json").write_text(json.dumps({"schema": "fda-inspect/1", "design": b.design_rel, "variant": b.variant, "stamp": st,
                                                 "checkpoints": {s: {"file": str(c["file"]), "exists": c["exists"], "bytes": c["bytes"]} for s, c in cps.items()},
                                                 "project": str(xpr) if proj_made else None, "verify": verify_rec}, indent=1))
    if open_gui:
        pick = stage or ("route" if cps["route"]["exists"] else present[-1])
        if not proj_made:
            raise InspectError("--open needs the project: run without --no-project")
        run_vivado(out / f"open_{pick}.tcl", out / "open.log", mode="tcl")
    return {"out": str(out), "stamp": st, "project": str(xpr) if proj_made else None, "checkpoints": present, "verify": verify_rec}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m flow inspect", description=__doc__.split("\n")[0])
    ap.add_argument("design", help="designs/<name> (a path or the bare name)")
    ap.add_argument("--variant", default="base")
    ap.add_argument("--stage", choices=list(STAGES), help="the checkpoint --open opens (default: route, else the last present)")
    ap.add_argument("--open", action="store_true", dest="open_gui", help="launch the Vivado GUI on the project and that checkpoint (heavy slot)")
    ap.add_argument("--verify", action="store_true", help="prove in Vivado batch that the project and every checkpoint load (heavy slot)")
    ap.add_argument("--rtl", action="store_true", help="with --verify: also elaborate the project's RTL")
    ap.add_argument("--no-project", action="store_true", help="write the Tcl, INSPECT.md and the browser views only; no Vivado")
    ap.add_argument("--no-views", action="store_true", help="skip the browser views")
    ap.add_argument("--schematic", action="append", default=[], metavar="MODULE", help="a schematic of this module (repeatable); default: the top module")
    ap.add_argument("--out", type=Path, help="output directory (default: <build>/inspect)")
    a = ap.parse_args(argv)
    try:
        r = inspect(a.design, a.variant, a.stage, a.out, project=not a.no_project, views=not a.no_views, verify=a.verify, rtl=a.rtl,
                    schematics=a.schematic, open_gui=a.open_gui)
    except InspectError as e:
        print(f"inspect: {e}", file=sys.stderr)
        return 2
    print(f"inspect: wrote {r['out']}/INSPECT.md" + (f" and the project {r['project']}" if r["project"] else "") + f"; checkpoints: {', '.join(r['checkpoints'])}")
    if r["stamp"]["stale"]:
        print("inspect: the tree has changed since this build (see INSPECT.md)")
    if (Path(r["out"]) / "index.html").is_file():
        print(f"inspect: browser view: {r['out']}/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
