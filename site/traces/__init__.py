"""Model traces for the problem pages: each development task's own hidden/model.py, run on a fixed stimulus.

One adapter per task, site/traces/<task_id>.py, with

    def trace(m):   # m is the task's hidden/model.py, imported as a module
        return {"stimulus": str, "unit": str, "x": [int, ...], "signals": [...], "captions": [str, ...], "hero": {...}?}

Rules (checked by validate()):
- the values come from calling the model (its functions, classes, constants); nothing is typed in by hand except the
  stimulus itself (which inputs, which seed, which window of the output to show);
- 8 to 64 steps; x, every signal's values and captions all have one entry per step;
- a signal is {"name", "kind": "bit" | "bus" | "wave" | "text", "v": [...], "radix": "dec" | "hex" | "bin" (bus only),
  "width": bits (bus, optional), "lo"/"hi" (wave, optional axis range)}; at most 8 signals;
- captions are plain words, one short sentence or two per step, numbers only from the values;
- "hero" (showcase tasks only) is extra state for the bespoke animation, also computed by the model.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
KINDS = {"bit", "bus", "wave", "text"}


def load_model(task_dir: Path):
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    p = task_dir / "hidden" / "model.py"
    spec = importlib.util.spec_from_file_location(f"_model_{task_dir.name}", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def load_adapter(task: str):
    p = HERE / f"{task}.py"
    if not p.exists():
        return None
    spec = importlib.util.spec_from_file_location(f"_trace_{task}", p)
    a = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(a)
    return a


def validate(task: str, t: dict) -> None:
    n = len(t["x"])
    assert 8 <= n <= 64, (task, "steps", n)
    assert isinstance(t["stimulus"], str) and t["stimulus"], task
    assert isinstance(t["unit"], str) and t["unit"], task
    assert len(t["captions"]) == n, (task, "captions", len(t["captions"]), n)
    assert 1 <= len(t["signals"]) <= 8, (task, "signals")
    for s in t["signals"]:
        assert s["kind"] in KINDS, (task, s["name"], s["kind"])
        assert len(s["v"]) == n, (task, s["name"], len(s["v"]), n)
        if s["kind"] == "bit":
            assert all(v in (0, 1) for v in s["v"]), (task, s["name"])
        elif s["kind"] in ("bus", "wave"):
            assert all(isinstance(v, int) and not isinstance(v, bool) for v in s["v"]), (task, s["name"])
            if s["kind"] == "bus":
                assert s.get("radix", "dec") in ("dec", "hex", "bin"), (task, s["name"])
        else:
            assert all(isinstance(v, str) for v in s["v"]), (task, s["name"])


def build(task: str, task_dir: Path):
    a = load_adapter(task)
    if a is None:
        return None
    t = a.trace(load_model(task_dir))
    validate(task, t)
    return t
