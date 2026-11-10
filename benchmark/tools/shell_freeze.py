#!/usr/bin/env python3
"""The shell fingerprint: one hash over everything a grader imports from ``shell/`` (quality review 12, R2; brief 15).

    shell_freeze.py show   [--grader-shell DIR]                  # files and hash of the current (or given) shell
    shell_freeze.py make   OUT.json --reason TEXT                # record the current shell as a GRADER_DEPS file
    shell_freeze.py verify GRADER_DEPS.json [--grader-shell DIR]

Why: every task build compiles ``shell/rtl/*.sv`` (benchmark/tools/run_task.py) and every bench imports
``shell.host.protocol`` and ``shell.tests.uart_bfm`` (benchmark/lib/bench.py). The shell is also the agent's own working
copy, so it moves on. A score is tied to the *frozen* shell: the hash below is recorded per benchmark version
(``benchmark/GRADER_DEPS.json``, ``benchmark/course/GRADER_DEPS.json``, and a ``shell_freeze`` entry in the v2 ledger), and
``freeze.py verify`` / ``split.py verify`` fail when the shell they find differs.

Scoring with the frozen shell while the agent's copy moves on: check out the freeze commit as a second work tree and point
the grader at it,

    git worktree add /tmp/frozen_shell <commit recorded in GRADER_DEPS.json>
    FDA_GRADER_SHELL=/tmp/frozen_shell python3 benchmark/tools/run_task.py <task> --rtl <dir>
    python3 benchmark/tools/freeze.py verify --grader-shell /tmp/frozen_shell

``FDA_GRADER_SHELL`` (a repository root that holds ``shell/``) makes run_task compile that copy's ``shell/rtl`` and put it
first on the simulator's PYTHONPATH, so ``shell.host`` and ``shell.tests`` come from it too. ``--grader-shell`` accepts the
same directory (or a ``shell/`` directory itself) and checks it against the record instead of the current tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmark.tools.freeze import digest  # noqa: E402

# Everything under shell/ that a grader reads. Keep in step with benchmark/tools/run_task.py (sources: shell/rtl/*.sv) and
# benchmark/lib/bench.py (imports shell.host.protocol and shell.tests.uart_bfm; the packages' __init__ files come with them).
FILES = ["__init__.py", "host/__init__.py", "host/protocol.py", "tests/__init__.py", "tests/uart_bfm.py"]
GLOBS = ["rtl/*.sv"]


def shell_dir(path: Path | None = None) -> Path:
    """The ``shell/`` directory: of the current tree, or of ``path`` (a repository root holding ``shell/``, or ``shell/`` itself)."""
    if path is None:
        return ROOT / "shell"
    path = Path(path)
    return path / "shell" if (path / "shell").is_dir() else path


def files(path: Path | None = None) -> dict[str, str]:
    """``{"shell/<relative path>": sha256}`` for the grader-dependency files."""
    d = shell_dir(path)
    rels = list(FILES)
    for g in GLOBS:
        rels += sorted(str(p.relative_to(d)) for p in d.glob(g))
    out = {}
    for rel in sorted(set(rels)):
        p = d / rel
        out[f"shell/{rel}"] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "missing"
    return out


def fingerprint(path: Path | None = None) -> str:
    """One SHA-256 over the sorted ``<sha256>  <path>`` lines (the rule of freeze.digest, so ``sha256sum`` reproduces it)."""
    return digest(files(path))


def last_commit() -> str | None:
    """The newest commit that touched any of the files: a work tree at it (or later) holds exactly this shell."""
    paths = [f"shell/{p}" for p in FILES] + [f"shell/{g}" for g in GLOBS]
    try:
        r = subprocess.run(["git", "log", "-1", "--format=%H", "--", *paths], cwd=ROOT, capture_output=True, text=True, timeout=60)
        return r.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def record(reason: str) -> dict:
    f = files()
    return {"kind": "grader_deps", "dated": time.strftime("%Y-%m-%d"), "reason": reason, "shell_sha256": digest(f),
            "last_changed_in_commit": last_commit(), "files": f}


def differences(rec: dict, path: Path | None = None) -> list[str]:
    """What differs between a recorded shell fingerprint and the shell at ``path`` (empty = identical)."""
    now = files(path)
    out = [f"{p}: {'missing' if now.get(p) is None else 'changed'}" for p, h in rec["files"].items() if now.get(p) != h]
    out += [f"{p}: not in the record" for p in now if p not in rec["files"]]
    if not out and digest(now) != rec["shell_sha256"]:
        out.append("hash differs")
    return out


def verify_record(rec: dict, path: Path | None = None, label: str = "shell") -> list[str]:
    """Problems as strings, ready for a verify tool to print; empty = the shell is the recorded one."""
    d = differences(rec, path)
    if not d:
        return []
    where = f"--grader-shell {path}" if path else "the current tree"
    return [f"{label}: {where} differs from the recorded shell fingerprint {rec['shell_sha256'][:16]}... ({'; '.join(d)}). "
            f"Score with a checked-out frozen copy (--grader-shell DIR / FDA_GRADER_SHELL), or record a new shell freeze"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["show", "make", "verify"])
    ap.add_argument("target", nargs="?", type=Path)
    ap.add_argument("--grader-shell", type=Path, default=None)
    ap.add_argument("--reason", default="")
    a = ap.parse_args()
    if a.cmd == "show":
        f = files(a.grader_shell)
        print("\n".join(f"{h}  {p}" for p, h in f.items()) + f"\nshell fingerprint {digest(f)} ({len(f)} files)")
        return 0
    if a.cmd == "make":
        if not a.target or not a.reason:
            raise SystemExit("make needs OUT.json and --reason")
        a.target.write_text(json.dumps(record(a.reason), indent=1) + "\n")
        print(f"{a.target}: shell fingerprint {fingerprint()}")
        return 0
    if not a.target:
        raise SystemExit("verify needs a GRADER_DEPS.json")
    bad = verify_record(json.loads(a.target.read_text()), a.grader_shell)
    print("\n".join(bad) or f"shell fingerprint ok ({fingerprint(a.grader_shell)[:16]}...)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
