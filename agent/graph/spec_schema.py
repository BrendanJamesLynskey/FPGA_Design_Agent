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

REQUIRED = ("name", "top", "ports", "clocks", "reset", "behaviour", "registers", "timing", "requirements")
#: how a requirement can be shown to hold (brief 05d, Taylor addition 1): a cocotb test against the blind model, a
#: formal property, a check on the board, or an analysis (a flow gate or a report)
PROOF_METHODS = ("simulation", "formal", "hardware", "analysis")
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


def shape_errors(spec: dict[str, Any]) -> list[str]:
    """The ONE canonical shape the gates read (``flow/verif_gates.spec_items``): ``behaviour`` is a mapping of
    lists, ``registers`` is a mapping whose ``map`` is a list of mappings each with a ``name``, ``timing`` is a
    mapping (its ``latency``, if given, a mapping). Anything else is rejected here, with the shape named, instead of
    crashing the gates later."""
    errs, b, r, t = [], spec.get("behaviour"), spec.get("registers"), spec.get("timing")
    if b and not (isinstance(b, dict) and all(isinstance(v, list) for v in b.values())):
        errs.append("'behaviour' must be a mapping of lists (group name -> list of statements)")
    if r:
        m = r.get("map") if isinstance(r, dict) else None
        if not isinstance(m, list) or not m or not all(isinstance(x, dict) and x.get("name") for x in m):
            errs.append("'registers' must be a mapping with a non-empty 'map' list; each entry a mapping with a "
                        "'name' (offset, access, reset, bits)")
    if t:
        if not isinstance(t, dict):
            errs.append("'timing' must be a mapping (for example clock_constraint, latency: {name: text})")
        elif t.get("latency") is not None and not isinstance(t["latency"], dict):
            errs.append("'timing.latency' must be a mapping of name -> text")
    return errs


def requirement_errors(spec: dict[str, Any], need_proof: bool = True) -> list[str]:
    """``requirements`` is a list of mappings ``{id, text, proof: [method, ...]}``: ids unique, ``proof`` a non-empty
    list from :data:`PROOF_METHODS`. With ``need_proof=False`` (before the interview has proposed a method for each)
    a missing ``proof`` is allowed, a wrong one is not."""
    reqs = spec.get("requirements")
    if reqs is None:
        return []
    if not isinstance(reqs, list) or not all(isinstance(r, dict) for r in reqs):
        return ["'requirements' must be a list of mappings: {id, text, proof: [simulation|formal|hardware|analysis]}"]
    errs, seen = [], set()
    for i, r in enumerate(reqs):
        rid = r.get("id")
        if not rid or not r.get("text"):
            errs.append(f"requirements[{i}] needs an 'id' and a 'text'")
            continue
        if rid in seen:
            errs.append(f"requirement id {rid} is used twice")
        seen.add(rid)
        p = r.get("proof")
        if p is None:
            if need_proof:
                errs.append(f"requirement {rid} has no proof method (proof: a list from {', '.join(PROOF_METHODS)})")
        elif not isinstance(p, list) or not p or any(m not in PROOF_METHODS for m in p):
            errs.append(f"requirement {rid}: proof must be a non-empty list from {', '.join(PROOF_METHODS)} (got {p!r})")
    return errs


def propose_proof(text: str) -> tuple[list[str], str]:
    """A default proof method for a requirement, from its wording (the interview offers it with its reason)."""
    low = text.lower()
    if re.search(r"\b(never|always|at most one|mutually exclusive|invariant|no more than)\b", low):
        return ["simulation", "formal"], "an invariant over all states: a bounded formal proof backs the simulation"
    if re.search(r"\b(mhz|ns\b|timing|slack|clock rate|resource|lut|bram|dsp|power|temperature)\b", low):
        return ["analysis"], "a timing, resource or power figure is read from the flow's reports, not simulated"
    if re.search(r"\b(board|led|button|switch|display|uart|pin|visible)\b", low) and "simulat" in low:
        return ["simulation", "hardware"], "board-visible behaviour: simulated, then checked on the board"
    return ["simulation"], "behaviour of the design: a cocotb test against the blind model"


def validate(spec: dict[str, Any], allow_rates: bool = False, need_proof: bool = True) -> list[str]:
    """Why this spec cannot be signed off (empty list: it can). ``need_proof=False``: the first pass, before the
    interview has settled each requirement's proof method."""
    if not spec:
        return ["spec.yaml is empty"]
    errs = [f"spec.yaml has no {k!r} (required, non-empty)" for k in REQUIRED if not spec.get(k)]
    errs += requirement_errors(spec, need_proof)
    for k in ("ports", "clocks"):
        if spec.get(k) and not isinstance(spec[k], (list, dict)):
            errs.append(f"{k!r} must be a list or mapping")
    errs += shape_errors(spec)
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
