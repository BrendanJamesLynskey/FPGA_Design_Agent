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
    span = (f"The capture holds cycles {full[0]} to {full[-1]}; this answer covers cycles {cyc0} to {cyc1}, as asked."
            if cap is not whole else f"The window is cycles {cyc0} to {cyc1}.")
    first = (f"Triggered on {ttext}. Cycle 0 is sample {whole['timebase']['trigger_sample']} of "
             f"{whole['timebase']['samples']}{mhz}. {span}")
    if whole["timebase"].get("trigger_sample_from") == "trigger position":
        first += " (The capture file had no trigger column, so cycle 0 is the planned trigger position.)"
    L.append(first)
    L.append(f"At cycle 0: {at0}.")
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
            parts.append(f"{'when armed' if when == 'armed' else 'after upload'}: die {now.get('TEMPERATURE')} C, VCCINT {now.get('VCCINT')} V, VCCAUX "
                         f"{now.get('VCCAUX')} V, VCCBRAM {now.get('VCCBRAM')} V")
    if not parts:
        return ""
    v = VERDICT_TEXT.get(cond.get("verdict"), cond.get("verdict"))
    return ("Supply and temperature from the chip's own monitor (XADC) " + "; ".join(parts) + (f"; {v}." if v else "."))


VERDICT_TEXT = {"inside ROC": "inside the recommended operating conditions (ROC: the data sheet's supply and temperature ranges)",
                "outside ROC": "OUTSIDE the recommended operating conditions (ROC: the data sheet's supply and temperature ranges)",
                "not read": "conditions not read"}


_NUM = re.compile(r"0x[0-9a-fA-F]+|-?\d+(?:\.\d+)?")


def _dec(x: Any) -> str:
    return f"{float(x):g}"


def _channel_numbers(F: dict[str, Any], cap: dict[str, Any], name: str) -> tuple[set[int], set[str]]:
    """(values a hex number may quote, decimal numbers a sentence may quote) for one channel in the answered window:
    its values (in decimal only for a 1-bit signal), its change cycles (and the cycle before each), run starts and
    lengths, and its counts. Nothing from other channels or from outside the window."""
    f = F["channels"][name]
    ch = channel(cap, name)
    values = set(ch["samples"])
    dec: set[str] = set()
    if f["width"] == 1:
        dec |= {_dec(v) for v in values}
    for c, _old, _new in f["changes"]:
        dec |= {_dec(c), _dec(c - 1)}
    for st, ln in f.get("high_runs", []):
        dec |= {_dec(st), _dec(ln), _dec(st + ln - 1)}
    for k in ("n_changes", "n", "high_samples", "n_high_runs", "n_values"):
        if isinstance(f.get(k), int):
            dec.add(_dec(f[k]))
    for _v, k in f.get("values", []):
        dec.add(_dec(k))
    return values, dec


def unquoted_numbers(text: str, cap: dict[str, Any], asked: dict[str, Any] | None = None) -> list[str]:
    """Numbers in ``text`` that the capture does not support where they are quoted. Line by line, a number must be: a
    value of a channel the line names (hex; decimal only for 1-bit signals), a change cycle, run or count of such a
    channel within the answered window (``asked``, the trimmed capture; default the whole capture), a window bound, the
    trigger sample, the sample count, the clock, a value in the trigger condition (on the line that states it), a readback
    value (on the readback line) or an operating-condition reading (on the conditions line). Empty means every number is
    attributed. Any phrasing step must keep one channel per line or name the channel in the line it quotes."""
    asked = asked or cap
    F = facts(asked)
    full = cycles(cap)
    glob = {_dec(x) for x in (0, cap["timebase"]["trigger_sample"], cap["timebase"]["samples"], full[0], full[-1],
                               F["first_cycle"], F["last_cycle"]) if x is not None}
    if cap["timebase"].get("mhz"):
        glob.add(_dec(cap["timebase"]["mhz"]))
    per = {c["name"]: _channel_numbers(F, asked, c["name"]) for c in asked["channels"]}
    trig_nums = {t for c in cap["trigger"].get("conditions", []) for t in _NUM.findall(c.get("text") or "")}
    bad = []
    for line in text.splitlines():
        hexok: set[int] = set()
        decok = set(glob)
        for name, (vals, dec) in per.items():
            if re.search(r"(?<![\w.])" + re.escape(name) + r"(?![\w])", line):
                hexok |= vals
                decok |= dec
        if line.startswith("Triggered on"):
            for t in trig_nums:
                if t.lower().startswith("0x"):
                    hexok.add(int(t, 16))
                else:
                    decok.add(_dec(t))
        if line.startswith("Read back"):
            hexok |= {v for v in (cap.get("readback") or {}).values() if isinstance(v, int)}
        if "VCCINT" in line:
            for when in ("armed", "done"):
                for grp in ("now", "max", "min"):
                    decok |= {_dec(v) for v in (((cap.get("conditions") or {}).get(when) or {}).get(grp) or {}).values()}
        for tok in _NUM.findall(line):
            if tok.lower().startswith("0x"):
                if int(tok, 16) not in hexok:
                    bad.append(tok)
            elif _dec(tok) not in decok:
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
