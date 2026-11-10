"""``python -m project`` (also ``python -m agent project``): check a project, show its status, print the stage keys,
generate the contract tests.

    python -m project check     <dir> [--json OUT]
    python -m project status    <dir> [--json OUT] [--html OUT]
    python -m project hash      <dir> [--module M] [--json]
    python -m project gen-tests <dir> [--module M]
    python -m project spec      <dir> [--interview on|oracle|off] [--hidden-spec F] [--model M] [--usd-cap X]

``status`` and ``check`` exit 1 when the checker finds a problem. ``hash`` prints the key of every (module, stage): the
value an evidence item records (``modules/<m>/evidence/status.json``) so that it counts as current. ``spec`` is phase 0
(``project/phase0.py``): from ``<dir>/system/spec.md`` it writes the requirements, ``design.yaml`` and the contracts, and
the question log under ``<dir>/phase0/``.
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
    sp = sub.add_parser("spec", help="phase 0: requirements, design.yaml and the contracts from system/spec.md")
    for p in (c, s, h, g, sp):
        p.add_argument("dir", type=Path)
    sp.add_argument("--interview", choices=("on", "oracle", "off"), default="on")
    sp.add_argument("--hidden-spec", type=Path, help="the oracle's full spec (--interview oracle)")
    sp.add_argument("--model", help="the drafter's and the oracle's model (OpenRouter); default: the agent's")
    sp.add_argument("--board", default="nexys_a7_100t")
    sp.add_argument("--usd-cap", type=float, default=0.50, help="stop when provider-reported cost reaches this")
    sp.add_argument("--record", type=Path, help="write every model call to this file (a replay fixture)")
    sp.add_argument("--replay", type=Path, help="serve the model calls from this file (no network)")
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

    if a.cmd == "spec":
        return _spec(a, root)

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


def _spec(a: argparse.Namespace, root: Path) -> int:
    from agent.graph.interview import SpecOracle
    from agent.graph.llm import DEFAULT_MODEL, OpenRouterClient, Recorder, Replay
    from project.phase0 import Calls, Drafter, Session, Terminal, oracle_llm
    if not (root / "system" / "spec.md").is_file():
        print(f"project: {root}/system/spec.md is missing (the user's words)")
        return 1
    if a.interview == "oracle" and not (a.hidden_spec and a.hidden_spec.is_file()):
        print("project: --interview oracle needs --hidden-spec <file>")
        return 1
    if a.replay:
        client = Replay(a.replay)
    else:
        client = OpenRouterClient(a.model or DEFAULT_MODEL)
        client = Recorder(client, a.record) if a.record else client
    calls = Calls()
    who = {"on": Terminal(), "off": None}.get(a.interview) if a.interview != "oracle" else \
        SpecOracle(a.hidden_spec, oracle_llm(client, calls))
    out = Session(root, Drafter(client, calls, a.usd_cap), who, board=a.board).run()
    if isinstance(who, SpecOracle):                   # the oracle's own record: refused quotes, register-map answers
        (root / "phase0" / "oracle_log.json").write_text(json.dumps(who.log, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0 if out["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
