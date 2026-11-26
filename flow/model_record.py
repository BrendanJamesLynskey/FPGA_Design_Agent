"""Brief 213: what a bench feeds the reference model, and a snapshot of the RTL and model at the first failing check.

The Modeller's ``model.py`` has one class, ``Model`` (the model API contract): ``Model(**params)``, ``reset()``, ``step(inputs)`` -> outputs of
ONE clock cycle, and ``read_reg(offset)`` / ``write_reg(offset, value)``. This module wraps those entry points of the class named ``Model`` in a module
named ``model`` when it is imported (``flow/cocotb_run.py`` lists it as the first cocotb test module when one of the variables below is set, so the
hook is in place before the bench imports ``model``). It never changes a result and never raises into the bench.

``$FDA_MODEL_RECORD=<file>``: append one JSON line per call (size-bounded, ``MAX_LINES``):

  {"op": "new", "params": {...}, "test": "<cocotb test running>"}      a Model was constructed (one segment starts)
  {"op": "reset"} / {"op": "step", "in": {...}, "out": {...}} / {"op": "wr", "addr": A, "val": V} / {"op": "rd", "addr": A, "val": V}

``$FDA_DIAG_SNAPSHOT=<file>``: keep rings in memory (the last ``MODEL_RING`` model calls with the simulator time of each, and, from a coroutine started at the
first ``Model(...)``, the last ``DUT_RING`` clock cycles of the top level's signals sampled after each rising edge of the spec's clock), and when a cocotb test
fails write ``<file>`` with the rings, the failing test, the exception text, the bench's failing source line, and the simulator time; then stop the simulation
(the first failure is the evidence). Used by the diagnostic re-run of a failed simulate (``flow/divergence.py``), not by ordinary runs: the sampler costs
simulation time.
"""

from __future__ import annotations

import collections
import importlib.abc
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

MAX_LINES = 60_000
MODEL_RING = 40
DUT_RING = 24
MAX_SIGNALS = 48
_state: dict[str, Any] = {"lines": 0, "full": False, "seq": 0, "started": False, "design": None, "names": []}
_model_ring: collections.deque = collections.deque(maxlen=MODEL_RING)
_dut_ring: collections.deque = collections.deque(maxlen=DUT_RING)


def _jsonable(o: Any) -> Any:
    try:
        return int(o)
    except (TypeError, ValueError):
        return repr(o)


def _now_ns() -> float | None:
    try:
        from cocotb.utils import get_sim_time
        return float(get_sim_time("ns"))
    except Exception:
        return None


def _w(rec: dict[str, Any]) -> None:
    if os.environ.get("FDA_DIAG_SNAPSHOT"):
        _state["seq"] += 1
        _model_ring.append({"n": _state["seq"], "t": _now_ns(), **rec})
    path = os.environ.get("FDA_MODEL_RECORD")
    if not path or _state["full"]:
        return
    if _state["lines"] >= MAX_LINES:
        _state["full"] = True
        rec = {"op": "truncated", "lines": _state["lines"]}
    try:
        with open(path, "a") as f:
            f.write(json.dumps(rec, default=_jsonable, separators=(",", ":")) + "\n")
        _state["lines"] += 1
    except OSError:
        pass


def _test_name() -> str | None:
    try:
        import cocotb
        t = getattr(cocotb, "_regression_manager", None) or getattr(cocotb, "regression_manager", None)
        cur = getattr(t, "_test", None) or getattr(t, "test", None)
        return getattr(cur, "name", None) or getattr(cur, "__qualname__", None)
    except Exception:
        return None


def _clock_name(design: Path | None) -> str:
    try:
        import yaml
        spec = yaml.safe_load((design / "spec.yaml").read_text()) or {}
        return ((spec.get("clocks") or [{}])[0] or {}).get("name") or "clk"
    except Exception:
        return "clk"


def _sample_names(dut: Any) -> list[str]:
    names: list[str] = []
    try:
        for h in dut:
            n = getattr(h, "_name", None)
            if n and hasattr(h, "value"):
                names.append(n)
            if len(names) >= MAX_SIGNALS:
                break
    except Exception:
        pass
    return names


async def _sampler(dut: Any, clk_name: str, names: list[str]) -> None:
    from cocotb.triggers import ReadOnly, RisingEdge
    clk = getattr(dut, clk_name, None)
    if clk is None:
        return
    handles = [(n, getattr(dut, n)) for n in names if getattr(dut, n, None) is not None]
    cyc = 0
    while True:
        await RisingEdge(clk)
        await ReadOnly()
        row = {}
        for n, h in handles:
            try:
                row[n] = int(h.value)
            except ValueError:
                row[n] = str(h.value)
            except Exception:
                pass
        _dut_ring.append({"cycle": cyc, "t": _now_ns(), "sig": row})
        cyc += 1


