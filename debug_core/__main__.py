"""Command line for the natural-language debug front end (brief 50A).

    python -m debug_core plan    designs/t1_dimmer_counter "capture count when the shell writes COUNT, 16 before, 32 after"
    python -m debug_core plan    designs/t1_dimmer_counter --intent intent.json      (no language model)
    python -m debug_core build   <plan.json>                  (Vivado; run it under a heavy slot)
    python -m debug_core capture <plan.json> [--board nexys_a7_100t] [--no-program]   (board.lock, SRAM only)
    python -m debug_core run     designs/<d> "<request>" [--build] [--yes]
    python -m debug_core answer  <capture.json>
    python -m debug_core view    <capture.json> [-o view.html]
    python -m debug_core query   <capture.json> '{"op": "first", "channel": "count", "cmp": "==", "value": "0x1234"}'
    python -m debug_core schema  intent|plan|capture
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from debug_core.rtl_index import ROOT


def _design(p: str) -> Path:
    d = Path(p)
    return d if d.is_absolute() else ROOT / d


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m debug_core", description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("design")
    p.add_argument("request", nargs="?")
    p.add_argument("--intent", type=Path)
    p.add_argument("--model")
    p.add_argument("-o", "--out", type=Path)
    b = sub.add_parser("build")
    b.add_argument("plan", type=Path)
    c = sub.add_parser("capture")
    c.add_argument("plan", type=Path)
    c.add_argument("--board")
    c.add_argument("--no-program", action="store_true")
    c.add_argument("--out", type=Path)
    r = sub.add_parser("run")
    r.add_argument("design")
    r.add_argument("request", nargs="?")
    r.add_argument("--intent", type=Path)
    r.add_argument("--model")
    r.add_argument("--build", action="store_true", help="build the probe set if no debug build holds it (heavy slot!)")
    r.add_argument("--yes", action="store_true", help="go on from the plan without asking")
    r.add_argument("--board")
    r.add_argument("--out", type=Path)
    a = sub.add_parser("answer")
    a.add_argument("capture", type=Path)
    v = sub.add_parser("view")
    v.add_argument("capture", type=Path)
    v.add_argument("-o", "--out", type=Path)
    q = sub.add_parser("query")
    q.add_argument("capture", type=Path)
    q.add_argument("query")
    q.add_argument("--other", type=Path)
    s = sub.add_parser("schema")
    s.add_argument("name", choices=["intent", "plan", "capture"])
    x = ap.parse_args(argv)

    from debug_core import answer as A
    from debug_core import capture as C
    from debug_core import run as R
    from debug_core.plan import render

    if x.cmd == "schema":
        from debug_core.plan import load_schema
        print(json.dumps(load_schema(x.name), indent=1))
        return 0
    if x.cmd in ("plan", "run"):
        intent = json.loads(x.intent.read_text()) if x.intent else None
        plan, meta = R.plan_request(_design(x.design), x.request, intent, model=x.model)
        print(render(plan))
        if meta.get("parser") == "llm":
            print(f"(parsed by {meta.get('model')}, cost {meta.get('cost')} USD as reported, "
                  f"{meta.get('prompt_tokens')}+{meta.get('completion_tokens')} tokens)")
        if x.cmd == "plan":
            out = x.out or R.run_dir(plan) / "plan.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(plan | {"parse": meta}, indent=1) + "\n")
            print(f"plan: {out}")
            return 2 if plan["errors"] else 0
        if plan["errors"]:
            return 2
        if not x.yes and input("Build and capture this plan? [y/N] ").strip().lower() != "y":
            return 1
        out = x.out or R.run_dir(plan)
        (out / "plan.json").write_text(json.dumps(plan | {"parse": meta}, indent=1) + "\n")
        (out / "plan.txt").write_text(render(plan) + "\n")
        ov, labels, info = R.ensure_build(plan, x.build)
        print(f"build: {'reused ' + ov.name if info['reused'] else 'built ' + ov.name}")
        cap = R.hardware_capture(plan, ov, labels, out, x.board)
        cap["build"]["reused"] = info["reused"]
        ans = R.finish(cap, plan, out)
        print(ans["text"])
        print(f"capture: {out / 'capture.json'}  view: {out / 'view.html'}")
        return 0 if not ans["check"] else 1
    if x.cmd == "build":
        from debug_core import build as B
        plan = json.loads(x.plan.read_text())
        st = B.run_build(plan)
        print(json.dumps(st, indent=1, default=str))
        return 0 if st.get("built") else 1
    if x.cmd == "capture":
        plan = json.loads(x.plan.read_text())
        ov, labels, info = R.ensure_build(plan, False)
        out = x.out or R.run_dir(plan)
        cap = R.hardware_capture(plan, ov, labels, out, x.board, program=not x.no_program)
        cap["build"]["reused"] = info["reused"]
        ans = R.finish(cap, plan, out)
        print(ans["text"])
        print(f"capture: {out / 'capture.json'}")
        return 0
    cap = C.load(x.capture)
    if x.cmd == "answer":
        ans = A.answer(cap)
        print(ans["text"])
        if ans["check"]:
            print(f"UNQUOTED NUMBERS: {ans['check']}", file=sys.stderr)
            return 1
        return 0
    if x.cmd == "view":
        from debug_core.view import write_view
        out = x.out or x.capture.with_suffix(".html")
        write_view(cap, out, answer_text=A.answer(cap)["text"])
        print(out)
        return 0
    if x.cmd == "query":
        other = C.load(x.other) if x.other else None
        print(json.dumps(A.query(cap, json.loads(x.query), other), indent=1))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
