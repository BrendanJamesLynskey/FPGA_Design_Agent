"""Repair, don't regenerate: route a stage-2 failure to the role that owns it (brief 05c2, fix 1).

Principle (stage-machine design): a failure is evidence about one artefact. Re-running every writer from scratch
re-breaks parts that passed (Opus run 2), and hands the model no signal about what to change. So the graph:

1. traces each failing gate or tool result to the role that wrote the failing artefact, from the evidence only
   (never from the model): the contract check and a traceback in ``model.py`` -> ``model``; a plan or traceability
   failure, or a traceback in the bench -> ``tests``; lint, an HDL compile error, or a behavioural mismatch
   between the RTL and the model -> ``rtl``;
2. runs only those roles, each handed the failures that are its own and its previous output to edit;
3. freezes every other artefact (it is not rewritten by anyone this visit);
4. escalates when a repair did not change the failure: the same signature twice adds the test writer to a
   behavioural mismatch (the bench may be wrong), three times adds the model writer.

The blind-model separation holds: the model writer is shown its own contract or traceback text, or - on the third
repeat - only the NAME of the test that disagrees, never RTL, RTL output or the other artefacts.

Pure functions over tool results: CI tests them with recorded evidence.
"""

from __future__ import annotations

import re
from typing import Any

ROLE_ORDER = ("model", "tests", "rtl")
_FRAME = re.compile(r'File "([^"]+\.py)", line \d+|^(\S+\.py):\d+:', re.M)
_HDL_ERR = re.compile(r"\.s?vh?:\d+(:\d+)?:\s*(error|syntax error)|%Error|I give up|Unable to bind|Unknown module type", re.I)
_EXC = re.compile(r"\b([A-Za-z_]*(?:Error|Exception|Exit|Interrupt))\b")


def verif_failures(v: dict[str, Any] | None, need: str = "V3", limit: int = 80) -> list[str]:
    """The failed checks of the first failed verification stage, with their values (untraced spec ids included).
    Empty when the stage ``need`` is reached."""
    if not v or not v.get("stages"):
        return ["verification gates produced no result (verif_gates did not run)"]
    if v.get("reached") is not None and v["reached"] >= need:
        return []
    st = v.get("first_failed")
    if st is None:
        return []
    out = []
    for name, c in ((v["stages"].get(st) or {}).get("checks") or {}).items():
        if c.get("pass"):
            continue
        val = c.get("value")
        if isinstance(val, list):
            val = f"[{len(val)}] " + ", ".join(str(x) for x in val[:limit]) + (" ..." if len(val) > limit else "")
        out.append(f"{st} {name}: {str(val)[:1500]} (need {c.get('threshold')})")
    return out or [f"verification stopped at {st}"]


def classify_sim(ff: dict[str, Any] | None, output: str = "") -> tuple[str, str]:
    """(role, kind) for a failed simulate. kind is ``code`` (an exception or compile error: the owner is certain) or
    ``mismatch`` (an assertion between the RTL and the model: the RTL is the first suspect)."""
    ff = ff or {}
    text = "\n".join([str(ff.get("where") or ""), *ff.get("message", []), *ff.get("cause", []), *ff.get("log_errors", []),
                      *ff.get("frames", [])]) or output          # outermost frame first, the innermost last
    if _HDL_ERR.search(text) or _HDL_ERR.search(output[-6000:]):
        return "rtl", "code"
    paths = [a or b for a, b in _FRAME.findall(text + "\n" + (output[-6000:] if not ff.get("frames") else ""))]
    own = [p for p in paths if "site-packages" not in p and "/cocotb" not in p and not p.endswith("cocotb_run.py")
           and not p.endswith("/runner.py")]
    cause_excs = [m.group(1) for x in ff.get("cause", []) for m in [re.match(r"^(\w*(?:Error|Exception|Exit))\b", x)] if m]
    msg_excs = [m.group(1) for x in ff.get("message", []) for m in [re.match(r"^(\w*(?:Error|Exception|Exit))\b", x)] if m]
    exc = cause_excs[-1] if cause_excs else (msg_excs[-1] if msg_excs else "")      # the simulator's own, if captured
    assertion = exc == "AssertionError" or (not exc and "assert" in text.lower())
    if own and not assertion:
        last = own[-1]
        if last.endswith("model.py"):
            return "model", "code"
        if "/tests/" in last or "/verif/" in last or last.startswith(("tests/", "verif/")):
            return "tests", "code"
    return "rtl", "mismatch"


