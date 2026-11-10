"""``python -m project`` (also ``python -m agent project``): check a project, show its status, print the stage keys,
generate the contract tests.

    python -m project check     <dir> [--json OUT]
    python -m project status    <dir> [--json OUT] [--html OUT]
    python -m project hash      <dir> [--module M] [--json]
    python -m project gen-tests <dir> [--module M]

``status`` and ``check`` exit 1 when the checker finds a problem. ``hash`` prints the key of every (module, stage): the
value an evidence item records (``modules/<m>/evidence/status.json``) so that it counts as current.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from project import contract_test, dashboard
from project.schema import check_project
from project.stages import stage_keys
from project.status import project_status, text


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m project", description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="check design.yaml, every contract.yaml and the requirements")
    s = sub.add_parser("status", help="current / stale / missing evidence per module and stage")
    h = sub.add_parser("hash", help="the stage keys of today's inputs")
    g = sub.add_parser("gen-tests", help="write tests/contract_tb.py and tests/test_contract_rtl.py per module")
    for p in (c, s, h, g):
        p.add_argument("dir", type=Path)
    for p in (c, s):
        p.add_argument("--json", type=Path, help="write the result as JSON to this file")
    s.add_argument("--html", type=Path, help="write the dashboard page to this file")
    for p in (h, g):
        p.add_argument("--module")
    h.add_argument("--json", action="store_true", help="print JSON")
    a = ap.parse_args(argv)
    root = a.dir.resolve()

    if a.cmd == "check":
        p = check_project(root)
        for e in p.errors:
            print(f"project: {e}")
        for w in p.warnings:
            print(f"project: warning: {w}")
        print(f"project: {'valid' if not p.errors else 'INVALID'} ({len(p.contracts)} contracts)")
        if a.json:
            _write(a.json, json.dumps({"valid": not p.errors, "errors": p.errors, "warnings": p.warnings}, indent=1) + "\n")
        return 0 if not p.errors else 1

    if a.cmd == "status":
        st = project_status(root)
        print(text(st))
        if a.json:
            _write(a.json, json.dumps(st, indent=1) + "\n")
        if a.html:
            _write(a.html, dashboard.page(st))
            print(f"dashboard: {a.html}")
        return 0 if st["valid"] else 1

    p = check_project(root)
    if p.errors:
        for e in p.errors:
            print(f"project: {e}")
        print("project: INVALID; fix the problems first")
        return 1
    mods = [a.module] if a.module else [m for m in p.modules() if m in p.contracts]
    unknown = [m for m in mods if m not in p.contracts]
    if unknown:
        print(f"project: no contract for {', '.join(unknown)}")
        return 1
    if a.cmd == "hash":
        res = {m: [{"n": k["n"], "stage": k["stage"], "key": k["key"]} for k in stage_keys(p, m)] for m in mods}
        if a.json:
            print(json.dumps(res, indent=1))
        else:
            for m, ks in res.items():
                for k in ks:
                    print(f"{m:<14} {k['n']} {k['stage']:<26} {k['key']}")
        return 0
    for m in mods:                                    # gen-tests
        for f in contract_test.write(root / "modules" / m, p.module(m).get("params")):
            print(f"wrote {f.relative_to(root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
