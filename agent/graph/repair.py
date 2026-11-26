"""Repair, don't regenerate: route a stage-2 failure to the role that owns it (brief 05c2, fix 1).

Principle (stage-machine design): a failure is evidence about one artefact. Re-running every writer from scratch
re-breaks parts that passed (Opus run 2), and hands the model no signal about what to change. So the graph:

1. traces each failing gate or tool result to the role that wrote the failing artefact, from the evidence only
   (never from the model): the contract check and a traceback in ``model.py`` -> ``model``; a plan or traceability
   failure, or a traceback in the bench -> ``tests``; lint, an HDL compile error, or a behavioural mismatch
   between the RTL and the model -> ``rtl``;
2. runs only those roles, each handed the failures that are its own and its previous output to edit;
3. freezes every other artefact (it is not rewritten by anyone this visit);
4. escalates when a repair did not change the failure: the same signature twice adds the Verifier to a
   behavioural mismatch (the bench may be wrong), three times adds the Modeller.

The Modeller's blindness to the RTL holds: the Modeller is shown its own contract or traceback text, or - on the third
repeat - only the NAME of the test that disagrees, never RTL, RTL output or the other artefacts.

Pure functions over tool results: CI tests them with recorded evidence.
"""

from __future__ import annotations

from agent.core.prompts import load as _p

import re
from typing import Any

ROLE_ORDER = ("model", "tests", "rtl")
#: V2 checks that fail only because a simulation test failed (brief 82P6, P1): while the simulation fails they are covered by
#: that failure, so they do not make the Verifier an owner and do not silence the repeat hint
SIM_CONSEQUENCES = ("failing_tests", "planned_tests_missing", "constrained_random_test_ran", "assertions_bound_zero_failures")
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
        if isinstance(val, str) and val.startswith("not evaluated"):
            continue          # a consequence of another failed check (05h): the line that names the cause is enough
        if isinstance(val, list):
            val = f"[{len(val)}] " + ", ".join(str(x) for x in val[:limit]) + (" ..." if len(val) > limit else "")
        if c.get("why"):          # 05j: the reason in plain words (the hidden precondition when the value looks fine)
            out.append(f"{st} {name}: {c['why']} [value {str(val)[:300]}, need {c.get('threshold')}]")
            continue
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


def constants_holder_texts(c: dict | None) -> dict[str, str]:
    """Brief 82P6: a ``CONST-ID-01`` that persisted into a later visit (the gate marks the table ``persisted``) goes to the owner
    of every artefact that carries the wrong value, not only to the RTL role that rewrote its binding. Returns role -> text for
    the Modeller and the Verifier (the RTL role has the finding already; spec.yaml is routed to the clarify stage by
    ``stages.classify``). Each text names only that role's own file and the value derived from the spec's quoted string, so the
    Modeller still never sees the RTL."""
    out: dict[str, str] = {}
    if not (c or {}).get("persisted"):
        return out
    for f in (c or {}).get("findings") or []:
        if f.get("code") != "CONST-ID-01" or not f.get("blocking"):
            continue
        for h in f.get("holders") or []:
            if h.get("role") in ("model", "tests") and h["role"] not in out:
                out[h["role"]] = (
                    f"[derived constants] the shell design ID is derived from the spec's quoted string {f.get('string')!r} (four ASCII "
                    f"characters, most significant first): 0x{f['expected']:08X}. {h['file']} line {h['line']} gives the design ID as "
                    f"0x{f['bound']:08X} ({h['text']!r}). That is a different constant (the endpoint's own identification word, if "
                    f"the spec has one, is separate). Set your design ID to 0x{f['expected']:08X} ({f['expected']}).")
    return out


def report_advisory_text(r: dict | None, limit: int = 5) -> str:
    """The advisories of the report checks, one line each, for a repair visit's feedback (they never block)."""
    adv = (r or {}).get("advisories") or []
    if not adv:
        return ""
    return "\n[advisories, not blocking] " + "; ".join(f"{a['code']} {a.get('where', '')}: {a.get('message', '')[:160]}" for a in adv[:limit])