def stage2_owners(ev: dict[str, Any], repeat: int = 0) -> tuple[dict[str, list[str]], str]:
    """Which roles must act on a failed stage-2 visit, with the failure text each one is given, and a signature of
    the failure (equal signatures on consecutive visits mean the last repair did not change it).

    ``repeat`` is how many consecutive earlier visits had this same signature."""
    owners: dict[str, list[str]] = {}
    sig: list[str] = []

    def add(role: str, text: str, tag: str) -> None:
        owners.setdefault(role, []).append(text)
        sig.append(f"{role}:{tag}")

    lint = ev.get("lint") or {}
    if not lint.get("ok"):
        add("rtl", "[lint] " + str(lint.get("text") or "lint not passing")[-1500:], "lint")
    c = ev.get("contract") or {}
    if not c.get("ok"):
        add("model", "[model contract] " + str(c.get("error") or "not checked")[-1200:], "contract")
    sim = ev.get("simulate") or {}
    mismatch_test = None
    if c.get("ok") and not sim.get("ok"):
        ff = sim.get("first_failure")
        role, kind = classify_sim(ff, str(sim.get("text") or ""))
        head = (f"first failing test {ff['test']}: " + " | ".join(ff.get("message", [])) + (f" ({ff['where']})" if ff.get("where") else "")
                + "".join("\n  cause: " + x for x in ff.get("cause", [])[:8])) if ff else ""
        text = "[simulate] " + head + "\n" + str(sim.get("text") or "")[-1500:]
        add(role, text, f"sim:{(ff or {}).get('test')}:{'|'.join((ff or {}).get('message', [])[:1])[:120]}")
        if kind == "mismatch":
            mismatch_test = (ff or {}).get("test")
    v = ev.get("verif") or {}
    need = ev.get("verif_level") or "V3"
    if not (v.get("reached") and v["reached"] >= need):
        fails = verif_failures(v, need)
        # the sim failure already covers `failing_tests`; everything the plan or bench lacks is the test writer's
        # (a missing model is the model writer's)
        covered = sim.get("ok") is False
        plan = [f for f in fails if not (covered and ("failing_tests" in f or "planned_tests_missing" in f))]
        if any("model_present" in f for f in plan):
            add("model", "[verification] " + "; ".join(f for f in plan if "model_present" in f), "model_present")
            plan = [f for f in plan if "model_present" not in f]
        if plan:
            add("tests", "[verification] " + "\n".join(plan), "verif:" + (v.get("first_failed") or "none"))
    if mismatch_test and repeat >= 1 and "tests" not in owners:
        owners["tests"] = [f"[simulate] the same failure survived a repair of the RTL: test {mismatch_test}. Check that the "
                           f"bench drives the ports as the spec says and compares the right outputs. "
                           + owners["rtl"][-1][:900]]
    if mismatch_test and repeat >= 2 and "model" not in owners:
        owners["model"] = [f"[independent check] your model disagreed with an independent check in test {mismatch_test}. "
                           f"Re-read spec.yaml for the behaviour that test covers and check your model against it."]
    if not owners:
        owners["rtl"] = ["[gates] " + " ".join(ev.get("other_fails") or ["a gate failed"])[:1500]]
        sig.append("rtl:other")
    owners = {r: owners[r] for r in ROLE_ORDER if r in owners}
    return owners, "|".join(sorted(sig))
