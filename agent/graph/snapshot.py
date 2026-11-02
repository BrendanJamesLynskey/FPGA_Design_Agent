"""Stage-end snapshots and exact rewind (brief 05b, owner feature "review with rewind").

Each stage end commits the design directory into a **per-run git repository** kept outside the design
(``<run_dir>/snap.git``, work tree = the design directory), records a SHA-256 manifest of every file, and copies
the stage's Vivado checkpoints (``build/<variant>/*.dcp``) into ``<run_dir>/dcp/<nn>_<stage>/``. A rewind to stage
N checks out that commit (removing files added later), restores the ``.dcp`` files, and verifies the manifest
hash for hash, so "restores the exact files" is checked, not assumed. The LangGraph checkpoint is restored by the
graph (``agent.graph.run``) from the checkpoint id saved with the snapshot.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

SKIP_DIRS = {"__pycache__", "sim_build", ".pytest_cache"}
#: build/ outputs are large and regenerable; the snapshot keeps the reports and gates the review pages cite,
#: and the .dcp files separately. Bitstreams are kept too (a rewind past stage 9 must restore them).
BUILD_KEEP = (".rpt", ".json", ".txt", ".bit", ".ltx", ".md", ".yaml", ".jsonl")


def _files(design: Path) -> list[Path]:
    out = []
    for p in sorted(design.rglob("*")):
        rel = p.relative_to(design)
        if not p.is_file() or set(rel.parts) & SKIP_DIRS or p.suffix in (".pyc", ".dcp"):
            continue
        if rel.parts[0] == "build" and (p.suffix not in BUILD_KEEP or "review" in rel.parts):
            continue
        out.append(p)
    return out


def manifest(design: Path) -> dict[str, str]:
    return {str(p.relative_to(design)): hashlib.sha256(p.read_bytes()).hexdigest() for p in _files(design)}


class Snapshots:
    def __init__(self, run_dir: Path, design: Path):
        self.run_dir, self.design = Path(run_dir), Path(design)
        self.git_dir = self.run_dir / "snap.git"
        self.index = self.run_dir / "snapshots.json"
        if not self.git_dir.is_dir():
            self.run_dir.mkdir(parents=True, exist_ok=True)
            self._git("init", "-q", "--bare", str(self.git_dir), work=False)
            (self.git_dir / "info").mkdir(exist_ok=True)
        self.records: list[dict[str, Any]] = json.loads(self.index.read_text()) if self.index.is_file() else []

    def _git(self, *args: str, work: bool = True, author: str = "fda-agent") -> str:
        env = {**os.environ, "GIT_AUTHOR_NAME": author, "GIT_AUTHOR_EMAIL": f"{author}@localhost",
               "GIT_COMMITTER_NAME": author, "GIT_COMMITTER_EMAIL": f"{author}@localhost"}
        base = ["git", f"--git-dir={self.git_dir}", f"--work-tree={self.design}"] if work else ["git"]
        return subprocess.run([*base, *args], check=True, capture_output=True, text=True, env=env).stdout

    def take(self, n: int, stage: str, checkpoint_id: str | None = None, note: str = "",
             author: str = "fda-agent", key: str | None = None) -> dict[str, Any]:
        """Commit the design directory. ``author="owner"`` for the owner's hand edits (05d): a separate commit."""
        if key is not None and any(r.get("key") == key for r in self.records):
            return next(r for r in self.records if r.get("key") == key)    # a resumed review node: the same snapshot
        if self.records and self.records[-1]["n"] == n and self.records[-1]["manifest"] == manifest(self.design):
            return self.records[-1]               # LangGraph re-runs a node on resume: same state, same snapshot
        files = _files(self.design)
        self._git("read-tree", "--empty", author=author)
        for i in range(0, len(files), 200):
            self._git("add", "-f", "--", *[str(p.relative_to(self.design)) for p in files[i:i + 200]], author=author)
        self._git("commit", "-q", "--allow-empty", "-m", f"{n:02d} {stage}: {note}"[:200], author=author)
        commit = self._git("rev-parse", "HEAD").strip()
        dcp_dir = self.run_dir / "dcp" / f"{n:02d}_{stage}"
        dcps = {}
        for d in sorted((self.design / "build").glob("*/*.dcp")):
            dcp_dir.mkdir(parents=True, exist_ok=True)
            dest = dcp_dir / f"{d.parent.name}__{d.name}"
            shutil.copy2(d, dest)
            dcps[str(d.relative_to(self.design))] = hashlib.sha256(d.read_bytes()).hexdigest()
        rec = {"n": n, "stage": stage, "commit": commit, "checkpoint_id": checkpoint_id, "author": author, "key": key,
               "manifest": manifest(self.design), "dcp": dcps, "seq": len(self.records)}
        self.records.append(rec)
        self.index.write_text(json.dumps(self.records, indent=1))
        return rec

    def latest_for(self, n: int) -> dict[str, Any]:
        for r in reversed(self.records):
            if r["n"] == n:
                return r
        raise KeyError(f"no snapshot for stage {n}")

    def rewind(self, n: int) -> dict[str, Any]:
        """Restore the design directory to the end of stage ``n`` exactly; returns the record with a
        ``verified`` field (manifest and .dcp hashes match)."""
        rec = self.latest_for(n)
        for p in _files(self.design):                      # remove files the snapshot does not have
            if str(p.relative_to(self.design)) not in rec["manifest"]:
                p.unlink()
        for d in (self.design / "build").glob("*/*.dcp"):
            if str(d.relative_to(self.design)) not in rec["dcp"]:
                d.unlink()
        self._git("checkout", "-f", rec["commit"], "--", ".")
        dcp_dir = self.run_dir / "dcp" / f"{rec['n']:02d}_{rec['stage']}"
        for rel in rec["dcp"]:
            src = dcp_dir / f"{Path(rel).parent.name}__{Path(rel).name}"
            (self.design / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, self.design / rel)
        now = manifest(self.design)
        dcp_now = {str(d.relative_to(self.design)): hashlib.sha256(d.read_bytes()).hexdigest()
                   for d in sorted((self.design / "build").glob("*/*.dcp"))}
        out = dict(rec, verified=(now == rec["manifest"] and dcp_now == rec["dcp"]))
        if not out["verified"]:
            diff = sorted(set(now.items()) ^ set(rec["manifest"].items()))
            out["diff"] = [k for k, _ in diff][:20]
        return out

    def diff(self, n_from: int | None, n_to: int | None = None, paths: tuple[str, ...] = ("rtl/",)) -> list[dict[str, str]]:
        """Unified diffs of ``paths`` between the snapshots of two stages (``n_from=None``: from nothing). ``n_to=None``:
        the latest snapshot. The review page's RTL diff against the previous approved stage."""
        a = self.latest_for(n_from)["commit"] if n_from is not None else None
        b = self.latest_for(n_to)["commit"] if n_to is not None else self.records[-1]["commit"]
        out = []
        base = a or "4b825dc642cb6eb9a060e54bf8d7d9b4d3ca7a5e"          # git's empty tree
        env = {**os.environ}
        run = lambda *x: subprocess.run(["git", f"--git-dir={self.git_dir}", *x], capture_output=True, text=True,  # noqa: E731
                                        env=env, errors="replace").stdout
        for f in run("diff", "--name-only", base, b, "--", *paths).split():
            out.append({"path": f, "diff": run("diff", "--no-color", "-U3", base, b, "--", f)})
        return out
