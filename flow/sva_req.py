#!/usr/bin/env python3
"""Requirement to assertion (brief 218, part 2): an SVA property for each checkable requirement, a back-translation to English that a
different reader compares with the requirement, and a proof the formal flow runs, with a reachable cover of the trigger.

    requirement text (and the structured L2 fields when brief 227 supplies them) + the design's port list
      -> generator (one model call) -> {kind, ante, cons}          the property, in the house's three forms (same cycle, next cycle, reset)
      -> back-translator (another model, sees only the property) -> one English sentence
      -> compare (CODE, never a model)                              mismatch: the property is discarded, with the reason
      -> SymbiYosys: bmc + prove + cover                            cover = the trigger (``<name>__ante``) is reachable
      -> evidence on the requirement's row

**What counts as evidence** (research/228 section 8, accepted): a property that is *proved* or *bounded-checked* **and** whose trigger has a
reachable cover. A proof whose trigger can never happen is vacuous and is recorded as such, never as evidence (the 228 saturation example
proves vacuously at N=100,000). A failed assertion is a finding (the property is wrong, or the design is), recorded with its counterexample,
never installed. Only an evidenced property is written to ``verif/formal/sva_<id>.sby``, tagged ``# req: <id>``, where the traceability
matrix finds it like any formal job.

**What it cannot do.** It does not know the RTL (the generator sees the spec's ports, never the design: the same blindness as the Verifier).
It checks one clock domain: a row whose signals span two clocks is simulation-only unless the spec states a clock relation. The wrapper
asserts reset in the first cycle only (reset rows: free reset after the third cycle), so a mid-run reset is not explored for the other kinds;
the evidence file says so. Bounded results hold to the depth shown. The comparison is a word-and-number check, not understanding: it catches a
changed latency, a dropped negation and a signal that is not in the requirement; it does not catch every misreading, which is why the
original English stays the thing the user confirms.

Run from the command line on a design: ``python -m flow.sva_req <design> [--ids REQ-01,REQ-02] [--no-formal]`` needs the claude CLI for
the two model calls (the purposes ``assertgen`` and ``assertback`` of the model table in the agent; here the two ``--gen-model`` and ``--back-model``
flags); ``--from-file replies.json`` replays recorded replies (tests, and re-judging without calling a model).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "fpga-force/req-sva/v1"
DIR_REL = ("build", "verif", "sva")
EVIDENCE = "evidence.json"
KINDS = ("same", "next", "reset")
MAX_PAST = 16
PARTIAL_BELOW = 0.6      # a property whose back-translation covers less of the requirement's words is marked partial: evidence of part of the row
BMC_DEPTH, PROVE_DEPTH, COVER_DEPTH = 24, 12, 24
TASK_TIMEOUT_S = 180       # per task: a task that does not finish is an `error`, never evidence (z3 took over 4 minutes on a 32-bit CRC core where yices took one second)

# ---- which rows ---------------------------------------------------------------------------------------------------------------------------
#: wording of a requirement that is a cycle-level property of the ports (something an assertion can say)
TEMPORAL = re.compile(r"\b(when|whenever|while|within|after|before|until|never|always|must not|only if|if|every|each|cycle|cycles|clock|"
                      r"asserted|deasserted|asserts|deasserts|high|low|reset|valid|ready|latency|stays|holds|held|next|same|simultaneous|"
                      r"at most|at least|exactly|no more than|pulse)\b", re.I)
#: wording of a requirement that is a budget, a board fact or a document, which no assertion states
NOT_A_PROPERTY = re.compile(r"\b(lut|luts|flip-?flops?|bram|dsp|wns|slack|fmax|mhz|ghz|watt|power|resource|utili[sz]ation|pin|pins|"
                            r"iostandard|constraint|xdc|bitstream|datasheet|documented|readme|board|led colour|jtag programming)\b", re.I)


def spec_of(design: Path) -> dict[str, Any]:
    return yaml.safe_load((Path(design) / "spec.yaml").read_text()) or {}


_DIRS = {"in": "in", "input": "in", "out": "out", "output": "out", "inout": "inout", "internal": "internal", "wire": "internal"}


def ports_of(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """The module's ports as ``{name, dir, width, clock, note}``. ``dir`` is in, out, inout or internal (a spec's net that has no pin: a register
    port inside the top); the spec may write ``dir`` or ``direction``, ``in`` or ``input``. A port whose width is not a number has ``width: None``."""
    out = []
    for p in spec.get("ports") or []:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        w = p.get("width", 1)
        try:
            w = int(w)
        except (TypeError, ValueError):
            w = None
        d = _DIRS.get(str(p.get("dir", p.get("direction", "in"))).lower(), "in")
        out.append({"name": str(p["name"]), "dir": d, "width": w, "clock": p.get("clock"),
                    "note": str(p.get("note") or p.get("board_pin_role") or p.get("pin_role") or p.get("role") or "")})
    return out


def clocks_of(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """The clocks as ``{name, port, ...}``: a spec that names only ``name`` (the clock is the port of that name) is accepted."""
    return [{**c, "port": c.get("port") or c["name"]} for c in spec.get("clocks") or [] if isinstance(c, dict) and (c.get("port") or c.get("name"))]


def reset_of(spec: dict[str, Any]) -> tuple[str | None, bool]:
    """(reset port, active_low)."""
    r = spec.get("reset") or {}
    port = (r.get("port") or r.get("name")) if isinstance(r, dict) else None
    return (str(port) if port else None), "low" in str((r or {}).get("polarity", "active_low")).replace("-", "_") and "high" not in str((r or {}).get("polarity", ""))


# ---- the module the properties are about --------------------------------------------------------------------------------------------------
_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
_MODULE = re.compile(r"\bmodule\s+(?:automatic\s+)?(\w+)\s*(?:#\s*\(.*?\)\s*)?\((.*?)\)\s*;", re.S)
_PORTW = re.compile(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]")


def rtl_modules(files: list[Path]) -> dict[str, list[dict[str, Any]]]:
    """``{module: [{name, dir, width}]}`` from the ANSI port lists of the HDL files (interfaces only: nothing of a module's body is read).
    A module with a port whose width is not a plain ``[N:M]`` is left out."""
    mods: dict[str, list[dict[str, Any]]] = {}
    for f in files:
        try:
            text = _COMMENT.sub(" ", Path(f).read_text(errors="replace"))
        except OSError:
            continue
        text = re.sub(r"^\s*`\w+.*$", " ", text, flags=re.M)                # ifdef / ifndef / else / endif lines: both branches stay
        for m in _MODULE.finditer(text):
            ports, cur, ok = [], "in", True
            for item in re.split(r",", m.group(2)):
                t = item.strip()
                if not t:
                    continue
                dm = re.match(r"(input|output|inout)\b", t)
                if dm:
                    cur = _DIRS[dm.group(1)]
                    t = t[dm.end():].strip()
                t = re.sub(r"^(?:logic|wire|reg|var|signed)\b\s*", "", t).strip()
                wm = _PORTW.match(t)
                if wm:
                    w, t = abs(int(wm.group(1)) - int(wm.group(2))) + 1, t[wm.end():].strip()
                elif t.startswith("["):
                    ok = False
                    break
                else:
                    w = 1
                nm = re.match(r"(\w+)\s*$", t.split("=")[0].strip())
                if not nm:
                    ok = False
                    break
                ports.append({"name": nm.group(1), "dir": cur, "width": w})
            if ok and ports:
                mods.setdefault(m.group(1), ports)
    return mods


_KW = {"module", "endmodule", "if", "else", "for", "while", "always", "always_ff", "always_comb", "always_latch", "assign", "case", "casez", "endcase", "function",
       "endfunction", "task", "endtask", "begin", "end", "generate", "endgenerate", "initial", "input", "output", "inout", "logic", "wire", "reg", "parameter",
       "localparam", "genvar", "integer", "int", "bit", "typedef", "enum", "struct", "return", "assert", "assume", "cover", "property", "import", "package",
       "endpackage", "default", "automatic", "static", "var", "signed", "unsigned", "posedge", "negedge", "or", "and", "not"}
_INST = re.compile(r"(?m)^\s*([A-Za-z_]\w*)(?:\s*#\s*\([^;]*?\)\s*|\s+)([A-Za-z_]\w*)\s*\(")


def undefined_cells(files: list[Path]) -> dict[str, set[str]]:
    """``{module: cell types it instantiates that no file defines}`` (Xilinx primitives such as MMCME4_BASE, or anything missing). Open-source Yosys
    cannot elaborate a module with such a cell, so a module without them is preferred as the one to state properties about."""
    texts, defined = {}, set()
    for f in files:
        try:
            t = _COMMENT.sub(" ", Path(f).read_text(errors="replace"))
        except OSError:
            continue
        for m in re.finditer(r"\bmodule\s+(?:automatic\s+)?(\w+)", t):
            defined.add(m.group(1))
        for m in re.finditer(r"\bmodule\s+(?:automatic\s+)?(\w+)(.*?)\bendmodule\b", t, re.S):
            texts.setdefault(m.group(1), m.group(2))
    out = {}
    for name, body in texts.items():
        body = re.sub(r"^\s*`\w+.*$", " ", body, flags=re.M)
        out[name] = {c for c, _ in _INST.findall(body) if c not in _KW and c not in defined}
    return out


def effective_spec(design: Path, spec: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """``(spec', how)``: the spec with ``top`` and ``ports`` of the module the properties are about, and a sentence saying which module and why.

    The spec's ``top`` is used when it exists in the RTL and its ports cover the spec's. Otherwise (a register core behind a bus module, where
    the spec lists the register port as internal nets) the RTL module whose ports match the most spec port names is used: those ports are where the
    requirement can be seen. The clock and reset ports are the ones of that module named by the spec (``clk`` when the spec lists two clocks, one
    derived from the other)."""
    files = sources_of(design)
    mods, unknown = rtl_modules(files), undefined_cells(files)
    want = {p["name"] for p in ports_of(spec)}
    top = str(spec.get("top") or spec.get("name") or "")

    def score(name: str) -> int:
        return len({p["name"] for p in mods[name]} & want)
    best = max(mods, key=lambda n: (score(n) >= 2 and not unknown.get(n), score(n), n == top, -len(mods[n])), default=None)
    if best is None or score(best) < 2:
        return spec, "the spec's own top and port list (no RTL module's ports match them)"
    ports = []
    note = {p["name"]: p["note"] for p in ports_of(spec)}
    for p in mods[best]:
        ports.append({**p, "dir": {"in": "in", "out": "out"}.get(p["dir"], p["dir"]), "note": note.get(p["name"], "")})
    names = {p["name"] for p in ports}
    clocks = [c for c in clocks_of(spec) if c["port"] in names] or [{"name": n, "port": n} for n in ("clk", "clock", "clk_i") if n in names][:1]
    if "clk" in names:                           # the register-port clock first: a second clock input (a reference clock) is a free input of the wrapper
        clocks = [next((c for c in clocks if c["port"] == "clk"), {"name": "clk", "port": "clk"}), *[c for c in clocks if c["port"] != "clk"]]
    rport, low = reset_of(spec)
    if rport not in names:
        rport = next((n for n in ("rst", "reset", "rst_n", "resetn", "reset_n") if n in names), None)
        low = bool(rport and rport.endswith(("_n", "n")) and rport != "rst")
    return ({**spec, "top": best, "ports": [{"name": p["name"], "dir": p["dir"], "width": p["width"], "note": p["note"]} for p in ports], "clocks": clocks,
             "reset": {"port": rport, "polarity": "active_low" if low else "active_high"} if rport else {}},
            f"module `{best}`" + ("" if best == top else f" (the spec's top `{top}` has primitives and a bus the properties cannot see through; "
                                                          f"this module carries {score(best)} of the spec's ports)"))


def has_clock_relation(spec: dict[str, Any]) -> bool:
    """True when the spec states how its clocks relate (an ``assumptions`` entry or a ``clock_relations`` list naming the relation)."""
    if spec.get("clock_relations"):
        return True
    for a in spec.get("assumptions") or []:
        t = json.dumps(a).lower() if not isinstance(a, str) else a.lower()
        if "clock" in t and any(w in t for w in ("phase", "ratio", "relation", "synchronous", "same source", "derived from", "integer multiple")):
            return True
    return False


def select(spec: dict[str, Any], ids: list[str] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """``(candidates, skipped)``: the requirements an assertion can state, and each skipped row with its reason.

    A row is skipped when: its proof methods are only analysis or hardware; its text is a budget or board fact; it has no cycle-level wording;
    a port it needs has no numeric width (cannot be declared); or it names two clocks and the spec states no clock relation (simulation-only)."""
    cands, skipped = [], []
    clocks = clocks_of(spec)
    relation = has_clock_relation(spec)
    for r in spec.get("requirements") or []:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        rid, text = str(r["id"]), str(r.get("text", ""))
        if ids and rid not in ids:
            continue
        proof = [str(x) for x in r.get("proof") or []]
        if proof and not set(proof) & {"simulation", "formal"}:
            skipped.append({"id": rid, "reason": f"proof method is {', '.join(proof)} only: not a property of the ports"})
        elif NOT_A_PROPERTY.search(text) and not TEMPORAL.search(text):
            skipped.append({"id": rid, "reason": "a budget, board or document statement: no assertion states it"})
        elif not TEMPORAL.search(text) and not (r.get("l2") or {}):
            skipped.append({"id": rid, "reason": "no cycle-level condition or response in the wording (checked by simulation or analysis)"})
        elif len(clocks) > 1 and not relation and sum(1 for c in clocks if re.search(rf"\b{re.escape(str(c.get('name', c['port'])))}\b|\b{re.escape(str(c['port']))}\b", text)) > 1:
            skipped.append({"id": rid, "reason": "names two clocks and the spec states no clock relation: simulation-only"})
        else:
            cands.append(r)
    return cands, skipped


# ---- the generator and the back-translator ------------------------------------------------------------------------------------------------
GEN_SYSTEM = """You write one SystemVerilog assertion from one hardware requirement. You are shown the requirement and the ports of the module; you never see its RTL.
Answer with ONE JSON object and nothing else:
{"kind": "same" | "next" | "reset", "ante": "<boolean expression>", "cons": "<boolean expression>", "why": "<one line: how the property states the requirement>"}
Meaning (rst is the module's reset, active high; the clock is the module's single clock):
- "same": on every clock edge where `ante` is true, `cons` is true in the same cycle.
- "next": on every clock edge where `ante` was true on the previous edge, `cons` is true now (one cycle later).
- "reset": on every edge right after a cycle with rst high, `cons` is true (`ante` is ignored; give "1").
Rules: use only the listed port names, `rst`, constants and the operators of Verilog expressions. `$past(x)` and `$past(x, N)` (N from 1 to 16) read earlier values
and are the way to state a latency. `$rose(x)`, `$fell(x)` and `$stable(x)` are allowed. No `##`, no `|->`, no `always`, no `;`, no `assert`.
`ante` must be a condition that can really happen: it is also checked as reachable, and a property whose `ante` never happens is thrown away.
Say only what the requirement says: do not add a condition or a number it does not give. If the requirement cannot be stated on the ports, answer {"kind": "none", "why": "<reason>"}."""

BACK_SYSTEM = """You read one SystemVerilog property of a hardware module and say in one plain English sentence what it requires of the module.
Rules: describe exactly what the expressions say, with every number and every signal name, and nothing else. Do not guess a purpose.
Meaning of the kinds: "same": whenever `ante` is true, `cons` is true in that same clock cycle. "next": whenever `ante` was true in the previous clock cycle,
`cons` is true now. "reset": in the cycle right after reset was high, `cons` is true. `$past(x, N)` is the value of x N clock cycles earlier; `rst` is reset, high when asserted.
Answer with the sentence only."""


def port_table(spec: dict[str, Any]) -> str:
    rows = [f"- {p['name']} ({p['dir']}, {p['width']} bit{'s' if (p['width'] or 1) != 1 else ''})" for p in ports_of(spec)]
    clk = ", ".join(f"{c['port']} (clock)" for c in clocks_of(spec))
    rp, low = reset_of(spec)
    return "\n".join(rows) + (f"\nClock port: {clk}." if clk else "") + (f"\nReset port: {rp}, {'active low' if low else 'active high'}; inside the property `rst` is the active-high reset." if rp else "")


def generation_messages(req: dict[str, Any], spec: dict[str, Any]) -> tuple[str, str]:
    l2 = req.get("l2")
    user = (f"Requirement {req['id']}: {req.get('text', '')}\n"
            + (f"Structured fields (from the requirements stage):\n{yaml.safe_dump(l2, sort_keys=False)}\n" if l2 else "")
            + f"Module `{spec.get('top') or spec.get('name')}` ports:\n{port_table(spec)}\n")
    return GEN_SYSTEM, user


def back_messages(gen: dict[str, Any], spec: dict[str, Any]) -> tuple[str, str]:
    return BACK_SYSTEM, (f"Module ports:\n{port_table(spec)}\n\nProperty: kind `{gen['kind']}`; ante: `{gen['ante']}`; cons: `{gen['cons']}`\n")


_JSON = re.compile(r"\{.*\}", re.S)
_SIZED = re.compile(r"\d+\s*'\s*[sS]?[bBdDhHoO]\s*[0-9a-fA-F_xXzZ]+")
_SYSFN = re.compile(r"\$(past|rose|fell|stable)\b")
_IDENT = re.compile(r"[A-Za-z_]\w*")
_BAD = re.compile(r"##|\|->|\|=>|;|`|\balways\b|\bassert\b|\bassume\b|\bcover\b|@|\biff\b|\binitial\b|\bbegin\b|\bend\b|\$(?!past\b|rose\b|fell\b|stable\b)")


def expr_problems(expr: str, allowed: set[str]) -> list[str]:
    """Why ``expr`` is not usable (empty list: usable): a forbidden construct, unbalanced brackets, an unknown name, a ``$past`` too deep."""
    out = []
    if not expr.strip():
        return ["empty expression"]
    if _BAD.search(expr):
        out.append(f"forbidden construct in {expr!r}")
    if expr.count("(") != expr.count(")") or expr.count("[") != expr.count("]"):
        out.append(f"unbalanced brackets in {expr!r}")
    for m in re.finditer(r"\$past\s*\(\s*[^()]*?(?:\([^()]*\)[^()]*?)*,\s*(\d+)\s*\)", expr):
        if int(m.group(1)) > MAX_PAST or int(m.group(1)) < 1:
            out.append(f"$past depth {m.group(1)} outside 1 to {MAX_PAST}")
    bare = _SYSFN.sub(" ", _SIZED.sub(" 0 ", expr))
    unknown = sorted({i for i in _IDENT.findall(bare) if i not in allowed})
    if unknown:
        out.append("not a port of the module: " + ", ".join(unknown))
    return out


def past_depth(*exprs: str) -> int:
    d = 1
    for e in exprs:
        for m in re.finditer(r",\s*(\d+)\s*\)", e):
            if "$past" in e:
                d = max(d, int(m.group(1)))
    return d


def parse_generation(text: str, spec: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """``(property, "")`` or ``(None, reason)``. The reply must be one JSON object of the form the system message gives."""
    m = _JSON.search(text or "")
    if not m:
        return None, "the reply holds no JSON object"
    try:
        g = json.loads(m.group(0))
    except ValueError as e:
        return None, f"the reply is not valid JSON ({e})"
    if not isinstance(g, dict):
        return None, "the reply is not a JSON object"
    kind = str(g.get("kind", "")).strip()
    if kind == "none":
        return None, "the generator says it cannot be stated on the ports: " + str(g.get("why", ""))[:200]
    if kind not in KINDS:
        return None, f"kind {kind!r} is not one of {', '.join(KINDS)}"
    ante, cons = str(g.get("ante", "1")).strip() or "1", str(g.get("cons", "")).strip()
    if kind == "reset":
        ante = "1"
    allowed = {p["name"] for p in ports_of(spec)} | {"rst"}
    probs = expr_problems(ante, allowed) + expr_problems(cons, allowed)
    if probs:
        return None, "; ".join(dict.fromkeys(probs))
    sigs = sorted({i for e in (ante, cons) for i in _IDENT.findall(_SYSFN.sub(" ", _SIZED.sub(" 0 ", e))) if i in allowed})
    return {"kind": kind, "ante": ante, "cons": cons, "why": str(g.get("why", ""))[:300], "signals": sigs, "past": past_depth(ante, cons)}, ""


# ---- comparing the back-translation with the requirement (code) --------------------------------------------------------------------------
STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "is", "are", "be", "it", "its", "for", "with", "at", "by", "as", "that", "this", "must",
        "shall", "should", "one", "each", "every", "any", "then", "than", "from", "into", "over", "whenever", "true", "now", "cycle", "cycles", "clock",
        "edge", "value", "previous", "was", "has", "have", "happen", "same", "earlier", "ago"}
NEGATION = re.compile(r"\b(never|not|no|neither|nor|cannot|can't|without|isn't|doesn't|stays? low|remains? low)\b", re.I)
_CODE_SPAN = re.compile(r"`[^`]*`")
_TOK = re.compile(r"[a-z0-9]+")
_NUMLIT = re.compile(r"\b\d+\s*'\s*[sS]?([bBdDhHoO])\s*([0-9a-fA-F_xXzZ]+)|\b0[xX]([0-9a-fA-F_]+)\b|\b(\d+)\b")
_REQID = re.compile(r"\b[A-Z]{2,5}-\d+\b")
#: the short names hardware ports use, and the words a requirement uses for them (so `rst` in a property meets "reset" in the requirement)
SYNONYMS = {"rst": ("reset",), "rstn": ("reset",), "clk": ("clock",), "we": ("write",), "wr": ("write",), "re": ("read",), "rd": ("read",),
            "addr": ("address",), "wdata": ("write", "data"), "rdata": ("read", "data"), "en": ("enable",), "cnt": ("count",), "ctrl": ("control",),
            "reg": ("register",), "tx": ("transmit",), "rx": ("receive",), "irq": ("interrupt",)}


def _stem(t: str) -> str:
    if t.isdigit():
        return t
    if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
        t = t[:-1]
    return t[:5]


def _tokens(s: str) -> set[str]:
    """Content words (plural cut, then five letters, as the requirements report does), names split at underscores, short port names widened
    (``rst`` to reset), numbers read as numbers (``0x008``, ``12'h008`` and ``8`` are one token)."""
    s = _REQID.sub(" ", s)
    out: set[str] = set()
    for lit in _NUMLIT.finditer(s):
        v = _lit(lit)
        if v is not None:
            out.add(str(v))
    s = _NUMLIT.sub(" ", s).replace("_", " ")
    for t in _TOK.findall(s.lower()):
        for w in SYNONYMS.get(t, (t,)):
            if w not in STOP and (len(w) > 2 or w.isdigit()):
                out.add(_stem(w))
    return out


def _lit(m: re.Match) -> int | None:
    try:
        if m.group(2) is not None:
            base = {"b": 2, "d": 10, "h": 16, "o": 8}[m.group(1).lower()]
            return int(m.group(2).replace("_", ""), base)
        if m.group(3) is not None:
            return int(m.group(3).replace("_", ""), 16)
        return int(m.group(4))
    except (ValueError, TypeError):                       # x or z digits
        return None


def _numbers(s: str) -> set[int]:
    return {v for m in _NUMLIT.finditer(_REQID.sub(" ", s)) for v in [_lit(m)] if v is not None}


def _prop_numbers(gen: dict[str, Any]) -> set[int]:
    """The numbers the property itself chooses: $past depths and constants of two or more (0 and 1 are logic levels, not figures)."""
    n = {int(x) for x in re.findall(r",\s*(\d+)\s*\)", gen["ante"] + " " + gen["cons"]) if "$past" in gen["ante"] + gen["cons"]}
    n |= _numbers(gen["ante"] + " " + gen["cons"])
    return {x for x in n if x >= 2}


def _l2_text(l2: Any) -> str:
    if not l2:
        return ""
    return " ".join(str(v) for v in l2.values()) if isinstance(l2, dict) else str(l2)


def compare(req: dict[str, Any], gen: dict[str, Any], back: str, spec: dict[str, Any] | None = None, min_cover: float = 0.25) -> dict[str, Any]:
    """Does the back-translation say what the requirement says? Code only: no model produces the verdict.

    The checks, each with its reason when it fails:

    * **signals**: the property uses at least one signal the requirement (or its L2 fields) names, and every signal the L2 fields name
      (``trigger``, ``response``, ``signal``, ``signals``) is in the property;
    * **numbers**: every figure the property chooses (a ``$past`` depth, a constant of two or more) is in the requirement or its L2 fields,
      and every number the back-translation states is in the requirement, the L2 fields or the property: a changed latency is the
      commonest error, so it is the strictest check;
    * **negation**: the requirement and the back-translation agree on whether the sentence forbids something;
    * **words**: at least ``min_cover`` of the requirement's content words (cut to five letters, as the requirements report does) appear in the
      back-translation or the property's signal names, and the same share of the back-translation's content words appear in the requirement.
      A sentence about something else fails here."""
    req_text = str(req.get("text", ""))
    l2 = req.get("l2")
    full = req_text + " " + _l2_text(l2)
    reasons: list[str] = []
    notes = {p["name"]: p["note"] for p in ports_of(spec or {})}            # a port is also named by its description in the spec
    sig_tokens = {t for s in gen["signals"] for t in _tokens(s) | _tokens(notes.get(s, ""))}
    ports = set(notes)
    named = {s for s in gen["signals"] if re.search(rf"\b{re.escape(s)}\b", full)
             or (_tokens(s) and _tokens(s) <= _tokens(full)) or (_tokens(notes.get(s, "")) & _tokens(full))}
    want_words = _tokens(full)
    if gen["signals"] and not named and not (set(gen["signals"]) == {"rst"} and re.search(r"\breset\b", full, re.I)) \
            and len(want_words & (sig_tokens | _tokens(back))) / max(1, len(want_words)) < PARTIAL_BELOW:
        # a register requirement names a register, not the port that carries it, so the words must support the link too
        reasons.append("signals: the property uses " + ", ".join(gen["signals"]) + ", none of which the requirement names or describes")
    if isinstance(l2, dict):
        for k in ("condition", "trigger", "response", "component", "signal", "signals"):      # brief 227's L2: scope, condition, component, timing, response
            v = l2.get(k)
            for name in (v if isinstance(v, list) else ([v] if v else [])):
                for s in _IDENT.findall(str(name)):
                    if s in ports and s not in gen["signals"]:
                        reasons.append(f"signals: the L2 field {k} names {s}, which the property does not use")
    rq_nums, bk_nums, pr_nums = _numbers(full), _numbers(back), _prop_numbers(gen)
    rq_nums |= {int(w) for w in want_words if w.isdigit()}
    expr = gen["ante"] + " " + gen["cons"]
    for n in sorted(pr_nums - rq_nums):
        if (n - 1) in rq_nums and re.search(rf"(?:<|>=)\s*(?:\d+'[sS]?[hHdDbB])?{n}\b", expr):
            continue                                          # `x < 1024` states "0 to 1023": the same bound spelled one past the last value
        reasons.append(f"numbers: the property uses {n}, which the requirement does not give")
    for n in sorted(bk_nums - rq_nums - pr_nums - {0, 1}):
        reasons.append(f"numbers: the back-translation states {n}, which neither the requirement nor the property gives")
    neg_req, neg_back = bool(NEGATION.search(_CODE_SPAN.sub(" ", req_text))), bool(NEGATION.search(_CODE_SPAN.sub(" ", back)))   # words, not the `!x` of a quoted expression
    if neg_req != neg_back:
        reasons.append("negation: the requirement " + ("forbids something" if neg_req else "does not forbid anything") +
                       " and the back-translation " + ("does" if neg_back else "does not"))
    want, got = _tokens(full), _tokens(back) | sig_tokens
    fwd = len(want & got) / len(want) if want else 1.0
    rev = len(_tokens(back) & (want | sig_tokens)) / len(_tokens(back)) if _tokens(back) else 0.0
    if fwd < min_cover:
        reasons.append(f"words: only {fwd:.0%} of the requirement's content words are in the back-translation (need {min_cover:.0%})")
    if rev < min_cover:
        reasons.append(f"words: only {rev:.0%} of the back-translation's content words are in the requirement (need {min_cover:.0%})")
    return {"match": not reasons, "reasons": reasons, "requirement_covered": round(fwd, 2), "translation_covered": round(rev, 2),
            "partial": fwd < PARTIAL_BELOW, "property_numbers": sorted(pr_nums)}


# ---- the formal job -----------------------------------------------------------------------------------------------------------------------------
def slug(rid: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", rid).strip("_")


def _decl(p: dict[str, Any]) -> str:
    w = p["width"]
    return f"[{w - 1}:0] " if w and w > 1 else ""


def wrapper_sv(design: Path, spec: dict[str, Any], rid: str, gen: dict[str, Any]) -> str:
    """The formal wrapper: the design's top module with free inputs, reset asserted in the first cycle, and the property (the house form of
    ``flow/v_macros.svh``'s ``V_SAME`` / ``V_NEXT`` / ``V_RST``, each with the ``<name>__ante`` cover of ``v_macros_paired.svh``)."""
    top = str(spec.get("top") or spec.get("name"))
    clk_port = str(clocks_of(spec)[0]["port"]) if clocks_of(spec) else None
    rst_port, low = reset_of(spec)
    ports = ports_of(spec)
    name = f"A_SVA_{slug(rid)}"
    reset_kind = gen["kind"] == "reset"
    lines = [f"// Generated by flow/sva_req.py (brief 218) from {rid}. The property was stated from the requirement and the port list only;",
             f"// {gen['kind']}: ante `{gen['ante']}`, cons `{gen['cons']}`. Reset is " + ("free after the third cycle (a reset requirement)." if reset_kind
                                                                                          else "asserted in the first cycle only; a mid-run reset is not explored."),
             f"module sva_{slug(rid)} (input logic clk" + "".join(f", input logic {_decl(p)}{p['name']}" for p in ports
                                                                  if p["dir"] == "in" and p["name"] not in (clk_port, rst_port)) + (", input logic rst_free" if reset_kind else "") + ");"]
    for p in ports:
        if p["dir"] != "in":
            lines.append(f"    wire {_decl(p)}{p['name']};")
    lines += ["    logic rst_first = 1'b1;",
              "    always @(posedge clk) rst_first <= 1'b0;",
              "    logic [4:0] hist = 5'd0;",
              "    always @(posedge clk) if (hist != 5'd31) hist <= hist + 5'd1;",
              f"    wire rst = rst_first" + (" | (rst_free & (hist >= 5'd3))" if reset_kind else "") + ";",
              "    logic seen_rst = 1'b0;",
              "    always @(posedge clk) if (rst) seen_rst <= 1'b1;",
              f"    wire past_ok = (hist >= 5'd{min(gen['past'] + 1, 30)});"]
    conn = []
    for p in ports:
        n = p["name"]
        if n == clk_port:
            conn.append(f".{n}(clk)")
        elif n == rst_port:
            conn.append(f".{n}({'~rst' if low else 'rst'})")
        else:
            conn.append(f".{n}({n})")
    lines.append(f"    {top} dut ({', '.join(conn)});")
    guard = "past_ok && seen_rst && !rst && !$past(rst)"
    if gen["kind"] == "same":
        lines.append(f"    always @(posedge clk) if ({guard} && ({gen['ante']})) begin {name}: assert ({gen['cons']}); {name}__ante: cover (1'b1); end")
    elif gen["kind"] == "next":
        lines.append(f"    always @(posedge clk) if ({guard} && $past({gen['ante']})) begin {name}: assert ({gen['cons']}); {name}__ante: cover (1'b1); end")
    else:
        lines.append(f"    always @(posedge clk) if (past_ok && $past(rst)) begin {name}: assert ({gen['cons']}); {name}__ante: cover (1'b1); end")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def sources_of(design: Path) -> list[Path]:
    """The design's build sources (``build.yaml`` ``sources``, globs relative to the repository root), else its rtl/ files."""
    bj = Path(design) / "build.yaml"
    files: list[Path] = []
    if bj.is_file():
        try:
            for pat in (yaml.safe_load(bj.read_text()) or {}).get("sources") or []:
                files += sorted(ROOT.glob(str(pat)))
        except (OSError, yaml.YAMLError):
            pass
    if not files:
        files = sorted((Path(design) / "rtl").glob("*.sv")) + sorted((Path(design) / "rtl").glob("*.v"))
    try:
        from flow.sources import order_sv
        return [Path(p) for p in order_sv(files)]
    except Exception:
        return files


def data_files(design: Path) -> list[Path]:
    """The design's ``data/`` files that are not HDL (a memory image the RTL reads with ``$readmemh``), which the job needs at ``data/<name>``."""
    d = Path(design) / "data"
    return sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() not in (".sv", ".v", ".vhd", ".vhdl", ".svh")) if d.is_dir() else []


def sby_text(design: Path, spec: dict[str, Any], rid: str, gen: dict[str, Any], sby_dir: Path, srcs: list[Path],
             tasks: tuple[str, ...] = ("bmc", "prove", "cover"), front: str = "native") -> str:
    """The .sby job. Paths in ``[files]`` are relative to ``sby_dir`` (the folder the job runs from). ``tasks`` lists the tasks the job has:
    a property that was only bounded-checked is installed without ``prove``, so the traceability matrix (which needs every listed task to
    pass) reads it as the bounded evidence it is."""
    top = f"sva_{slug(rid)}"
    opts = {"bmc": ["bmc: mode bmc", f"bmc: depth {BMC_DEPTH}"], "prove": ["prove: mode prove", f"prove: depth {PROVE_DEPTH}"],
            "cover": ["cover: mode cover", f"cover: depth {COVER_DEPTH}"]}

    def rel(p: Path) -> str:
        return os.path.relpath(p, sby_dir)
    return "\n".join([
        f"# SymbiYosys: {rid} stated as a property (brief 218, flow/sva_req.py): bounded check, k-induction proof and the cover of its trigger.",
        f"# The property ({gen['kind']}): ante `{gen['ante']}`, cons `{gen['cons']}`. Generated from the requirement and the port list; see {top}.sv.",
        f"# req: {rid}",
        "# SYNTHESIS is left undefined, so a design's own simulation stubs of vendor primitives (`ifndef SYNTHESIS`) are the models the proof uses; a stub is a modelling choice, not the primitive.",
        *(["# Needs the OSS CAD Suite the repository pins (Yosys with the slang plugin): flow/formal.sh puts it first on PATH for a job that says `plugin -i slang`."]
          if front == "slang" else []),
        "[tasks]", *tasks, "", "[options]", *[o for t in tasks for o in opts[t]], "", "[engines]", "smtbmc yices" if front == "slang" else "smtbmc z3", "",
        "[script]", *(["plugin -i slang", f"read_slang --top {top} -U SYNTHESIS " + " ".join([p.name for p in srcs] + [f"{top}.sv"])] if front == "slang" else
                      [*[f"read_verilog -formal -nosynthesis -sv {p.name}" for p in srcs], f"read_verilog -formal -nosynthesis -sv {top}.sv"]), f"prep -top {top}", "",
        "[files]", *[rel(p) for p in srcs], f"{top}.sv",
        *[f"data/{p.name} {rel(p)}" for p in data_files(design)], ""])        # the design's data files (a ROM image read at elaboration) at the path its RTL names


# ---- running it ----------------------------------------------------------------------------------------------------------------------------------
def formal_env() -> dict[str, str] | None:
    """The environment with ``sby`` on PATH, in this order: the OSS CAD Suite the repository pins (``$FDA_OSS_CAD``, then ``~/.local/opt/oss-cad-suite``:
    a current Yosys with the slang front end, the one CI uses), the current PATH, the owner's user-local install (``~/.local/opt/formal-deb/env.sh``:
    Yosys 0.33, which reads less SystemVerilog)."""
    for c in (os.environ.get("FDA_OSS_CAD"), str(Path.home() / ".local" / "opt" / "oss-cad-suite")):
        if c and (Path(c) / "bin" / "sby").exists():
            return dict(os.environ, PATH=f"{Path(c) / 'bin'}:{os.environ.get('PATH', '')}")
    if shutil.which("sby"):
        return dict(os.environ)
    sh = Path.home() / ".local" / "opt" / "formal-deb" / "env.sh"
    if not sh.is_file():
        return None
    try:
        out = subprocess.run(["bash", "-c", f"source '{sh}' && env -0"], capture_output=True, timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    env = dict(kv.split("=", 1) for kv in out.decode(errors="replace").split("\0") if "=" in kv)
    return env if shutil.which("sby", path=env.get("PATH")) else None


_FRONT: dict[str, str] = {}


def frontend(env: dict[str, str]) -> str:
    """``slang`` when this Yosys loads the slang plugin (full SystemVerilog: parameters with types, packages, ``logic`` ports), else ``native``
    (Yosys's own reader). The job is written for the front end of the tool that will prove it."""
    key = env.get("PATH", "")
    if key not in _FRONT:
        try:
            r = subprocess.run(["yosys", "-q", "-p", "plugin -i slang"], env=env, capture_output=True, timeout=60)
            _FRONT[key] = "slang" if r.returncode == 0 else "native"
        except (OSError, subprocess.SubprocessError):
            _FRONT[key] = "native"
    return _FRONT[key]


def tool_version(env: dict[str, str]) -> str:
    try:
        return subprocess.run(["yosys", "-V"], env=env, capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def run_tasks(sby: Path, work: Path, env: dict[str, str], tasks: tuple[str, ...] = ("bmc", "prove", "cover"),
              timeout: int = TASK_TIMEOUT_S, prefix: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Run each task into ``work/<task>``; ``{task: {status, seconds}}``. ``prefix`` wraps the command (systemd-run, nice)."""
    out: dict[str, dict[str, Any]] = {}
    work.mkdir(parents=True, exist_ok=True)
    for t in tasks:
        d = work / t
        t0 = time.monotonic()
        try:
            subprocess.run([*(prefix or []), "sby", "-f", "-d", str(d), str(sby.name), t], cwd=sby.parent, env=env, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            out[t] = {"status": "TIMEOUT", "seconds": round(time.monotonic() - t0, 1)}
            continue
        st = d / "status"
        out[t] = {"status": (st.read_text().split() or ["ABSENT"])[0] if st.is_file() else "ABSENT", "seconds": round(time.monotonic() - t0, 1)}
        if out[t]["status"] in ("ERROR", "ABSENT"):             # say why: usually the open-source Yosys cannot read a source file
            lg = d / "logfile.txt"
            errs = [l.split("] ", 1)[-1] for l in lg.read_text(errors="replace").splitlines() if "ERROR" in l and "task failed" not in l and "DONE" not in l] if lg.is_file() else []
            out[t]["error"] = (errs[0] if errs else "no log")[:300]
    return out


def judge(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The evidence a job's results give, by the rule in the module doc.

    ``proved``: prove PASS and cover PASS. ``bounded``: bmc PASS, cover PASS, prove not PASS (the property holds to the depth, not for all time).
    ``vacuous``: the cover (the trigger) is not reached, so whatever bmc and prove say is empty. ``failed``: an assertion failed (bmc or prove).
    ``error``: a tool error, a timeout or an absent result. Only proved and bounded are evidence."""
    s = {t: (results.get(t) or {}).get("status", "ABSENT") for t in ("bmc", "prove", "cover")}
    if "FAIL" in (s["bmc"], s["prove"]):
        return {"status": "failed", "evidence": False, "tasks": s, "why": "an assertion fails: the property is wrong or the design is (counterexample in the work folder)"}
    if s["cover"] == "FAIL":
        return {"status": "vacuous", "evidence": False, "tasks": s, "why": f"the trigger is never reached within {COVER_DEPTH} cycles: the proof is empty"}
    if any(v in ("ERROR", "TIMEOUT", "ABSENT") for v in (s["bmc"], s["cover"])):
        err = next((r["error"] for r in results.values() if r.get("error")), "")
        return {"status": "error", "evidence": False, "tasks": s, "why": "a task did not finish: " + ", ".join(f"{k}={v}" for k, v in s.items())
                + (f" ({err})" if err else "")}
    if s["cover"] == "PASS" and s["prove"] == "PASS" and s["bmc"] == "PASS":
        return {"status": "proved", "evidence": True, "tasks": s, "why": f"proved by k-induction (depth {PROVE_DEPTH}); the trigger is reachable"}
    if s["cover"] == "PASS" and s["bmc"] == "PASS":
        return {"status": "bounded", "evidence": True, "tasks": s, "why": f"holds to depth {BMC_DEPTH} (k-induction did not close: {s['prove']}); the trigger is reachable"}
    return {"status": "error", "evidence": False, "tasks": s, "why": "unexpected task states: " + ", ".join(f"{k}={v}" for k, v in s.items())}


# ---- the cover trace as a timing diagram (for the show-back packet, brief 227) -------------------------------------------------------------
def parse_vcd(text: str) -> tuple[dict[str, str], list[tuple[int, dict[str, str]]]]:
    """``({id: name}, [(time, {id: value})])``. ``name`` is the last path component, a bus keeps its width. A name is taken from the shallowest
    scope that has it (the wrapper's own nets; a net the front end folded into the design instance, such as an output wire, from one level down)."""
    best: dict[str, tuple[int, str]] = {}                  # name -> (depth, id)
    scope: list[str] = []
    events: list[tuple[int, dict[str, str]]] = []
    cur: dict[str, str] | None = None
    in_defs = True
    for raw in text.splitlines():
        line = raw.strip()
        if in_defs:
            if line.startswith("$scope"):
                scope.append(line.split()[2])
            elif line.startswith("$upscope"):
                scope.pop()
            elif line.startswith("$var"):
                parts = line.split()
                if len(scope) <= 2 and (parts[4] not in best or len(scope) < best[parts[4]][0]):
                    best[parts[4]] = (len(scope), parts[3])
            elif line.startswith("$enddefinitions"):
                in_defs = False
            continue
        if line.startswith("#"):
            cur = {}
            events.append((int(line[1:]), cur))
        elif cur is not None and line and not line.startswith("$"):
            if line[0] in "bB":
                v, i = line[1:].split()
                cur[i] = v
            elif line[0] in "01xXzZ":
                cur[line[1:]] = line[0]
    return {i: n for n, (_, i) in best.items()}, events


def wavedrom(vcd_text: str, signals: list[str], title: str = "", mark_last: bool = True) -> dict[str, Any]:
    """A WaveDrom document (``{signal: [...], head, foot}``) of ``signals`` sampled once per clock cycle of ``clk`` from a cover trace.
    The last cycle is the one in which the trigger fires; the foot says so. Buses show their values as data."""
    names, events = parse_vcd(vcd_text)
    by_name = {n: i for i, n in names.items()}
    clk = by_name.get("clk")
    state: dict[str, str] = {}
    samples: list[dict[str, str]] = []
    prev_clk = "0"
    for _, ch in events:
        state.update(ch)
        c = state.get(clk, "0") if clk else "0"
        if clk and prev_clk == "0" and c == "1":
            samples.append(dict(state))
        prev_clk = c
    if not samples:                                     # no clock edge seen: one sample per time step
        for _, ch in events:
            state.update(ch)
            samples.append(dict(state))
    rows = []
    for s in signals:
        i = by_name.get(s)
        if i is None:
            continue
        vals = [smp.get(i, "x") for smp in samples]
        if all(len(v) == 1 for v in vals):
            wave, last = "", None
            for v in vals:
                wave += "." if v == last else {"0": "0", "1": "1"}.get(v, "x")
                last = v
            rows.append({"name": s, "wave": wave})
        else:
            wave, data, last = "", [], None
            for v in vals:
                if v == last:
                    wave += "."
                else:
                    wave += "="
                    data.append(hex(int(v, 2)) if set(v) <= {"0", "1"} else v)
                last = v
            rows.append({"name": s, "wave": wave, "data": data})
    n = len(samples)
    return {"signal": [{"name": "clk", "wave": "p" + "." * max(0, n - 1)}, *rows], "head": {"text": title},
            "foot": {"text": f"cover trace, {n} cycles" + ("; the trigger fires in the last cycle" if mark_last else "")}}


# ---- the pipeline on one design ------------------------------------------------------------------------------------------------------------
def _key(req: dict[str, Any], spec: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps([req.get("id"), req.get("text"), req.get("l2"), ports_of(spec), reset_of(spec), clocks_of(spec)], sort_keys=True, default=str).encode()).hexdigest()[:16]


def sva_dir(design: Path) -> Path:
    return Path(design).joinpath(*DIR_REL)


def read_evidence(design: Path) -> dict[str, Any]:
    try:
        return json.loads((sva_dir(design) / EVIDENCE).read_text())
    except (OSError, ValueError):
        return {}


def process(design: Path, gen_llm: Callable[[str, str], str], back_llm: Callable[[str, str], str], *, ids: list[str] | None = None, formal: bool = True,
            prefix: list[str] | None = None, install: bool = True) -> dict[str, Any]:
    """Run the whole pipeline for the design's candidate requirements and write ``build/verif/sva/evidence.json``.

    ``gen_llm`` and ``back_llm`` are ``(system, user) -> text``; the caller gives them different models (the back-translation is read by a
    reader that did not write the property). A requirement whose key (text, L2, ports) is unchanged and whose result is already recorded
    is not asked again. Returns the evidence record."""
    design = Path(design).resolve()
    ospec = spec_of(design)
    cands, skipped = select(ospec, ids)
    spec, module_note = effective_spec(design, ospec)       # the module the properties are about; ``ospec`` keeps the requirements
    base = sva_dir(design)
    base.mkdir(parents=True, exist_ok=True)
    old = read_evidence(design).get("requirements", {})
    env = formal_env() if formal else None
    front = frontend(env) if env else "native"
    rows: dict[str, Any] = {}
    srcs = sources_of(design)
    rtl_key = hashlib.sha256(b"".join(p.name.encode() + b"\0" + p.read_bytes() for p in srcs if p.is_file())).hexdigest()[:16]
    for r in cands:
        rid = str(r["id"])
        key = _key(r, spec)
        row: dict[str, Any] = {"id": rid, "text": r.get("text"), "key": key}
        prev = old.get(rid)
        row["rtl_key"] = rtl_key
        if prev and prev.get("key") == key and (prev.get("status") in ("unusable", "sim_only")
                                                or (prev.get("rtl_key") == rtl_key and prev.get("status") in ("proved", "bounded", "failed", "vacuous"))):
            rows[rid] = prev                                      # unchanged requirement (and RTL, for a proof): the earlier result stands
            continue
        _uninstall(design, rid)                                   # an earlier installed job is re-earned below, never kept on trust
        if prev and prev.get("key") == key and prev.get("status") == "mismatch" and prev.get("back_translation"):
            gtext, btext0 = prev.get("generator_reply", ""), prev["back_translation"]      # the replies are kept; the comparison is code, so it is re-judged
        else:
            gtext, btext0 = gen_llm(*generation_messages(r, spec)), None
        gen, why = parse_generation(gtext, spec)
        row["generator_reply"] = (gtext or "")[:1500]
        if gen is None:
            rows[rid] = {**row, "status": "unusable", "why": why}
            continue
        row["property"] = {k: gen[k] for k in ("kind", "ante", "cons", "why", "signals")}
        multi = len(clocks_of(spec)) > 1 and not has_clock_relation(spec) and len({_domain(spec, s) for s in gen["signals"] if s != "rst"}) > 1
        if multi:
            rows[rid] = {**row, "status": "sim_only", "why": "its signals are in more than one clock domain and the spec states no clock relation: simulation-only"}
            continue
        btext = btext0 if btext0 is not None else back_llm(*back_messages(gen, spec)).strip()
        cmp = compare(r, gen, btext, spec)
        row["back_translation"], row["comparison"] = btext, cmp
        if not cmp["match"]:
            rows[rid] = {**row, "status": "mismatch", "why": "back-translation disagrees with the requirement: " + "; ".join(cmp["reasons"])}
            continue
        if not formal:
            rows[rid] = {**row, "status": "not_run", "why": "formal run not requested"}
            continue
        if env is None:
            rows[rid] = {**row, "status": "not_run", "why": "sby is not installed here: no proof was attempted"}
            continue
        work = base / slug(rid)
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        (work / f"sva_{slug(rid)}.sv").write_text(wrapper_sv(design, spec, rid, gen))
        sby = work / f"sva_{slug(rid)}.sby"
        sby.write_text(sby_text(design, spec, rid, gen, work, srcs, front=front))
        res = run_tasks(sby, work, env, prefix=prefix)
        j = judge(res)
        row.update(j)
        row["seconds"] = round(sum(v["seconds"] for v in res.values()), 1)
        row["job"] = f"sva_{slug(rid)}"
        trace = _cover_trace(work / "cover", f"A_SVA_{slug(rid)}__ante")
        if trace is not None:
            wd = wavedrom(trace.read_text(), ["rst", *[s for s in gen["signals"] if s != "rst"]], f"{rid}: the trigger is reachable")
            (work / "cover_trace.wavedrom.json").write_text(json.dumps(wd, indent=1))
            row["cover_trace"] = str((work / "cover_trace.wavedrom.json").relative_to(design))
        if j["evidence"] and install:
            fdir = design / "verif" / "formal"
            fdir.mkdir(parents=True, exist_ok=True)
            (fdir / f"sva_{slug(rid)}.sv").write_text(wrapper_sv(design, spec, rid, gen))
            keep = ("bmc", "prove", "cover") if j["status"] == "proved" else ("bmc", "cover")
            (fdir / f"sva_{slug(rid)}.sby").write_text(sby_text(design, spec, rid, gen, fdir, srcs, keep, front))
            row["installed"] = f"verif/formal/sva_{slug(rid)}.sby"
            for t in keep:                    # the results the matrix reads (flow/formal.sh writes the same files when it runs the job)
                dst = design / "build" / "verif" / "formal" / f"sva_{slug(rid)}_{t}"
                dst.mkdir(parents=True, exist_ok=True)
                shutil.copy(work / t / "status", dst / "status")
        rows[rid] = {**row, "status": j["status"]}
    rec = {"schema": SCHEMA, "design": design.name, "module": spec.get("top"), "module_note": module_note, "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "requirements": rows,
           "skipped": skipped, "counts": counts(rows), "formal_tool": (tool_version(env) + f" ({front} front end)") if env else None, "caveats": ["a vendor primitive is the design's own simulation stub (SYNTHESIS undefined), not the primitive", "reset is asserted in the first cycle only (reset rows: free after the third)",
                                                                    "one clock domain per property", "the property was written without the RTL"]}
    (base / EVIDENCE).write_text(json.dumps(rec, indent=1) + "\n")
    return rec


def _uninstall(design: Path, rid: str) -> None:
    """Remove the files this tool installed for ``rid`` (recognised by the header it writes), and their recorded results; nothing else."""
    fdir = Path(design) / "verif" / "formal"
    for ext in (".sby", ".sv"):
        f = fdir / f"sva_{slug(rid)}{ext}"
        if f.is_file() and "flow/sva_req.py" in f.read_text(errors="replace")[:400]:
            f.unlink()
    for t in ("bmc", "prove", "cover"):
        d = Path(design) / "build" / "verif" / "formal" / f"sva_{slug(rid)}_{t}"
        if (d / "status").is_file():
            (d / "status").unlink()


def _domain(spec: dict[str, Any], sig: str) -> str:
    for p in ports_of(spec):
        if p["name"] == sig and p.get("clock"):
            return str(p["clock"])
    cs = clocks_of(spec)
    return str(cs[0].get("name", cs[0]["port"])) if cs else ""


def _cover_trace(cover_dir: Path, label: str) -> Path | None:
    """The cover task's VCD for the cover ``label`` when sby names it, else the first one it wrote."""
    vcds = sorted(cover_dir.glob("engine_*/trace*.vcd"))
    if not vcds:
        return None
    for v in vcds:
        yw = v.with_suffix(".yw")
        if yw.is_file() and label in yw.read_text(errors="replace"):
            return v
    return vcds[0]


def counts(rows: dict[str, Any]) -> dict[str, int]:
    c: dict[str, int] = {}
    for r in rows.values():
        c[r["status"]] = c.get(r["status"], 0) + 1
    return c


def summary_line(rec: dict[str, Any]) -> str:
    c = rec.get("counts", {})
    n_ev = c.get("proved", 0) + c.get("bounded", 0)
    return (f"requirement-to-assertion: {n_ev} of {len(rec.get('requirements', {}))} tried carry evidence ({c.get('proved', 0)} proved, "
            f"{c.get('bounded', 0)} bounded); " + ", ".join(f"{k} {v}" for k, v in sorted(c.items()) if k not in ("proved", "bounded")) +
            f"; {len(rec.get('skipped', []))} skipped")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("design")
    ap.add_argument("--ids", help="comma list of requirement ids (default: every candidate)")
    ap.add_argument("--no-formal", action="store_true", help="generate, back-translate and compare; do not run sby")
    ap.add_argument("--gen-model", default="claude-sonnet-5-5")
    ap.add_argument("--back-model", default="claude-haiku-5-5", help="a different model from the generator")
    ap.add_argument("--from-file", help="JSON {id: {generator: text, back: text}}: use these replies, call no model")
    a = ap.parse_args(argv)
    if a.from_file:
        rp = json.loads(Path(a.from_file).read_text())
        cur: dict[str, str] = {}

        def gen_llm(system: str, user: str) -> str:
            rid = re.match(r"Requirement (\S+):", user).group(1)         # type: ignore[union-attr]
            cur["id"] = rid
            return rp[rid]["generator"]

        def back_llm(system: str, user: str) -> str:
            return rp[cur["id"]]["back"]
    else:
        from agent.models import claude_cli

        def _call(model: str) -> Callable[[str, str], str]:
            def f(system: str, user: str) -> str:
                return str(claude_cli.text_call(system, user, model=model, effort="low", timeout_s=300).get("result", ""))
            return f
        gen_llm, back_llm = _call(a.gen_model), _call(a.back_model)
    rec = process(Path(a.design), gen_llm, back_llm, ids=a.ids.split(",") if a.ids else None, formal=not a.no_formal)
    print(summary_line(rec))
    for rid, r in rec["requirements"].items():
        print(f"  {rid:8} {r['status']:9} {r.get('why', '')[:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