def _start_sampler() -> None:
    if _state["started"] or not os.environ.get("FDA_DIAG_SNAPSHOT"):
        return
    try:
        import cocotb
        dut = cocotb.top
        names = _sample_names(dut)
        cocotb.start_soon(_sampler(dut, _clock_name(_state["design"]), names))
        _state["started"], _state["names"] = True, names
    except Exception:
        pass


def wrap(model_module: Any) -> None:
    cls = getattr(model_module, "Model", None)
    if cls is None or getattr(cls, "_fda_recorded", False):
        return
    try:
        _state["design"] = Path(model_module.__file__).resolve().parent
    except Exception:
        pass
    o_init = cls.__init__
    o_reset, o_step = getattr(cls, "reset", None), getattr(cls, "step", None)
    o_rd, o_wr = getattr(cls, "read_reg", None), getattr(cls, "write_reg", None)

    def __init__(self, *a, **k):
        _w({"op": "new", "params": dict(k), "test": _test_name()})
        _start_sampler()
        o_init(self, *a, **k)

    def reset(self, *a, **k):
        r = o_reset(self, *a, **k)
        _w({"op": "reset"})
        return r

    def step(self, inputs=None, *a, **k):
        r = o_step(self, inputs, *a, **k) if inputs is not None else o_step(self, *a, **k)
        _w({"op": "step", "in": dict(inputs or {}), "out": dict(r) if isinstance(r, dict) else None})
        return r

    def read_reg(self, *a, **k):
        r = o_rd(self, *a, **k)
        _w({"op": "rd", "addr": a[0] if a else k.get("offset"), "val": r})
        return r

    def write_reg(self, *a, **k):
        r = o_wr(self, *a, **k)
        _w({"op": "wr", "addr": a[0] if a else k.get("offset"), "val": a[1] if len(a) > 1 else k.get("value")})
        return r
    cls.__init__ = __init__
    for name, fn, orig in (("reset", reset, o_reset), ("step", step, o_step), ("read_reg", read_reg, o_rd), ("write_reg", write_reg, o_wr)):
        if orig:
            setattr(cls, name, fn)
    cls._fda_recorded = True


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name != "model":
            return None
        for f in sys.meta_path:
            if f is self or not hasattr(f, "find_spec"):
                continue
            spec = f.find_spec(name, path, target)
            if spec is not None and spec.loader is not None:
                spec.loader = _Loader(spec.loader)
                return spec
        return None


class _Loader(importlib.abc.Loader):
    def __init__(self, inner):
        self.inner = inner

    def create_module(self, spec):
        return self.inner.create_module(spec) if hasattr(self.inner, "create_module") else None

    def exec_module(self, module):
        self.inner.exec_module(module)
        try:
            wrap(module)
        except Exception:
            pass


def _failure_site(exc: BaseException | None) -> dict[str, Any]:
    """The innermost frame of the failure that is in the design's own files (the bench), with its source line."""
    if exc is None:
        return {}
    site: dict[str, Any] = {}
    for fs in traceback.extract_tb(exc.__traceback__):
        if "site-packages" in fs.filename or "/cocotb" in fs.filename or fs.filename.endswith(("cocotb_run.py", "model_record.py")):
            continue
        site = {"file": Path(fs.filename).name, "line": fs.lineno, "func": fs.name, "source": (fs.line or "").strip()[:200]}
    return site


def _patch_failure_hook() -> None:
    try:
        from cocotb import regression as _reg
        cls = _reg.RegressionManager
        orig = cls._record_test_failed
        if getattr(orig, "_fda_hooked", False):
            return

        def hooked(self, wall_time_s, sim_time_ns, result, msg):
            try:
                path = os.environ.get("FDA_DIAG_SNAPSHOT")
                if path and not Path(path).exists():             # the FIRST failure only
                    snap = {"schema": "fda/failure-snapshot/v1", "test": getattr(self._test, "name", None), "sim_time_ns": float(sim_time_ns),
                            "exception": type(result).__name__ if result is not None else None, "message": str(result)[:600] if result is not None else (msg or ""),
                            "site": _failure_site(result), "model_ring": list(_model_ring), "dut_ring": list(_dut_ring),
                            "signals": _state["names"]}
                    Path(path).write_text(json.dumps(snap, default=_jsonable))
                    orig(self, wall_time_s, sim_time_ns, result, msg)
                    try:
                        self._fail_simulation("brief 213 diagnostic re-run: stopped at the first failing check")
                    except Exception:
                        pass
                    return
            except Exception:
                pass
            return orig(self, wall_time_s, sim_time_ns, result, msg)
        hooked._fda_hooked = True
        cls._record_test_failed = hooked
    except Exception:
        pass


def install() -> None:
    if not any(isinstance(f, _Finder) for f in sys.meta_path):
        sys.meta_path.insert(0, _Finder())
    if os.environ.get("FDA_DIAG_SNAPSHOT"):
        _patch_failure_hook()


if os.environ.get("FDA_MODEL_RECORD") or os.environ.get("FDA_DIAG_SNAPSHOT"):   # imported as a cocotb test module (flow/cocotb_run.py lists it first)
    install()
