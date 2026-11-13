"""The one model API shared by the Modeller and Verifier roles, and the contract-check gate (brief 05c, fix 2).

05b run 1 failed at 0 ns because the Verifier called ``Model(clk_hz=...)`` on a model that took
``Model(CLK_HZ=...)``. The API is now fixed text, put in both prompts, and the graph checks it (import the model,
instantiate it with the spec's parameters, ``reset()``, ``step({})``) before the expensive simulate step.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

MODEL_CONTRACT = """\
Model API contract (identical for the model writer and the test writer; the graph checks it before simulating):
- model.py defines exactly one class, named `Model`, with no other public entry point.
- `Model(**params)`: keyword arguments named EXACTLY as the keys of spec.yaml `parameters` (same spelling and case),
  each defaulting to the spec's value. No positional arguments. Timing parameters are integer cycle counts.
- `reset()` -> None: the state after reset is asserted and released.
- `step(inputs=None)` -> dict: advance ONE clock cycle. `inputs` maps input port names (spec.yaml `ports`, exact
  names) to ints; an absent port keeps its previous value. The result maps output port names to ints, as sampled
  after the clock edge, and is always a dict (an empty one is allowed only if the design has no outputs).
- `read_reg(offset)` -> int and `write_reg(offset, value)` -> None for the register window (spec.yaml `registers`).
- The test writer uses only these names: `from model import Model; m = Model(**params)`.
"""

_SNIPPET = r"""
import json, sys, traceback
design, params = sys.argv[1], json.loads(sys.argv[2])
sys.path.insert(0, design)
try:
    import model
    if not hasattr(model, "Model"):
        raise AttributeError("model.py defines no class named Model (found: %s)"
                             % sorted(n for n in dir(model) if not n.startswith("_")))
    m = model.Model(**params)
    m.reset()
    out = m.step({})
    if not isinstance(out, dict):
        raise TypeError("Model.step({}) returned %s, not a dict" % type(out).__name__)
    model.Model()
    print(json.dumps({"ok": True}))
except BaseException:
    print(json.dumps({"ok": False, "error": traceback.format_exc()[-1500:]}))
    sys.exit(1)
"""


def contract_argv(design: Path, spec: dict[str, Any]) -> list[str]:
    """The argv that imports the model and exercises the contract (run by the runner, in the container)."""
    params = {k: v for k, v in (spec.get("parameters") or {}).items() if isinstance(v, (int, str)) or v is None}
    return [sys.executable, "-I", "-c", _SNIPPET, str(design), json.dumps(params)]


def parse_result(returncode: int, stdout: str, stderr: str) -> dict[str, Any]:
    for line in reversed((stdout or "").splitlines()):
        try:
            r = json.loads(line)
            if isinstance(r, dict) and "ok" in r:
                return r
        except ValueError:
            continue
    return {"ok": False, "error": ((stderr or stdout or f"exit {returncode}")[-1500:])}