def stage2_owners(ev: dict[str, Any], repeat: int = 0, events: list[dict[str, Any]] | None = None) -> tuple[dict[str, list[str]], str]:
    """Which roles must act on a failed stage-2 visit, with the failure text each one is given, and a signature of
    the failure (equal signatures on consecutive visits mean the last repair did not change it).

    ``repeat`` is how many consecutive earlier visits had this same signature. ``events`` (82P6), when given, receives one dict per
    routing decision of the P1 and constants-routing paths, for the run record."""
    owners: dict[str, list[str]] = {}
    sig: list[str] = []

    def add(role: str, text: str, tag: str) -> None:
        owners.setdefault(role, []).append(text)
        sig.append(f"{role}:{tag}")

    lint = ev.get("lint") or {}
    if not lint.get("ok"):
        add("rtl", "[lint] " + str(lint.get("text") or "lint not passing")[-1500:], "lint")
    std = ev.get("standards_fails") or []
    if std:
        add("rtl", "[design standards] " + "\n".join(std)[:1800], "standards")
    from agent.graph.stages import constants_stage
    k_ok, k_why = constants_stage(ev.get("constants"))
    if not k_ok:
        add("rtl", "[derived constants] " + "\n".join(k_why)[:1800], "constants")
        for role, text in constants_holder_texts(ev.get("constants")).items():     # 82P6: a persisting CONST-ID-01
            add(role, text, "constants")
            if events is not None:
                events.append({"event": "const_id_routed_to_holder", "role": role})
    from agent.graph.stages import report_gates_stage
    g_ok, g_why = report_gates_stage(ev.get("report_gates"))
    if not g_ok:                                       # brief 209a: the synthesis report says the design cannot close
        add("rtl", "[report gates] " + "\n".join(g_why)[:1800] + report_advisory_text(ev.get("report_gates")), "report_gates")
    c = ev.get("contract") or {}
    if not c.get("ok"):
        add("model", "[model contract] " + str(c.get("error") or "not checked")[-1200:], "contract")
    sim = ev.get("simulate") or {}
    mismatch_test, sim_text = None, ""
    if c.get("ok") and not sim.get("ok"):
        ff = sim.get("first_failure")
        role, kind = classify_sim(ff, str(sim.get("text") or ""))
        head = (f"first failing test {ff['test']}: " + " | ".join(ff.get("message", [])) + (f" ({ff['where']})" if ff.get("where") else "")
                + "".join("\n  cause: " + x for x in ff.get("cause", [])[:8])) if ff else ""
        fc = (sim.get("first_check") or {}).get("text")           # brief 213 (R1): the first failing check replaces the raw log tail
        text = "[simulate] " + head + "\n" + (fc if fc else str(sim.get("text") or "")[-1500:])
        add(role, text, f"sim:{(ff or {}).get('test')}:{'|'.join((ff or {}).get('message', [])[:1])[:120]}")
        if kind == "mismatch":
            mismatch_test, sim_text = (ff or {}).get("test"), text
    v = ev.get("verif") or {}
    need = ev.get("verif_level") or "V3"
    if not (v.get("reached") and v["reached"] >= need):
        fails = verif_failures(v, need)
        # the sim failure already covers `failing_tests`; everything the plan or bench lacks is the Verifier's
        # (a missing model is the Modeller's)
        covered = sim.get("ok") is False
        plan = [f for f in fails if not (covered and any(k in f for k in SIM_CONSEQUENCES))]
        if events is not None and covered and len(plan) < len(fails):
            events.append({"event": "p1_consequences_covered", "checks": [k for k in SIM_CONSEQUENCES if any(k in f for f in fails)]})
        if any("model_present" in f for f in plan):
            add("model", "[verification] " + "; ".join(f for f in plan if "model_present" in f), "model_present")
            plan = [f for f in plan if "model_present" not in f]
        if plan:
            add("tests", "[verification] " + "\n".join(plan), "verif:" + (v.get("first_failed") or "none"))
    if mismatch_test and repeat >= 1:
        # P1 (82P6): the bench's owner always gets the repeat hint with the failing assertion, whatever else it owns
        if events is not None:
            events.append({"event": "p1_hint_sent", "test": mismatch_test, "bench_owner_for_other_reasons": "tests" in owners})
        owners.setdefault("tests", []).append(_p("graph/repair/stage2_owners_1").format(mismatch_test) + sim_text[:900])
    if mismatch_test and repeat >= 2 and "model" not in owners:
        owners["model"] = [_p("graph/repair/stage2_owners_2").format(mismatch_test)]
    rg = ev.get("regrade") or {}
    if rg.get("blocking") and rg.get("digest"):             # brief 213 (R3): a calibrated fresh-stimulus divergence on a design every gate accepted
        add("rtl", str(rg["digest"])[:2600], "regrade")
    stt = ev.get("spec_test") or {}
    if stt.get("blocks") and not owners:             # 08f: the independent spec-only bench failed and triage blamed the design
        add("rtl", str(stt.get("evidence") or _p("graph/repair/stage2_owners_3"))[:1800], str(stt.get("sig") or "spectest"))
    if not owners:
        owners["rtl"] = ["[gates] " + " ".join(ev.get("other_fails") or ["a gate failed"])[:1500]
                         + (("\n[build output]\n" + ev["build_output"][-1800:]) if ev.get("build_output") else "")]
        sig.append("rtl:other")
    owners = {r: owners[r] for r in ROLE_ORDER if r in owners}
    return owners, "|".join(sorted(sig))


