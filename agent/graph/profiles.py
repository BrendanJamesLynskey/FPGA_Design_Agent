"""Verification profiles: named presets of per-method switches, with overrides (brief 194).

A *profile* is a preset of *switches*. Each switch is one verification method or reliability structure with a typed value
(on/off, a number, or a name from a list). ``resolve(profile, overrides)`` returns the effective switches and a record that
names the profile and every override (what it was, what it became), which goes into the run summary.

Reconciled with what exists (nothing is duplicated, nothing is removed):

* ``--verif-level V1|V2|V3`` is the switch ``verif_level``. A profile sets it; giving ``--verif-level`` on the command line is an
  override of that switch and is recorded as one.
* ``--spec-tests`` is the switch ``indep_spec_test``.
* The V3 floors of ``flow/verif_floors.yaml`` stay the minimum. ``mutation_floor`` and ``seeds`` can only raise them: a value below
  the floor is refused by ``resolve`` (a profile never lowers a floor; ``prototype`` stops at V1, where the floors do not apply).
* The required method mix per requirement kind (``flow/method_mix_policy.yaml``, brief 143a) decides when a requirement is
  ``verified``. Profiles do not change it. A profile that lacks a method the policy requires for a kind cannot produce ``verified``
  for that kind; ``method_mix_gap(profile)`` names the gap.
* The IP library's "verified" label (VERIFIED.md, decisions 24 and 26) requires profile ``ip_release`` or stronger: ``ip_release_ok``.

The existing ``--profile`` flag is per-role model routing (brief 05f). It is unchanged; the verification profile is
``--verif-profile``.

Each switch has a ``consumer``: where the value takes effect. ``wired`` is True when the harness or flow reads it today; a switch
that is only recorded says so (``wired: False``; ``not_wired`` lists such switches whose value differs from ``standard``, which is what runs today), so a profile never claims a check that nothing runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

BOOL, INT, CHOICE = "bool", "int", "choice"


@dataclass(frozen=True)
class Switch:
    name: str
    kind: str
    doc: str
    consumer: str
    wired: bool
    choices: tuple = ()
    lo: int = 0
    hi: int = 1000


SWITCHES: tuple[Switch, ...] = (
    Switch("lint", BOOL, "Verilator/slang lint of the RTL", "agent.graph.run (lint gate)", True),
    Switch("directed_sim", BOOL, "directed tests against the reference model", "agent.graph.run (simulate)", True),
    Switch("verif_level", CHOICE, "the verification stage the design must reach (V1 testplan, V2 tests and formal, V3 coverage closed)",
           "agent.graph.run (cfg.verif_level)", True, choices=("V1", "V2", "V3")),
    Switch("random_sim", BOOL, "constrained-random tests with checkers bound", "agent.graph.run (V2)", True),
    Switch("coverage_target", INT, "functional-bin and cover-property percentage required (floor 100 at V3)",
           "flow/verif_floors.yaml", True, lo=0, hi=100),
    Switch("mutation_floor", INT, "bench mutation score required, percent (floor 70 at V3)", "flow/verif_floors.yaml", True, lo=0, hi=100),
    Switch("seeds", INT, "seeds the randomised benches run, all passing (floor 3 at V3)", "flow/verif_floors.yaml; flow/assurance.py",
           True, lo=1, hi=64),
    Switch("indep_spec_test", BOOL, "second reader writes a spec-only bench (08f)", "agent.graph.spectest (cfg.spec_tests)", True),
    Switch("formal_depth_scale", INT, "bounded formal on the control logic: 0 = off, 1 = the depth in the design's own .sby files, n = n times that depth",
           "flow/formal.sh (.sby depth)", False, lo=0, hi=16),
    Switch("formal_induction", BOOL, "k-induction where the property closes", "flow/formal.sh", False),
    Switch("formal_pdr", BOOL, "property-directed reachability (unbounded) where induction does not close", "flow/formal.sh", False),
    Switch("lean_proof", BOOL, "Lean proof of the named lemmas (brief 125 evidence tier)", "flow/lean_tier.py", False),
    Switch("uvm", CHOICE, "UVM-style bench: none, pyuvm on cocotb, or SystemVerilog UVM", "verif bench (brief 112, 123)", False,
           choices=("none", "pyuvm", "sv_uvm")),
    Switch("post_synth_sim", BOOL, "the functional bench re-run on the Vivado funcsim netlist", "flow/assurance.py", True),
    Switch("equivalence", BOOL, "RTL against the synthesised netlist with eqy where the primitives are modelled", "flow/assurance.py", True),
    Switch("timing_sim", CHOICE, "post-route timing simulation with SDF: off, auto (only if the spec says timing_sim: true) or on",
           "flow/assurance.py", True, choices=("off", "auto", "on")),
    Switch("fault_injection", BOOL, "seeded single-bit-flip simulation against the protected and the plain design", "flow/assurance.py",
           True),
    Switch("reliability", CHOICE, "structures added to the design: none, or the set the interview chose (ecc, parity, safe_fsm, tmr, watchdog)",
           "agent.graph.assurance (interview + RTL generation)", True, choices=("none", "interview")),
    Switch("latency_checks", BOOL, "latency budget check and the latency-path documentation rule (brief 84, 189)", "flow/latency", False),
    Switch("board_hil", CHOICE, "board or hardware-in-the-loop run: off, smoke or full", "agent.graph.run (stage 9)", True,
           choices=("off", "smoke", "full")),
    Switch("repeats", INT, "whole-flow repeats for the QoR spread", "agent.graph.run", False, lo=1, hi=20),
)
BY_NAME = {s.name: s for s in SWITCHES}

#: the floors of flow/verif_floors.yaml that a profile may raise but never lower (applies from verif_level V3)
FLOORS = {"coverage_target": 100, "mutation_floor": 70, "seeds": 3}

_OFF = {"lint": False, "directed_sim": False, "verif_level": "V1", "random_sim": False, "coverage_target": 0, "mutation_floor": 0,
        "seeds": 1, "indep_spec_test": False, "formal_depth_scale": 0, "formal_induction": False, "formal_pdr": False, "lean_proof": False,
        "uvm": "none", "post_synth_sim": False, "equivalence": False, "timing_sim": "off", "fault_injection": False,
        "reliability": "none", "latency_checks": False, "board_hil": "off", "repeats": 1}


def _p(**kw: Any) -> dict[str, Any]:
    return {**_OFF, **kw}


_STANDARD = _p(lint=True, directed_sim=True, verif_level="V3", random_sim=True, coverage_target=100, mutation_floor=70, seeds=3,
               formal_depth_scale=1, board_hil="smoke")
_THOROUGH = {**_STANDARD, "seeds": 8, "formal_depth_scale": 4, "post_synth_sim": True, "equivalence": True, "timing_sim": "auto"}

PROFILES: dict[str, dict[str, Any]] = {
    "prototype": _p(lint=True, directed_sim=True, verif_level="V1", seeds=1),
    "standard": _STANDARD,
    "thorough": _THOROUGH,
    "ip_release": {**_THOROUGH, "mutation_floor": 85, "seeds": 8, "indep_spec_test": True, "formal_induction": True, "formal_pdr": True,
                   "uvm": "pyuvm", "formal_depth_scale": 4},
    "high_reliability": {**_THOROUGH, "fault_injection": True, "reliability": "interview"},
    "low_latency": {**_STANDARD, "latency_checks": True},
}
SUMMARY = {
    "prototype": "fastest: lint and directed tests to V1; no coverage, no formal, no netlist checks",
    "standard": "today's default: V3 with the floors, constrained-random, bounded formal on the control logic, board smoke run",
    "thorough": "standard plus the netlist checks (functional simulation of the synthesised netlist, equivalence), 8 seeds, deeper formal",
    "ip_release": "thorough plus an independent spec bench, mutation floor 85, induction and PDR proofs, pyuvm bench: what a library 'verified' label needs",
    "high_reliability": "thorough plus the structures the interview chose (ECC, parity, safe FSM, TMR, watchdog) and fault-injection simulation",
    "low_latency": "standard plus the latency budget checks and the latency-path documentation rule",
}
DEFAULT_PROFILE = "standard"


class ProfileError(ValueError):
    pass


def parse_value(sw: Switch, text: str) -> Any:
    t = str(text).strip()
    if sw.kind == BOOL:
        if t.lower() in ("1", "true", "on", "yes"):
            return True
        if t.lower() in ("0", "false", "off", "no"):
            return False
        raise ProfileError(f"{sw.name}: expected on or off, got {text!r}")
    if sw.kind == INT:
        try:
            v = int(t)
        except ValueError:
            raise ProfileError(f"{sw.name}: expected a whole number, got {text!r}") from None
        if not sw.lo <= v <= sw.hi:
            raise ProfileError(f"{sw.name}: {v} is outside {sw.lo}..{sw.hi}")
        return v
    if t not in sw.choices:
        raise ProfileError(f"{sw.name}: expected one of {', '.join(sw.choices)}, got {text!r}")
    return t


def parse_sets(items: list[str] | None) -> dict[str, Any]:
    """``--set name=value`` strings to a validated dict (the Navigator and the CLI both go through here)."""
    out: dict[str, Any] = {}
    for it in items or []:
        name, sep, val = str(it).partition("=")
        name = name.strip()
        if not sep or name not in BY_NAME:
            raise ProfileError(f"--set {it!r}: use <switch>=<value> with a switch from: {', '.join(BY_NAME)}")
        out[name] = parse_value(BY_NAME[name], val)
    return out


def resolve(profile: str | None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """The effective switches and the record of how they came about. A floor is never lowered when ``verif_level`` is V3."""
    name = profile or DEFAULT_PROFILE
    if name not in PROFILES:
        raise ProfileError(f"unknown profile {name!r}; profiles: {', '.join(PROFILES)}")
    eff = dict(PROFILES[name])
    changed: dict[str, dict[str, Any]] = {}
    for k, v in (overrides or {}).items():
        if k not in BY_NAME:
            raise ProfileError(f"unknown switch {k!r}")
        v = parse_value(BY_NAME[k], v) if isinstance(v, str) else v
        if v != eff[k]:
            changed[k] = {"profile_value": eff[k], "value": v}
        eff[k] = v
    if eff["verif_level"] == "V3":
        for k, fl in FLOORS.items():
            if eff[k] < fl:
                raise ProfileError(f"{k}={eff[k]} is below the V3 floor {fl} (flow/verif_floors.yaml): a profile may raise a floor, never lower it")
    return {"profile": name, "overrides": changed, "effective": eff,
            "not_wired": sorted(k for k, v in eff.items() if v != _STANDARD[k] and not BY_NAME[k].wired)}


def method_mix_gap(eff: dict[str, Any]) -> list[str]:
    """Methods the required method mix (flow/method_mix_policy.yaml) names that the effective switches leave off: the matrix cannot reach
    ``verified`` for a requirement kind that needs them. Simulation is always there at V1 or above; formal and board are the alternatives."""
    gaps = []
    if not (eff["directed_sim"] or eff["random_sim"]):
        gaps.append("simulation (every kind needs it, or formal, or the board)")
    if not (eff["formal_depth_scale"] or eff["formal_induction"] or eff["formal_pdr"] or eff["lean_proof"]):
        gaps.append("formal (a safety requirement needs simulation plus formal or the board)")
    if eff["board_hil"] == "off":
        gaps.append("board (the alternative to formal for safety, and for a performance measurement)")
    return gaps


def ip_release_ok(eff: dict[str, Any]) -> list[str]:
    """What the IP library's 'verified' label asks of the switches, as reasons it is not met (empty = met). The label's own record
    (VERIFIED.md) is written by the library briefs; this is only the part the profile can decide."""
    ref = PROFILES["ip_release"]
    out = []
    for k, v in ref.items():
        cur = eff[k]
        weaker = (cur < v) if isinstance(v, (int, float)) and not isinstance(v, bool) else (v and not cur) if isinstance(v, bool) else \
            (k == "verif_level" and cur < v) or (k == "uvm" and cur == "none") or (k == "timing_sim" and cur == "off")
        if weaker:
            out.append(f"{k}: {cur} (ip_release: {v})")
    return out


def describe(name: str) -> dict[str, Any]:
    """One profile for the pickers: summary, switches, and what each is wired to."""
    r = resolve(name)
    return {"name": name, "summary": SUMMARY[name], "switches": r["effective"], "not_wired": r["not_wired"]}


# ---- the command line, the config and the run record --------------------------------------------------------------------------

def from_cli(profile: str | None, sets: list[str] | None, verif_level: str | None = None, spec_tests: bool = False) -> dict[str, Any]:
    """The run's verification settings from the command line. ``verif_level`` is the value of ``--verif-level`` only when it was given
    explicitly (None when it was defaulted), ``spec_tests`` the ``--spec-tests`` flag. Each of the two old flags is an override of its
    switch and is recorded as one. Returns ``resolve``'s record plus the Config fields the harness reads today."""
    ov = parse_sets(sets)
    if verif_level is not None:
        ov["verif_level"] = verif_level
    if spec_tests:
        ov["indep_spec_test"] = True
    rec = resolve(profile, ov)
    return {**rec, "cfg": cfg_fields(rec["effective"])}


