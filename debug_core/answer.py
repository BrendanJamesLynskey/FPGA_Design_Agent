"""What the capture shows, in plain words, quoting only values that are in it (brief 50A); and cheap queries on a capture.

``facts(cap)`` reduces a capture to events: the value of every channel at the trigger, its changes, the runs of a 1-bit
signal, the values a bus took and for how long. ``answer(cap)`` writes those facts as sentences, with the channels the
question names first. No language model writes the answer: every number in it is formatted from a fact, and
``unquoted_numbers(text, cap)`` checks a text against the capture (any phrasing step must pass it).

``query(cap, {...})`` answers the agent's questions without handing it raw samples: value_at, first, count, changes,
runs, summary, and diverge (the first cycle where two captures of the same probes differ: hardware against simulation).
"""

from __future__ import annotations

import re
from typing import Any

from debug_core.capture import channel, cycles, trim

MAX_CHANGES = 6


def fmt(v: int, width: int) -> str:
    return str(v) if width == 1 else f"0x{v:0{(width + 3) // 4}X}"


def _changes(c: dict[str, Any], cyc: list[int]) -> list[tuple[int, int, int]]:
    s = c["samples"]
    return [(cyc[k], s[k - 1], s[k]) for k in range(1, len(s)) if s[k] != s[k - 1]]


def _runs(c: dict[str, Any], cyc: list[int], value: int = 1) -> list[tuple[int, int]]:
    out, start = [], None
    for k, v in enumerate(c["samples"]):
        if v == value and start is None:
            start = k
        if v != value and start is not None:
            out.append((cyc[start], k - start))
            start = None
    if start is not None:
        out.append((cyc[start], len(c["samples"]) - start))
    return out


def _holds(pattern: str, now: int, before: int | None) -> bool:
    w = len(pattern)
    for i, ch in enumerate(pattern):
        b = (now >> (w - 1 - i)) & 1
        pb = None if before is None else (before >> (w - 1 - i)) & 1
        if ch in "01" and b != int(ch):
            return False
        if ch == "R" and not (pb == 0 and b == 1):
            return False
        if ch == "F" and not (pb == 1 and b == 0):
            return False
        if ch == "B" and not (pb is not None and pb != b):
            return False
    return True


def facts(cap: dict[str, Any]) -> dict[str, Any]:
    cyc = cycles(cap)
    t0 = cap["timebase"]["trigger_sample"]
    n = cap["timebase"]["samples"]
    out: dict[str, Any] = {"samples": n, "trigger_sample": t0, "first_cycle": cyc[0], "last_cycle": cyc[-1],
                           "mhz": cap["timebase"].get("mhz"), "channels": {}}
    for c in cap["channels"]:
        s, w = c["samples"], c["width"]
        ch = _changes(c, cyc)
        f: dict[str, Any] = {"width": w, "path": c.get("path"), "at_trigger": s[t0],
                             "before_trigger": s[t0 - 1] if t0 > 0 else None,
                             "after_trigger": s[t0 + 1] if t0 + 1 < n else None,
                             "first": s[0], "last": s[-1], "n_changes": len(ch), "changes": ch[:MAX_CHANGES], "n": n}
        vals: dict[int, int] = {}
        for v in s:
            vals[v] = vals.get(v, 0) + 1
        if len(vals) <= 8:
            f["values"] = sorted(vals.items(), key=lambda kv: -kv[1])
        else:
            f["n_values"] = len(vals)
            f["min"], f["max"] = min(vals), max(vals)
        if w == 1:
            f["high_samples"] = vals.get(1, 0)
            f["high_runs"] = _runs(c, cyc, 1)[:MAX_CHANGES]
            f["n_high_runs"] = len(_runs(c, cyc, 1))
        out["channels"][c["name"]] = f
    conds = []
    for cond in cap["trigger"].get("conditions", []):
        try:
            c = channel(cap, cond["probe"])
        except KeyError:
            continue
        now = c["samples"][t0]
        before = c["samples"][t0 - 1] if t0 > 0 else None
        conds.append({"probe": cond["probe"], "text": cond.get("text"), "holds": _holds(cond["pattern"], now, before)})
    comb = cap["trigger"].get("combine", "AND")
    out["trigger"] = {"combine": comb, "conditions": conds,
                      "holds": (all if comb == "AND" else any)(x["holds"] for x in conds) if conds else None}
    return out


