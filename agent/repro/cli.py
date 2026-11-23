"""``python -m agent example list | run <name> | compare <run_dir> | tools <name>`` (brief 195). The navigator's Examples page calls the same functions."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from agent.repro import compare as C
from agent.repro import registry as R
from agent.repro import runner as RN

HEAD = ("What should match and what should not (read this before comparing):",
        "  deterministic: tool results for identical RTL (hidden-bench verdicts, Vivado resources, slack, build ID); shown with the RTL hash when the RTL matched",
        "  varies: the RTL text, repair loops, tokens, cost, wall time; shown against the reference minimum / median / maximum",
        "  outcome: do the hidden tests pass; are resources and slack within what the references reached")


def fmt_range(sp: dict[str, Any] | None, nd: int = 0, unit: str = "") -> str:
    if not sp:
        return "none recorded"
    f = lambda x: f"{x:.{nd}f}"                                              # noqa: E731
    return f"{f(sp['min'])} / {f(sp['median'])} / {f(sp['max'])}{(' ' + unit) if unit else ''} (n={sp['n']})"


def list_rows() -> list[dict[str, Any]]:
    reg = R.load()
    rows = []
    for e in reg["examples"]:
        refs = RN.references(e["name"])
        rows.append({**e, "reference": C.reference_summary(refs) if refs else None})
    return rows


def render(c: dict[str, Any]) -> str:
    L = [f"example {c['example']}, run {c['run_id']}, against {c['references']} reference runs", *HEAD, ""]
    lf = c["like_for_like"]
    L.append("setup: " + ("same pinned setup as the references" if lf["same"] else "NOT like for like: " + "; ".join(f"{k} (run {v['run']}, references {', '.join(v['references'])})" for k, v in lf["differences"].items()) + ("; waived: " + ", ".join(lf["waived"]) if lf["waived"] else "")))
    o = c["outcome"]
    L += ["", "OUTCOME", f"  hidden tests: {o['tests']} ({'pass' if o['hidden_pass'] else 'FAIL'}); references passed {o['references_passed']}. {o['verdict']}",
          f"  the agent's own gates: {'passed' if o['internal_pass'] else 'did not all pass'}; references {o['references_internal']}"]
    for r in o["spread"]:
        L.append(f"  {r['label']}: {r['run']} {r['unit']}  reference min/median/max {fmt_range(r['reference'], 3 if r['unit'] == 'ns' else 0)}: {r['where']}")
    d = c["deterministic"]
    L += ["", "DETERMINISTIC given the same inputs", f"  RTL hash {str(d['rtl_sha256'])[:16]}; references with the same RTL: {', '.join(d['matching_references']) or 'none'}"]
    if d.get("note"):
        L.append("  " + d["note"])
    for r in d["rows"]:
        if "verdict" in r:
            L.append(f"  {r['label']}: {r['run'] if not isinstance(r['run'], dict) else '(see per-test)'}  {r['verdict']}")
    L += ["", "VARIES with the model"]
    for r in c["varies"]:
        if r["field"] == "rtl_same":
            L.append(f"  {r['label']}: {r['where']}")
        else:
            L.append(f"  {r['label']}: {r['run']} {r['unit']}  reference min/median/max {fmt_range(r['reference'], r['digits'])}: {r['where']}")
    L += ["", "Limits:", *[f"  - {x}" for x in c["limits"]]]
    return "\n".join(L)


def main(a) -> int:
    if a.example_cmd == "list":
        rows = list_rows()
        if a.json:
            print(json.dumps(rows, indent=1, default=str))
            return 0
        for r in rows:
            ref = r["reference"]
            print(f"{r['name']:<14} {r['title']:<28} {r['kind']}")
            print(f"{'':<14} reference runs: {ref['n'] if ref else 0}; hidden tests passed {ref['hidden_pass'] if ref else '-'}; wall s min/median/max {fmt_range(ref['wall_s']) if ref else '-'}; cost USD {fmt_range(ref['cost_usd'], 2) if ref else '-'}")
        return 0
    if a.example_cmd == "run":
        try:
            info = RN.run_example(a.name, max_usd=a.max_usd, slot=not a.no_slot, allow_unpinned=a.allow_unpinned, dry_run=a.dry_run)
        except R.ExampleError as e:
            print(f"refused: {e}", file=sys.stderr)
            return 2
        for c in info["preflight"]["checks"]:
            print(f"  [{'ok' if c['ok'] else 'WAIVED' if c['name'] in info['preflight']['unpinned_waived'] else 'FAIL'}] {c['name']}: {c['detail']}")
        if info["refused"]:
            print("refused: " + info["refused"], file=sys.stderr)
            return 2
        if a.dry_run:
            print("command: " + " ".join(info["command"]))
            return 0
        print(f"\nrun directory {info['run_dir']} (exit {info['exit_code']}, wall {info['wall_s']} s); result in example_result.json\n")
        print(render(info["comparison"]))
        return 0 if info["result"]["outcome"]["hidden_pass"] else 1
    if a.example_cmd == "compare":
        rd = Path(a.run_dir)
        f = rd / RN.RESULT_FILE
        if not f.is_file():
            print("no example_result.json in that run directory: it was not started by `example run`", file=sys.stderr)
            return 2
        rec = json.loads(f.read_text())
        c = C.compare(rec, RN.references(rec["example"]))
        print(json.dumps(c, indent=1) if a.json else render(c))
        return 0
    if a.example_cmd == "tools":
        from agent.repro import tools as T
        return T.main(a)
    return 2


def add_parser(sub) -> None:
    ex = sub.add_parser("example", help="brief 195: reproducible examples: list them, re-run one with the pinned setup, compare a run with its reference runs")
    es = ex.add_subparsers(dest="example_cmd", required=True)
    l = es.add_parser("list", help="the examples and what their reference runs measured")
    l.add_argument("--json", action="store_true")
    r = es.add_parser("run", help="re-run an example with the pinned setup (spends the plan's tokens; takes a heavy slot where the owner's script exists)")
    r.add_argument("name")
    r.add_argument("--max-usd", type=float, help="a lower cost cap than the pinned one")
    r.add_argument("--no-slot", action="store_true", help="the caller already holds a heavy slot (the navigator does)")
    r.add_argument("--allow-unpinned", action="store_true", help="let the knowledge-bank checkout differ from the pin; the result says so and the comparison is marked not like for like")
    r.add_argument("--dry-run", action="store_true", help="run the pre-flight and print the command; start nothing")
    c = es.add_parser("compare", help="compare a finished example run directory with the reference runs")
    c.add_argument("run_dir", type=Path)
    c.add_argument("--json", action="store_true")
    t = es.add_parser("tools", help="re-run the deterministic part on a stored reference RTL: no model call")
    t.add_argument("name")
    t.add_argument("--ref", type=int, default=1, help="which reference run's RTL (1..N)")
    t.add_argument("--vivado", action="store_true", help="also re-run the Vivado build (a heavy job: take a slot first)")