def cfg_fields(eff: dict[str, Any]) -> dict[str, Any]:
    """The Config fields the harness reads from the switches today: ``verif_level`` and ``spec_tests``. Every other switch is read through
    the record (flow/assurance.py reads the netlist switches; the rest are recorded and listed as not wired)."""
    return {"verif_level": eff["verif_level"], "spec_tests": bool(eff["indep_spec_test"])}


def record_of(profile: str | None, overrides: dict[str, Any] | None) -> dict[str, Any]:
    """The run-summary entry: the profile, every override (profile value and the value used), and the switches that are only recorded."""
    r = resolve(profile, overrides)
    r["ip_release_gaps"] = ip_release_ok(r["effective"])
    r["method_mix_gaps"] = method_mix_gap(r["effective"])
    return r


# ---- the pin: the switches are variables the model cannot change (brief 194, docs/agent_levers.md) ----------------------------------

PIN = "policy.json"


def _digest(profile: str | None, sets: dict[str, Any] | None) -> str:
    import hashlib
    import json
    eff = resolve(profile, sets)["effective"]
    return hashlib.sha256(json.dumps(eff, sort_keys=True).encode()).hexdigest()


def write_pin(run_dir, profile: str | None, sets: dict[str, Any] | None, replace: bool = False, set_by: str = "command line") -> dict[str, Any]:
    """Pin the run's effective switches in ``<run dir>/policy.json``. The run directory is outside the design directory, so no role's
    file tool reaches it. Written by the harness at the start of the run; the interview replaces it once, with ``replace=True``, when it
    chooses the profile (the user's answer, or the default they accepted). A resume keeps the pin it finds."""
    import json
    import time
    from pathlib import Path
    f = Path(run_dir) / PIN
    if f.is_file() and not replace:
        return {**json.loads(f.read_text()), "new": False}
    rec = {"profile": profile or DEFAULT_PROFILE, "overrides": dict(sets or {}), "effective_sha256": _digest(profile, sets), "set_by": set_by,
           "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    f.write_text(json.dumps(rec, indent=1) + "\n")
    return {**rec, "new": True}


def check_pin(run_dir, profile: str | None, sets: dict[str, Any] | None, design=None) -> list[str]:
    """Policy breaches: the live settings differ from the pin, or ``spec.yaml`` (which a role may write) names another profile. Empty when
    they agree or the run has no pin (a run from before brief 194)."""
    import json
    from pathlib import Path
    f = Path(run_dir) / PIN
    if not f.is_file():
        return []
    pin = json.loads(f.read_text())
    out = []
    if _digest(profile, sets) != pin["effective_sha256"]:
        out.append(f"the effective verification switches differ from the pin made by {pin['set_by']} ({pin['profile']})")
    if design is not None:
        import yaml
        try:
            sp = yaml.safe_load((Path(design) / "spec.yaml").read_text()) or {}
        except (OSError, yaml.YAMLError):
            sp = {}
        named = sp.get("verif_profile") if isinstance(sp, dict) else None
        if named is not None and named != pin["profile"]:
            out.append(f"spec.yaml names profile {named!r} but the run is pinned to {pin['profile']!r} (set by {pin['set_by']}): the pin wins")
    return out