def _channel_sentence(name: str, f: dict[str, Any], cyc0: int, cyc1: int) -> str:
    w = f["width"]
    if f["n_changes"] == 0:
        return f"{name} held {fmt(f['first'], w)} for the whole window (cycles {cyc0} to {cyc1})."
    if w == 1:
        runs = f["high_runs"]
        parts = [f"high for {ln} cycle{'s' if ln != 1 else ''} from cycle {st}" for st, ln in runs[:3]]
        more = f" and {f['n_high_runs'] - 3} more high runs" if f["n_high_runs"] > 3 else ""
        return (f"{name} was {fmt(f['at_trigger'], 1)} at the trigger; " + "; ".join(parts) + more +
                f" ({f['high_samples']} of {f['n']} samples high).")
    if f["n_changes"] <= 3:
        segs, prev_c = [], cyc0
        for c, old, new in f["changes"]:
            segs.append(f"{fmt(old, w)} from cycle {prev_c} to {c - 1}")
            prev_c = c
        segs.append(f"{fmt(f['changes'][-1][2], w)} from cycle {prev_c} to {cyc1}")
        return f"{name} was " + ", then ".join(segs) + "."
    if "values" in f:
        total = sum(k for _, k in f["values"])
        vs = ", ".join(f"{fmt(v, w)} for {k} of {total} samples" for v, k in f["values"])
        return (f"{name} was {fmt(f['at_trigger'], w)} at the trigger and changed {f['n_changes']} times; it was " + vs + ".")
    first = ", ".join(f"cycle {c}: {fmt(o, w)} -> {fmt(nw, w)}" for c, o, nw in f["changes"][:3])
    return (f"{name} was {fmt(f['at_trigger'], w)} at the trigger and changed {f['n_changes']} times "
            f"({f['n_values']} values, {fmt(f['min'], w)} to {fmt(f['max'], w)}); first changes: {first}.")


def answer(cap: dict[str, Any], question: str | None = None) -> dict[str, Any]:
    """{"text": the answer, "facts": facts(cap), "check": unquoted numbers (must be empty)}. The answer covers the window
    the request asked for (the ILA's window is a power of two and usually longer); the capture keeps every sample."""
    full = cycles(cap)
    req = (cap.get("window") or {}).get("requested") or {}
    lo = -int(req["pre"]) if req.get("pre") is not None else full[0]
    hi = int(req["post"]) if req.get("post") is not None else full[-1]
    whole = cap
    if (lo, hi) != (full[0], full[-1]):
        cap = trim(cap, lo, hi)
    F = facts(cap)
    q = (question or cap.get("question") or "").lower()
    cyc0, cyc1 = F["first_cycle"], F["last_cycle"]
    L = []
    trig = F["trigger"]
    tw = " AND " if trig["combine"] == "AND" else " OR "
    ttext = tw.join(c["text"] or c["probe"] for c in trig["conditions"]) or "(no condition)"
    mhz = f" at {F['mhz']:g} MHz" if F.get("mhz") else ""
    at0 = ", ".join(f"{n} = {fmt(f['at_trigger'], f['width'])}" for n, f in F["channels"].items())
    span = (f"the capture holds cycles {full[0]} to {full[-1]}; this answer covers cycles {cyc0} to {cyc1} as asked"
            if cap is not whole else f"window cycles {cyc0} to {cyc1}")
    L.append(f"Triggered on {ttext}: cycle 0 is sample {whole['timebase']['trigger_sample']} of "
             f"{whole['timebase']['samples']}{mhz} ({span}). At cycle 0: {at0}.")
    if trig["holds"] is False:
        bad = [c["probe"] for c in trig["conditions"] if not c["holds"]]
        L.append(f"WARNING: the trigger condition does not hold at cycle 0 (not met: {', '.join(bad)}); the capture "
                 "may have triggered on something else.")
    names = list(F["channels"])
    names.sort(key=lambda n: (n.lower() not in q and (F["channels"][n].get("path") or "").lower() not in q))
    for n in names:
        L.append(_channel_sentence(n, F["channels"][n], cyc0, cyc1))
    rb = cap.get("readback") or {}
    if rb:
        L.append("Read back over the shell after the capture: " +
                 ", ".join(f"{k} = 0x{v:08X}" for k, v in rb.items() if isinstance(v, int)) + ".")
    cond = cap.get("conditions") or {}
    ctext = conditions_text(cond)
    if ctext:
        L.append(ctext)
    text = "\n".join(L)
    return {"text": text, "facts": F, "check": unquoted_numbers(text, whole, cap)}


