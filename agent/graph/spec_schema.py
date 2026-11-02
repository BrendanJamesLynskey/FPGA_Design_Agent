"""spec.yaml loading and the minimal schema the clarify gate requires (brief 05c, fixes 1 and 3).

``load_spec`` never turns a parse error into an empty spec: it raises :class:`SpecError` carrying the parser's
message (line and column), which the clarify gate feeds back to the work agent. ``validate`` lists what a spec
must have before it can be signed off (ports, clocks, reset, registers, timing, a name and a top), and rejects
timing parameters given as rates or fractions: they must be integer cycle counts, so the blind model and the RTL
cannot round a divider differently (05b diagnosis, run 1: ``an: rtl=0xfd model=0xfe``).

``rate_params`` finds rate-style parameters (``PWM_HZ``, ``DEBOUNCE_MS``...) with the integer cycle count the
interview offers as the default for each.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REQUIRED = ("name", "top", "ports", "clocks", "reset", "registers", "timing")
#: parameter-name suffix -> seconds per unit (a rate is a frequency: 1/value)
_RATE = {"HZ": ("rate", 1.0), "KHZ": ("rate", 1e3), "MHZ": ("rate", 1e6), "BAUD": ("rate", 1.0),
         "MS": ("period", 1e-3), "US": ("period", 1e-6), "NS": ("period", 1e-9)}
_SUFFIX = re.compile(r"_(" + "|".join(_RATE) + r")$")


class SpecError(Exception):
    """spec.yaml is not valid YAML (the message is the parser's own, with line and column)."""


def load_spec(path: Path) -> dict[str, Any]:
    """The parsed spec; ``{}`` only if the file is absent or empty. A parse error raises :class:`SpecError`."""
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise SpecError(f"spec.yaml is not valid YAML: {' '.join(str(e).split())}") from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise SpecError(f"spec.yaml must be a mapping at the top level, not {type(data).__name__}")
    return data


def clock_hz(spec: dict[str, Any]) -> float | None:
    for c in spec.get("clocks") or []:
        if isinstance(c, dict):
            if isinstance(c.get("freq_mhz"), (int, float)):
                return float(c["freq_mhz"]) * 1e6
            if isinstance(c.get("freq_hz"), (int, float)):
                return float(c["freq_hz"])
    return None


def rate_params(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Parameters given as rates or durations, each with the cycle count at the spec's clock (None if unknown)."""
    hz, out = clock_hz(spec), []
    for k, v in (spec.get("parameters") or {}).items():
        m = _SUFFIX.search(str(k))
        if not m or isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            continue
        kind, scale = _RATE[m.group(1)]
        cycles = None
        if hz:
            cycles = max(1, round(hz / (v * scale))) if kind == "rate" else max(1, round(v * scale * hz))
        out.append({"name": k, "value": v, "unit": m.group(1), "cycles": cycles,
                    "new_name": _SUFFIX.sub("_CYCLES", str(k))})
    return out


def validate(spec: dict[str, Any], allow_rates: bool = False) -> list[str]:
    """Why this spec cannot be signed off (empty list: it can)."""
    if not spec:
        return ["spec.yaml is empty"]
    errs = [f"spec.yaml has no {k!r} (required, non-empty)" for k in REQUIRED if not spec.get(k)]
    for k in ("ports", "clocks", "registers"):
        if spec.get(k) and not isinstance(spec[k], (list, dict)):
            errs.append(f"{k!r} must be a list or mapping")
    if spec.get("timing") and not isinstance(spec["timing"], dict):
        errs.append("'timing' must be a mapping")
    params = spec.get("parameters") or {}
    if not isinstance(params, dict):
        errs.append("'parameters' must be a mapping")
        return errs
    for k, v in params.items():
        if isinstance(v, float):
            errs.append(f"parameter {k} = {v} is fractional: timing parameters must be integer cycle counts")
    if not allow_rates:
        for r in rate_params(spec):
            errs.append(f"parameter {r['name']} is a {r['unit']} rate or duration: give an integer cycle count "
                        f"(for example {r['new_name']})")
    return errs
