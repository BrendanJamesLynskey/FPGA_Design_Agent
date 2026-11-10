#!/usr/bin/env python3
"""Run a design's own cocotb tests with synchroniser-delay injection (brief 16, V-level CDC gate, part 2).

    python3 flow/cdc_inject_run.py designs/<d> [--seeds 4] [--json designs/<d>/build/verif/cdc_inject.json]
            [--tests designs/<d>/tests/test_x_rtl.py ...] [--timeout-s 900]

Runs the design's tests/test_*_rtl.py (what the `simulate` tool runs; Icarus) once plain and then once per seed with
``$FDA_CDC_INJECT_SEED`` set (flow/cdc_inject.py: every first-stage synchroniser flop and every XPM stand-in gets a random
extra 0/1 destination cycle). The plain run must pass; the gate fails if any injected run fails (a test that passes without
injection and fails with it), if a register the injector could not rewrite is left, or if the design has crossings and nothing
could be injected. Writes the evidence file flow/verif_gates.py reads (``--cdc-inject``). A design with no crossing writes
``applicable: false`` and passes without running anything.

Cost: (1 + seeds) runs of the design's tests. T1's tests take about 25 s a run on this machine, so the default 4 seeds add
about 100 s. Needs no heavy-job lock beyond what `simulate` needs (one Icarus process).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from flow import cdc_inject  # noqa: E402

PY = os.environ.get("MUTATE_PYTHON", sys.executable)
DEFAULT_SEEDS = 4


def run_once(tests: list[Path], seed: int | None, timeout_s: int, info_file: Path | None) -> dict:
    env = dict(os.environ)
    env.pop("FDA_CDC_INJECT_SEED", None)
    if seed is not None:
        env["FDA_CDC_INJECT_SEED"] = str(seed)
        if info_file:
            env["FDA_CDC_INJECT_INFO"] = str(info_file)
    t0 = time.time()
    try:
        p = subprocess.run([PY, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", *map(str, tests)], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=timeout_s)
        ok, tail, rc = p.returncode == 0, (p.stdout + p.stderr)[-1500:], p.returncode
    except subprocess.TimeoutExpired:
        ok, tail, rc = False, f"timed out after {timeout_s} s", -9
    return {"seed": seed, "pass": ok, "returncode": rc, "wall_s": round(time.time() - t0, 1), "tail": "" if ok else tail}


def evaluate(design: Path, seeds: int = DEFAULT_SEEDS, tests: list[Path] | None = None, timeout_s: int = 900) -> dict:
    design = Path(design).resolve()
    rep: dict = {"design": design.name, "seeds": list(range(1, seeds + 1))}
    if not cdc_inject.design_crosses(design):
        rep.update({"applicable": False, "pass": True, "why": "the design has no ASYNC_REG register, XPM CDC macro or second clock domain"})
        return rep
    tests = tests or sorted((design / "tests").glob("test_*_rtl.py"))
    if not tests:
        rep.update({"applicable": True, "pass": False, "why": "the design has no tests/test_*_rtl.py to run with injection"})
        return rep
    rep["applicable"] = True
    plain = run_once(tests, None, timeout_s, None)
    rep["plain"] = plain
    runs, info = [], {"sites": 0, "xpm": [], "regs": [], "unhandled": []}
    if plain["pass"]:
        with tempfile.TemporaryDirectory() as t:
            for s in rep["seeds"]:
                f = Path(t) / f"info{s}.json"
                runs.append(run_once(tests, s, timeout_s, f))
                try:
                    i = json.loads(f.read_text())
                    info["sites"] = max(info["sites"], i.get("sites", 0))
                    for k in ("xpm", "regs", "unhandled"):
                        info[k] = sorted(set(info[k]) | set(i.get(k, [])))
                except (OSError, ValueError):
                    pass
    rep["runs"], rep["injection"] = runs, info
    bad = [r["seed"] for r in runs if not r["pass"]]
    if not plain["pass"]:
        why = "the plain run (no injection) fails: this is a functional failure, not an injection finding; fix the tests first"
    elif bad:
        why = (f"the tests pass without injection and fail with injection (seeds {bad}): a crossing depends on the exact number "
               "of destination cycles it takes (a pulse that can be missed, a bus crossed bit by bit, two synchronisers whose outputs "
               f"are combined). First failure: {next(r for r in runs if not r['pass'])['tail'][-400:]}")
    elif info["unhandled"]:
        why = ("a synchroniser register could not be rewritten for injection, so its crossing was not exercised: "
               + "; ".join(info["unhandled"][:6]) + " (use a scalar chain, a shift vector, or an XPM macro)")
    elif info["sites"] + len(info["xpm"]) == 0:
        why = ("the design has crossings but nothing could be injected: no (* ASYNC_REG *) first-stage register and no XPM "
               "macro in the RTL, so the simulation says nothing about them")
    else:
        why = ""
    rep["pass"] = not why
    rep["why"] = why
    rep["wall_s"] = round(plain["wall_s"] + sum(r["wall_s"] for r in runs), 1)
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("design")
    ap.add_argument("--seeds", type=int, default=DEFAULT_SEEDS)
    ap.add_argument("--tests", nargs="*", default=None)
    ap.add_argument("--timeout-s", type=int, default=900)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    d = Path(a.design) if Path(a.design).is_absolute() else ROOT / a.design
    rep = evaluate(d, a.seeds, [Path(x) for x in a.tests] if a.tests else None, a.timeout_s)
    out = Path(a.json) if a.json else d / "build" / "verif" / "cdc_inject.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=1) + "\n")
    print(f"cdc_inject: {'PASS' if rep['pass'] else 'FAIL'} {rep.get('why', '')[:300]}")
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