def conditions_text(cond: dict[str, Any]) -> str:
    parts = []
    for when in ("armed", "done"):
        c = cond.get(when) or {}
        if c.get("read"):
            now = c.get("now", {})
            parts.append(f"{when}: die {now.get('TEMPERATURE')} C, VCCINT {now.get('VCCINT')} V, VCCAUX "
                         f"{now.get('VCCAUX')} V, VCCBRAM {now.get('VCCBRAM')} V")
    if not parts:
        return ""
    v = cond.get("verdict")
    return "Operating conditions (XADC over JTAG) " + "; ".join(parts) + (f"; {v}." if v else ".")


def _allowed_numbers(cap: dict[str, Any]) -> set[str]:
    F = facts(cap)
    ok: set[str] = set()

    def add(x: Any) -> None:
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            ok.add(f"{x:g}" if isinstance(x, float) else str(x))
        elif isinstance(x, str):
            ok.update(re.findall(r"-?\d+(?:\.\d+)?", x))
    for k in ("samples", "trigger_sample", "first_cycle", "last_cycle", "mhz"):
        add(F.get(k))
    for c in cap["channels"]:
        w = c["width"]
        for v in set(c["samples"]):
            ok.add(fmt(v, w).lower())
            ok.add(str(v))
    for f in F["channels"].values():
        for k, v in f.items():
            if isinstance(v, int):
                add(v)
            elif isinstance(v, list):
                for item in v:
                    for x in (item if isinstance(item, (tuple, list)) else [item]):
                        add(x)
                        if isinstance(x, int):
                            add(x - 1)       # "to cycle c-1"
    for v in (cap.get("readback") or {}).values():
        if isinstance(v, int):
            ok.add(f"0x{v:08x}")
            ok.add(str(v))
    for when in ("armed", "done"):
        for grp in ("now", "max", "min"):
            for v in (((cap.get("conditions") or {}).get(when) or {}).get(grp) or {}).values():
                add(float(v))
                ok.add(str(v))
    for c in cap["trigger"].get("conditions", []):
        add(c.get("text"))
    ok.update({"0", "1", "2", "3"})
    return {x.lower() for x in ok}


def unquoted_numbers(text: str, cap: dict[str, Any], *more: dict[str, Any]) -> list[str]:
    """Numbers in ``text`` that are not values, cycles, counts or conditions of the capture (or of its trimmed views in
    ``more``); empty means every number is quoted from the capture."""
    allowed = set().union(*(_allowed_numbers(c) for c in (cap, *more)))
    bad = []
    for tok in re.findall(r"0x[0-9a-fA-F]+|-?\d+(?:\.\d+)?", text):
        t = tok.lower()
        if t in allowed or (t.startswith("0x") and str(int(t, 16)) in allowed and
                            any(a.startswith("0x") and int(a, 16) == int(t, 16) for a in allowed if a.startswith("0x"))):
            continue
        try:
            if not t.startswith("0x") and f"{float(t):g}" in allowed:
                continue
        except ValueError:
            pass
        bad.append(tok)
    return bad


