"""Load a design for review without touching it (brief 84).

Review mode never edits the reviewed design. The check suite writes under ``<design>/build/``, so every review works on a
copy under ``runs/review/`` (the repository root is where the suite's globs and the Verilator lint resolve paths, and
``runs/`` is not committed). The reviewed directory is hashed before and after; the report records both hashes.

A design the agent did not write has no ``build.yaml``. The copy gets one, made by code from the files: the RTL sources
are the ``.sv``/``.v``/``.vhd`` files that are not testbenches, and the top is the one module nothing else instantiates.
The reviewed design's own ``build.yaml`` is kept when it has one.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {"build", ".git", "runs", "__pycache__", "sim_build", ".pytest_cache", "node_modules", "results"}
RTL_EXT = (".sv", ".v", ".vhd", ".vhdl")
TB_DIRS = {"tb", "test", "tests", "verif", "sim", "bench", "tests_cocotb"}
TB_NAME = re.compile(r"(^tb_|_tb\b|_tb\.|^test_|_test\.|testbench)", re.I)
TEXT_EXT = RTL_EXT + (".svh", ".vh", ".md", ".txt", ".yaml", ".yml", ".json", ".py", ".xdc", ".sdc", ".tcl", ".mk", ".toml", ".cfg", ".csv", ".hex", ".mem")


def _files(d: Path):
    for dp, dn, fn in os.walk(d):
        dn[:] = sorted(x for x in dn if x not in SKIP_DIRS)
        for f in sorted(fn):
            yield Path(dp) / f


def tree_sha(d: Path) -> str:
    """SHA-256 over every file's relative path and content (build/, .git and caches left out)."""
    h = hashlib.sha256()
    for f in sorted(_files(d), key=lambda p: p.relative_to(d).as_posix()):
        h.update(f.relative_to(d).as_posix().encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def is_tb(rel: Path) -> bool:
    return bool(set(rel.parts[:-1]) & TB_DIRS) or bool(TB_NAME.search(rel.name))


_MOD = re.compile(r"^\s*module\s+(?:automatic\s+)?(\w+)", re.M)
_INST = re.compile(r"^\s*(\w+)\s*(?:#\s*\((?:[^;]*?)\)\s*)?(\w+)\s*\(", re.M)
_KW = {"module", "if", "else", "for", "while", "case", "always", "always_ff", "always_comb", "assign", "generate", "function",
       "task", "begin", "end", "initial", "input", "output", "inout", "wire", "reg", "logic", "return", "assert", "property",
       "import", "typedef", "parameter", "localparam", "genvar", "integer", "int", "bit", "posedge", "negedge"}


def strip_comments(t: str) -> str:
    t = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), t, flags=re.S)
    return re.sub(r"//[^\n]*", "", t)


def modules(files: list[Path]) -> dict[str, dict[str, Any]]:
    """name -> {file, line, instances (module names instantiated)} from the source text (comments removed)."""
    mods: dict[str, dict[str, Any]] = {}
    for f in files:
        if f.suffix.lower() not in (".sv", ".v"):
            continue
        t = strip_comments(f.read_text(errors="replace"))
        starts = [(m.start(), m.group(1)) for m in _MOD.finditer(t)]
        for i, (s, name) in enumerate(starts):
            e = starts[i + 1][0] if i + 1 < len(starts) else len(t)
            body = t[s:e]
            mods[name] = {"file": f, "line": t.count("\n", 0, s) + 1, "body": body, "instances": []}
    names = set(mods)
    for name, m in mods.items():
        for im in _INST.finditer(m["body"]):
            if im.group(1) in names and im.group(1) != name and im.group(1) not in _KW:
                m["instances"].append((im.group(1), im.group(2)))
    return mods


def infer_top(files: list[Path]) -> str | None:
    """The top module of the files: the SystemVerilog module nothing instantiates (the largest hierarchy), else (brief 153) the one VHDL
    entity no other VHDL file instantiates; None when there is no unique answer."""
    mods = modules(files)
    if not mods:
        from flow import sources, vhdl
        vh = sources.vhdl_files(files)
        if vh:
            try:
                return vhdl.top_entity(vh, "")
            except RuntimeError:
                return None
    inst = {c for m in mods.values() for c, _ in m["instances"]}
    tops = sorted(n for n in mods if n not in inst)
    if not tops:
        return None
    def size(n: str, seen=()) -> int:
        return 1 + sum(size(c, seen + (n,)) for c, _ in mods[n]["instances"] if c not in seen)
    return max(tops, key=lambda n: (size(n), -tops.index(n)))


def prepare(design: Path, name: str | None = None, top: str | None = None) -> dict[str, Any]:
    """Copy ``design`` to ``runs/review/<name>-<hash>/design`` and give it a build.yaml when it has none.
    Returns {work, src, top, rtl, tb, constraints, docs, tests, sha}."""
    design = Path(design).resolve()
    if not design.is_dir():
        raise SystemExit(f"review: {design} is not a directory")
    sha = tree_sha(design)
    work = ROOT / "runs" / "review" / f"{name or design.name}-{sha[:8]}"
    dst = work / "design"
    if work.exists():
        shutil.rmtree(work)
    dst.mkdir(parents=True)
    for f in _files(design):
        t = dst / f.relative_to(design)
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, t)
    rels = [f.relative_to(dst) for f in _files(dst)]
    rtl = [r for r in rels if r.suffix.lower() in RTL_EXT and not is_tb(r)]
    tb = [r for r in rels if r.suffix.lower() in RTL_EXT + (".py",) and is_tb(r)]
    cons = [r for r in rels if r.suffix.lower() in (".xdc", ".sdc")]
    docs = [r for r in rels if r.suffix.lower() == ".md" or r.name.lower() in ("readme", "readme.txt")]
    had_build = (dst / "build.yaml").is_file()
    t = top
    if had_build:
        try:
            b = yaml.safe_load((dst / "build.yaml").read_text()) or {}
            t = t or b.get("top")
        except yaml.YAMLError:
            pass
    else:
        t = t or infer_top([dst / r for r in rtl])
        rel = dst.relative_to(ROOT).as_posix()
        pats = sorted({f"{rel}/{r.parent.as_posix()}/*{r.suffix}" if r.parent.as_posix() != "." else f"{rel}/*{r.suffix}" for r in rtl
                       if r.suffix.lower() in (".sv", ".v", ".vhd", ".vhdl")})
        pats = [p for p in pats if "*" in p]
        (dst / "build.yaml").write_text(yaml.safe_dump({"top": t, "sources": pats, "made_by": "review (flow/review/prepare.py)"}))
    return {"work": work, "src": dst, "top": t, "rtl": [r.as_posix() for r in rtl], "tb": [r.as_posix() for r in tb],
            "constraints": [r.as_posix() for r in cons], "docs": [r.as_posix() for r in docs],
            "had_build_yaml": had_build, "sha": sha, "origin": design}