_GATE_OF_TAG = {"lint": "lint", "standards": "design standards", "constants": "derived constants", "contract": "model contract",
                "model_present": "verification (model present)", "spectest": "spec test", "other": "other gates",
                "sim": "simulate", "report_gates": "report gates", "regrade": "fresh-stimulus regrade"}


def stop_diagnosis(n: int, limit: int, state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Brief 82P6, P3: the stop reason of a stage that ran out of visits, and the same facts as a record. The reason keeps the
    prefix ``stage N visited more than L times`` (the handover reads it) and adds what the last gate evaluation says: the failing
    gate(s), the role(s) that owned the failure, the failing assertion, and how many consecutive visits had the same failure
    signature. Facts only, from the evidence the graph already holds (tool output, never a prompt)."""
    ev = state.get("evidence") or {}
    owners = state.get("owners") or {}
    sig = str(state.get("sig") or "")
    gates: list[str] = []
    roles: list[str] = []
    for part in sig.split("|"):
        role, _, tag = part.partition(":")
        key = tag.split(":")[0].split(" ")[0]
        if key.startswith("verif"):
            g = "verification " + (tag.partition(":")[2] or "V2")
        else:
            g = _GATE_OF_TAG.get(key) or key
        if g and g not in gates:
            gates.append(g)
        if role and role not in roles:
            roles.append(role)
    if not gates:                                        # a stage other than 2: the gate lines the stage failed on
        gates = [str(f)[:90] for f in (state.get("fails") or [])[:2]]
    ff = ((ev.get("simulate") or {}).get("first_failure")) or {}
    assertion = ""
    if ff:
        msgs = [m for m in ff.get("message", []) if "cocotb run failed" not in m] or ff.get("message", [])    # skip the wrapper's line
        assertion = f"{ff.get('test')}: " + " | ".join(msgs[:2]) + (f" ({ff['where']})" if ff.get("where") else "")
    elif (ev.get("verif") or {}).get("first_failed"):
        vf = verif_failures(ev.get("verif"), ev.get("verif_level") or "V3", limit=3)
        assertion = vf[0] if vf else ""
    assertion = assertion[:240]
    rep = int(state.get("repeat") or 0)
    detail = {"stage": n, "limit": limit, "gates": gates, "roles": roles, "owners_last_visit": sorted(owners),
              "last_failing_assertion": assertion or None, "same_signature_visits": rep + 1 if sig else None,
              "last_fails": [str(f)[:200] for f in (state.get("fails") or [])[:4]],
              **({"ledger": state["ledger"]} if state.get("ledger") else {})}
    why = f"stage {n} visited more than {limit} times; last failing gate: {', '.join(gates) or 'none recorded'}"
    if roles:
        why += f"; owned by the {'/'.join(roles)} role"
    if assertion:
        why += f"; last failing assertion: {assertion}"
    if sig and rep >= 1:
        why += f"; the same failure on {rep + 1} consecutive visits"
    return why, detail