# --- queries ------------------------------------------------------------------------------------------------------------------

_CMP = {"==": lambda a, b: a == b, "!=": lambda a, b: a != b, "<": lambda a, b: a < b, "<=": lambda a, b: a <= b,
        ">": lambda a, b: a > b, ">=": lambda a, b: a >= b}


def _val(v: Any) -> int:
    return int(v, 0) if isinstance(v, str) else int(v)


def query(cap: dict[str, Any], q: dict[str, Any], other: dict[str, Any] | None = None) -> dict[str, Any]:
    op = q.get("op")
    cyc = cycles(cap)
    if op == "summary":
        return {"ok": True, "facts": facts(cap)}
    if op == "diverge":
        if other is None:
            return {"ok": False, "why": "diverge needs a second capture"}
        return {"ok": True, **diverge(cap, other)}
    try:
        c = channel(cap, q["channel"])
    except KeyError as e:
        return {"ok": False, "why": str(e)}
    s, w = c["samples"], c["width"]
    if op == "value_at":
        k = int(q["cycle"]) - cyc[0]
        if not 0 <= k < len(s):
            return {"ok": False, "why": f"cycle {q['cycle']} is outside the window {cyc[0]}..{cyc[-1]}"}
        return {"ok": True, "cycle": int(q["cycle"]), "value": s[k], "text": fmt(s[k], w)}
    if op in ("first", "count"):
        f = _CMP.get(q.get("cmp", "=="))
        if f is None:
            return {"ok": False, "why": f"cmp must be one of {sorted(_CMP)}"}
        v = _val(q["value"])
        start = int(q.get("from_cycle", cyc[0])) - cyc[0]
        hits = [cyc[k] for k in range(max(0, start), len(s)) if f(s[k], v)]
        if op == "count":
            return {"ok": True, "count": len(hits), "of": len(s) - max(0, start)}
        return {"ok": True, "cycle": hits[0] if hits else None, "found": bool(hits)}
    if op == "changes":
        ch = _changes(c, cyc)
        lim = int(q.get("limit", 20))
        return {"ok": True, "n": len(ch), "changes": [{"cycle": a, "from": fmt(b, w), "to": fmt(d, w)} for a, b, d in ch[:lim]]}
    if op == "runs":
        r = _runs(c, cyc, _val(q.get("value", 1)))
        lim = int(q.get("limit", 20))
        return {"ok": True, "n": len(r), "runs": [{"start": a, "length": b} for a, b in r[:lim]]}
    return {"ok": False, "why": f"unknown query op {op!r}; one of value_at, first, count, changes, runs, summary, diverge"}


def diverge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """The first cycle (relative to each capture's trigger) where the channels the two captures share differ."""
    names = [c["name"] for c in a["channels"] if any(d["name"] == c["name"] for d in b["channels"])]
    ca, cb = cycles(a), cycles(b)
    lo, hi = max(ca[0], cb[0]), min(ca[-1], cb[-1])
    for cy in range(lo, hi + 1):
        diff = []
        for n in names:
            x, y = channel(a, n), channel(b, n)
            va, vb = x["samples"][cy - ca[0]], y["samples"][cy - cb[0]]
            if va != vb:
                diff.append({"channel": n, "a": fmt(va, x["width"]), "b": fmt(vb, x["width"])})
        if diff:
            return {"diverged": True, "cycle": cy, "differences": diff, "compared": names, "range": [lo, hi]}
    return {"diverged": False, "compared": names, "range": [lo, hi]}
