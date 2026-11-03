#!/usr/bin/env python3
"""Dry check of the bring-up artefacts, before the board is asked for (brief 05d, planner item from luna run 7).

    python3 flow/hw_dry_check.py designs/<name> [--json OUT]

``flow/bringup.py`` needs, in the design directory: ``hw_checks.py`` (a module-level ``CAPTURES`` list of captures
and a ``restore(sh)`` function), ``tests/test_*_hw.py`` (pytest tests marked ``hw``) and ``probes.yaml``; and the
human tester needs ``BRINGUP.md`` (Setup, Testing, Debug aids, If it fails). The check reads them as text and
syntax trees only: agent-written code is never imported or run on the host here. Raw problems, no hints.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

CAPTURE_FIELDS = ("name", "condition", "position", "compares", "setup", "stimulus", "check")
BRINGUP_SECTIONS = ("setup", "test", "debug", "if it fails")


def _parse(p: Path, probs: list[str]) -> ast.Module | None:
    try:
        return ast.parse(p.read_text(), filename=str(p))
    except SyntaxError as e:
        probs.append(f"{p.name}: syntax error at line {e.lineno}: {e.msg}")
    except OSError as e:
        probs.append(f"{p.name}: cannot be read ({e.strerror})")
    return None


def _or_problem(i: int, call: ast.Call) -> list[str]:
    """Vivado cannot merge several compare values (a multi-bit probe is split over several nets) on one ILA port under
    an OR trigger: ``Trigger needs too many comparators``. With one compared probe OR means the same as AND."""
    kw = {k.arg: k.value for k in call.keywords}
    cond, cmp_ = kw.get("condition"), kw.get("compares")
    if (isinstance(cond, ast.Constant) and cond.value == "OR" and isinstance(cmp_, ast.Dict) and len(cmp_.keys) <= 1):
        return [f"hw_checks.py: CAPTURES[{i}] has condition 'OR' with {len(cmp_.keys)} compared probe(s): Vivado cannot "
                "merge the compare values of one ILA port under OR (Labtools 27-3239); 'AND' is the same trigger"]
    return []


def check_design(design: Path) -> dict[str, Any]:
    probs: list[str] = []
    hc = design / "hw_checks.py"
    if not hc.is_file():
        probs.append("hw_checks.py does not exist (flow/bringup.py imports it for the ILA captures)")
    elif (tree := _parse(hc, probs)) is not None:
        names = {t.id for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign))
                 for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)}
        funcs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        if "CAPTURES" not in names:
            probs.append("hw_checks.py defines no module-level CAPTURES list")
        if "restore" not in funcs:
            probs.append("hw_checks.py defines no restore(sh) function (bringup.py calls it after the captures)")
        for n in tree.body:
            v = n.value if isinstance(n, (ast.Assign, ast.AnnAssign)) else None
            tg = [t.id for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)] \
                if v is not None else []
            if "CAPTURES" in tg and isinstance(v, ast.List):
                if not v.elts:
                    probs.append("hw_checks.py: CAPTURES is empty")
                for i, e in enumerate(v.elts):
                    if isinstance(e, ast.Call):
                        have = {k.arg for k in e.keywords} | set(range(len(e.args)))
                        kw = [k.arg for k in e.keywords]
                        if not e.args and any(f not in kw for f in CAPTURE_FIELDS):
                            probs.append(f"hw_checks.py: CAPTURES[{i}] lacks "
                                         f"{', '.join(f for f in CAPTURE_FIELDS if f not in kw)}")
                        probs += _or_problem(i, e)
    for sv in sorted((design / "rtl").glob("*.sv")) if (design / "rtl").is_dir() else []:
        if re.search(r"\.BUILD_STAMP\s*\(\s*(\d+\s*')?[hHdDbB]\s*_?0[0_]*\s*\)", sv.read_text()):
            probs.append(f"rtl/{sv.name}: fpga_shell BUILD_STAMP is a constant 0; pass the top's BUILD_STAMP parameter "
                         "through (the flow sets it per build; bring-up's still_alive compares it with the build's)")
    tests = sorted((design / "tests").glob("test_*_hw.py")) if (design / "tests").is_dir() else []
    if not tests:
        probs.append("no tests/test_*_hw.py (flow/bringup.py runs pytest -m hw on them)")
    for t in tests:
        tree = _parse(t, probs)
        if tree is None:
            continue
        text = t.read_text()
        fns = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
        if not fns:
            probs.append(f"{t.name}: no test_ function")
        if "mark.hw" not in text:
            probs.append(f"{t.name}: no pytest.mark.hw (pytestmark = pytest.mark.hw): the tests would be deselected")
        if "hw-port" not in text and "hw_port" not in text:
            probs.append(f"{t.name}: never reads the --hw-port option (request.config.getoption('--hw-port'))")
    bu = design / "BRINGUP.md"
    if not bu.is_file():
        probs.append("BRINGUP.md does not exist")
    else:
        heads = [l.lstrip("# ").lower() for l in bu.read_text().splitlines() if l.startswith("#")]
        missing = [s for s in BRINGUP_SECTIONS if not any(s in h for h in heads)]
        if missing:
            probs.append("BRINGUP.md has no section for: " + ", ".join(missing))
    pr = design / "probes.yaml"
    if not pr.is_file():
        probs.append("probes.yaml does not exist")
    else:
        try:
            data = yaml.safe_load(pr.read_text())
            try:
                from flow.prepare import check_probes
            except ImportError:
                from prepare import check_probes
            probs += [f"probes.yaml: {e}" for e in check_probes(data if isinstance(data, dict) else {})]
        except yaml.YAMLError as e:
            probs.append(f"probes.yaml is not valid YAML: {' '.join(str(e).split())[:200]}")
    return {"ok": not probs, "problems": probs}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("design", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    res = check_design(a.design.resolve())
    for p in res["problems"]:
        print(f"bringup artefacts: {p}")
    print(f"bringup artefacts: {'ready' if res['ok'] else 'NOT READY'}")
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(res, indent=1) + "\n")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
