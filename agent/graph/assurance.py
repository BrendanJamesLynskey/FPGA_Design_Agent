"""The interview side of the verification profile and the dependability structures (brief 194): which profile to propose, which structures
to ask about, what each costs (from the measured records), and the advisory line of the run summary. Pure functions, tested without a model.

The measured records are ``results/b194/costs.json`` (area, Fmax and latency of each structure on the development design) and
``results/b194/profile_times.json`` (wall time of each profile's checks on it). A question's reason quotes them; when a record is
missing the reason says so instead of inventing a figure.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent.graph import profiles as P

RESULTS = Path(__file__).resolve().parents[2] / "results" / "b194"

STRUCTURES = ("ecc", "parity", "safe_fsm", "tmr", "watchdog")
#: block class -> (words in the spec that suggest it, the structure proposed by default, the other structures that fit)
CLASSES = {
    "memory": (r"\b(fifo|ram|memory|memories|buffer|table|bram)\b", "ecc", ("parity",)),
    "state machine": (r"\b(fsm|state machine|states?|sequencer|controller)\b", "safe_fsm", ("watchdog",)),
    "counter or register that must not corrupt": (r"\b(counter|count|length|remaining|pointer|threshold)\b", "tmr", ()),
    "internal bus or pipeline register": (r"\b(bus|pipeline|datapath|stream)\b", "parity", ()),
}

_TRIGGERS = (
    ("high_dependability", r"\b(radiation|single[- ]event|seu|soft error|safety|fault[- ]tolerant|must recover|ecc|redundan|rad-hard|space)\b"),
    ("ip_release", r"\b(library|ip core|reusable ip|ip block|release|verified ip|for reuse)\b"),
    ("low_latency", r"\b(low[- ]latency|tick[- ]to[- ]trade|latency[- ]critical|latency budget|nanosecond)\b"),
    ("prototype", r"\b(prototype|quick look|throwaway|proof of concept|sketch)\b"),
)


def _load(name: str) -> dict | None:
    f = RESULTS / name
    try:
        return json.loads(f.read_text()) if f.is_file() else None
    except (OSError, ValueError):
        return None


def spec_text(spec: dict[str, Any]) -> str:
    parts = [str(spec.get(k, "")) for k in ("title", "summary", "description", "purpose")]
    parts += [str(r.get("text", "")) for r in spec.get("requirements") or [] if isinstance(r, dict)]
    parts += [str(x) for v in (spec.get("behaviour") or {}).values() if isinstance(v, list) for x in v]
    return " ".join(parts).lower()


def propose_profile(spec: dict[str, Any]) -> tuple[str, str]:
    """(profile, reason): the interview's default. The spec's own field wins; then words in the spec; else standard."""
    given = spec.get("verif_profile")
    if given in P.PROFILES:
        return given, f"spec.yaml names it ({given})"
    txt = spec_text(spec)
    for name, rx in _TRIGGERS:
        m = re.search(rx, txt)
        if m:
            return name, f"the spec mentions '{m.group(0)}', which points to {name}"
    return P.DEFAULT_PROFILE, "nothing in the spec asks for more or less; standard is the default and what runs today"


def extra_time_text(name: str) -> str:
    t = _load("profile_times.json")
    if not t or name not in (t.get("profiles") or {}):
        return "extra time: not measured yet"
    base = t["profiles"].get("standard", {}).get("seconds", 0)
    me = t["profiles"][name]["seconds"]
    return f"measured on the development design: {me:.0f} s of checks against {base:.0f} s for standard (model time not included)"


def profile_question(spec: dict[str, Any]) -> tuple[str, str, str]:
    """The interview question: (text, default, reason). The answer is a profile name."""
    default, why = propose_profile(spec)
    lines = "; ".join(f"{n}: {P.SUMMARY[n]}" for n in P.PROFILES)
    text = f"Which verification profile should this run use? Profiles: {lines}. Answer with a profile name."
    return text, default, f"{why}. {extra_time_text(default)}"


def profile_from_answer(answer: str | None, default: str) -> str:
    a = (answer or "").lower()
    found = [n for n in P.PROFILES if re.search(rf"\b{n}\b", a)]
    return found[0] if found else default


_SECURITY_WORDS = r"\b(production|deployed|deployment|in the field|customer|customers|ship|shipping|secure|security|tamper|copy[- ]protect|ip protection|encrypt\w*|confidential|proprietary|trade secret)\b"
SECURITY_QUESTION = "Is this a production build that must be hard to copy, read back or debug?"


def security_cost_text() -> str:
    return _load_b196() or "cost: not measured yet"


def _load_b196() -> str | None:
    f = RESULTS.parent / "b196" / "costs.json"
    try:
        d = json.loads(f.read_text()) if f.is_file() else None
    except (OSError, ValueError):
        return None
    if not d:
        return None
    return (f"measured on the development design (Vivado 2026.1, xck26): {d['d_lut']:+d} LUT, {d['d_ff']:+d} FF, build time {d['d_build_s']:+.0f} s "
            f"(the encryption itself costs no fabric)")


def security_question(spec: dict[str, Any]) -> tuple[str, str, str]:
    """The interview question for the production_secure switch (brief 196): (text, default, reason). Yes only when the spec's own words point
    to a production or protected design; otherwise no. The reason says what a yes does, what it costs (the measured record) and what stays with the owner."""
    m = re.search(_SECURITY_WORDS, spec_text(spec))
    default = "yes" if m else "no"
    why = (f"the spec mentions '{m.group(0)}'" if m else "nothing in the spec asks for a protected or production build")
    text = (SECURITY_QUESTION + " A yes turns on: bitstream encryption and authentication, readback and JTAG access to the system monitor off, "
            "no debug core or debug port in the built design, and system-monitor alarms wired to a latched safe shutdown; the build then fails a gate "
            "for each of these that Vivado's own outputs do not show. You keep the key: the agent never makes, stores or programs one (eFUSE and "
            "BBRAM are yours). Answer yes or no.")
    return text, default, f"{why}. {security_cost_text()}"


def security_from_answer(answer: str | None, default: str) -> bool:
    a = (answer or "").strip().lower()
    if re.match(r"^(yes|y|true|on)\b", a):
        return True
    if re.match(r"^(no|n|false|off)\b", a):
        return False
    return default == "yes"


def candidate_classes(spec: dict[str, Any]) -> list[str]:
    txt = spec_text(spec)
    return [c for c, (rx, _d, _o) in CLASSES.items() if re.search(rx, txt)]


def structure_cost_text(structure: str) -> str:
    c = _load("costs.json")
    row = ((c or {}).get("structures") or {}).get(structure)
    if not row:
        return "cost: not measured yet"
    return (f"measured on the development design (Vivado 2026.1, xc7a100t, one run): {row['d_lut']:+d} LUT, {row['d_ff']:+d} FF, "
            f"{row['d_bram']:+.1f} BRAM tiles, Fmax {row['fmax_pct']:+.1f} %, latency {row['d_latency']:+d} clocks")


def structure_questions(spec: dict[str, Any], eff: dict[str, Any]) -> list[tuple[str, str, str]]:
    """One question per block class the spec seems to contain, only when the profile asks for dependability structures. The default is to
    protect memories and state machines (the structure with the best measured protection per cost) and to leave the rest alone."""
    if eff.get("dependability") != "interview":
        return []
    out = []
    for cls in candidate_classes(spec):
        rx, d, others = CLASSES[cls]
        default = f"protect with {d}" if cls in ("memory", "state machine") else "do not protect"
        text = (f"Which of this design's blocks of the kind '{cls}' need protection against single-event upsets? Options: {d}"
                + (f" (or {', '.join(others)})" if others else "") + ", or none. Name the blocks.")
        out.append((text, default, f"{structure_cost_text(d)}. A block you do not name is not changed."))
    return out


def advisory(rec: dict[str, Any]) -> str:
    """One line for the run summary: what the profile bought and what it left off."""
    eff, name = rec["effective"], rec["profile"]
    bits = [f"profile {name}" + (f" with {len(rec['overrides'])} override(s)" if rec["overrides"] else "")]
    if eff["post_synth_sim"] or eff["equivalence"]:
        bits.append("netlist checks on")
    if eff["fault_injection"]:
        bits.append("fault injection on")
    if eff.get("production_secure"):
        bits.append("production_secure on (" + ", ".join(k[4:] for k in P.SECURITY[1:] if eff[k]) + ")")
    if rec["method_mix_gaps"]:
        bits.append("cannot reach 'verified' for every kind: lacks " + "; ".join(g.split(" (")[0] for g in rec["method_mix_gaps"]))
    if rec["not_wired"]:
        bits.append("recorded, not yet run by the flow: " + ", ".join(rec["not_wired"]))
    return "; ".join(bits)
