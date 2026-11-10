#!/usr/bin/env python3
"""Synchroniser-delay injection for RTL simulation (brief 16, V-level CDC gate, part 2).

A clock-domain-crossing bug that depends on how many destination cycles a crossing takes (a pulse that is too short,
a multi-bit bus crossed bit by bit, a reconverging pair) is invisible in a zero-delay simulation, where every
synchroniser takes exactly its nominal number of cycles. This module makes the first stage of every synchroniser in a
design take 0 or 1 extra destination cycle, at random, so that a test of the design's own behaviour sees what hardware
metastability resolution can do. The model is cycle-level (flow/cdc_models/cdc_inj_pkg.sv): no time window, so it is not tied to one
simulator (written for Icarus and Verilator; only Icarus has been run).

What is injected
  * every register declared ``(* ASYNC_REG = "TRUE" *)`` in the design's RTL, at its first stage (the part of the
    register whose next value does not come from another ASYNC_REG register): ``r <= d;`` becomes a block that keeps
    the old value of those bits when cdc_inj_pkg::hold() says so. Supported shapes: a scalar ``s1 <= d; s2 <= s1;``, a
    shift vector ``s <= {s[N-2:0], d};`` or ``s <= {d, s[N-1:1]};``, a vector stage ``s1 <= bus;``, and a concatenated
    left side ``{s2, s1} <= {s1, d};``. A register with another shape is reported in ``unhandled`` and fails the gate.
  * every XPM CDC macro (xpm_cdc_single / array_single / pulse / gray / handshake / sync_rst, xpm_fifo_async): the
    design is built against flow/cdc_models/xpm_cdc_models.sv, whose first stage asks the same function.
A crossing that is not an ASYNC_REG register or an XPM macro has no injection point; the structural check
(flow/cdc_structure.py) is what catches it.

Use: ``prepare(sources, work_dir, seed)`` returns the source list to build and the plusargs to pass; flow/cocotb_run.py
calls it when ``$FDA_CDC_INJECT_SEED`` is set (injection) and, with no seed, only adds the XPM stand-ins that a build
needs (so that a design with XPM macros simulates at all). flow/cdc_inject_run.py runs a design's tests plain and with
N seeds and writes the evidence file the gate reads.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
MODELS = HERE / "cdc_models"
PKG = MODELS / "cdc_inj_pkg.sv"
XPM_MODELS = MODELS / "xpm_cdc_models.sv"

XPM_NAMES = ("xpm_cdc_single", "xpm_cdc_array_single", "xpm_cdc_sync_rst", "xpm_cdc_pulse", "xpm_cdc_gray",
             "xpm_cdc_handshake", "xpm_fifo_async")

_ATTR_DECL = re.compile(r"\(\*[^*]*?ASYNC_REG[^*]*?\*\)\s*(?:(?:logic|reg|bit)\b\s*)?(?P<rng>\[[^\]]*\]\s*)?(?P<names>[^;]+);")
_NAME = re.compile(r"\s*([A-Za-z_]\w*)")


def strip_comments(text: str) -> str:
    """Comments replaced by spaces (same length, so offsets and line numbers hold)."""
    return re.sub(r"//[^\n]*|/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)


def async_reg_decls(text: str) -> dict[str, str]:
    """name -> range text ('' for a scalar) of every ASYNC_REG-attributed register declared in ``text``."""
    out: dict[str, str] = {}
    for m in _ATTR_DECL.finditer(strip_comments(text)):
        rng = (m.group("rng") or "").strip()
        for part in re.split(r",(?![^\[]*\])", m.group("names")):
            nm = _NAME.match(part)
            if nm:
                out[nm.group(1)] = rng
    return out


def _split_top(s: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in s:
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    parts.append(cur.strip())
    return parts


def _refs(expr: str, names: set[str]) -> bool:
    return any(re.search(rf"\b{re.escape(n)}\b", expr) for n in names)


_CONST = re.compile(r"(?:\d*'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ]+|'[01xXzZ]|\d+)")
_NBA = re.compile(r"(?P<lhs>\{[^{};]*\}|[A-Za-z_]\w*\s*(?:\[[^\];]*\])?)\s*<=\s*(?P<rhs>[^;]+);")


def inject_text(text: str, key0: int = 0) -> tuple[str, dict[str, Any]]:
    """Rewrite the first-stage assignments of the ASYNC_REG registers declared in ``text``.
    Returns ``(new text, {"sites": n, "regs": [...], "unhandled": [...]})``; ``key0`` numbers the sites."""
    decls = async_reg_decls(text)
    info: dict[str, Any] = {"sites": 0, "regs": sorted(decls), "unhandled": []}
    if not decls:
        return text, info
    names = set(decls)
    clean = strip_comments(text)
    done: set[str] = set()
    out, last = [], 0
    key = key0

    def plan(lhs_name: str, lhs_idx: str, rhs: str) -> tuple[str, str, int | None] | None:
        """(kind, bit expr, ...) for a first-stage assignment; None when ``lhs_name`` is a later stage."""
        rng = decls[lhs_name]
        if lhs_idx:                                    # r[i] <= rhs
            return ("bit", lhs_idx, None) if not _refs(rhs, names) else None
        if not _refs(rhs, names):
            return None if _CONST.fullmatch(rhs.strip()) else ("all", "", None)       # a reset/constant is not a crossing
        left = re.sub(r"\b(?:%s)\b\s*(?:\[[^\]]*\])?" % "|".join(map(re.escape, names)), "", rhs)
        if not re.search(r"[A-Za-z_]", left):                # only ASYNC_REG registers on the right: a later stage
            return None
        r = rhs.strip()
        if r.startswith("{") and r.endswith("}") and rng:
            el = _split_top(r[1:-1])
            if len(el) >= 2 and _refs(el[0], {lhs_name}) and not _refs(el[-1], names):
                return ("bit", "[0]", None)
            if len(el) >= 2 and _refs(el[-1], {lhs_name}) and not _refs(el[0], names):
                return ("bit", f"[$bits({lhs_name})-1]", None)
        return ("?", "", None)

    def rng_of(name: str) -> str:
        return decls[name]

    def site(name: str, idx: str, rhs: str, k: int) -> str | None:
        p = plan(name, idx, rhs)
        if p is None:
            return ""                                   # a later stage: leave as it is (empty marks "no change")
        kind, bit, _ = p
        if kind == "?":
            return None
        blk = f"cdcinj_{k}"
        if kind == "all" and not rng_of(name):
            return (f"begin : {blk} logic __nv; __nv = {rhs.strip()}; "
                    f"if (cdc_inj_pkg::hold(32'({k} * 256), __nv !== {name})) __nv = {name}; {name} <= __nv; end")
        if kind == "all":
            return (f"begin : {blk} logic [$bits({name})-1:0] __nv; __nv = {rhs.strip()}; "
                    f"for (int __b = 0; __b < $bits({name}); __b++) "
                    f"if (cdc_inj_pkg::hold(32'({k} * 256 + __b), __nv[__b] !== {name}[__b])) __nv[__b] = {name}[__b]; "
                    f"{name} <= __nv; end")
        tgt = f"{name}{bit}"
        return (f"begin : {blk} logic __nv; __nv = (({rhs.strip()}) >> 0); "
                f"if (cdc_inj_pkg::hold(32'({k} * 256), __nv !== {tgt})) __nv = {tgt}; {tgt} <= __nv; end") \
            if idx else (f"begin : {blk} logic [$bits({name})-1:0] __nv; __nv = {rhs.strip()}; "
                         f"if (cdc_inj_pkg::hold(32'({k} * 256), __nv{bit} !== {name}{bit})) __nv{bit} = {name}{bit}; "
                         f"{name} <= __nv; end")

    for m in _NBA.finditer(clean):
        lhs, rhs = m.group("lhs").strip(), m.group("rhs")
        repl = None
        if lhs.startswith("{"):                          # {a, b} <= {x, y}
            ls, rs = _split_top(lhs[1:-1]), _split_top(rhs.strip()[1:-1]) if rhs.strip().startswith("{") else []
            if len(ls) == len(rs) and all(re.fullmatch(r"[A-Za-z_]\w*", x) for x in ls) and any(x in names for x in ls):
                parts, bad = [], False
                for a, b in zip(ls, rs):
                    if a in names:
                        s = site(a, "", b, key)
                        if s is None:
                            bad = True
                            info["unhandled"].append(f"{a} (concatenated assignment)")
                        elif s:
                            parts.append(s); key += 1; info["sites"] += 1; done.add(a)
                        else:
                            parts.append(f"{a} <= {b};")
                    else:
                        parts.append(f"{a} <= {b};")
                if not bad:
                    repl = " ".join(parts)
                else:
                    repl = ""
        else:
            lm = re.fullmatch(r"([A-Za-z_]\w*)\s*(\[[^\]]*\])?", lhs)
            if lm and lm.group(1) in names:
                nm, idx = lm.group(1), lm.group(2) or ""
                s = site(nm, idx, rhs, key)
                if s is None:
                    info["unhandled"].append(f"{nm} <= {rhs.strip()[:60]}")
                    repl = ""
                elif s:
                    repl = s; key += 1; info["sites"] += 1; done.add(nm)
        if repl:
            out.append(text[last:m.start()])
            out.append(repl)
            last = m.end()
    out.append(text[last:])
    for nm in sorted(names - done):
        if not any(nm in u for u in info["unhandled"]):
            if not re.search(rf"\b{re.escape(nm)}\b[^;]*<=", clean) and not re.search(rf"<=[^;]*\b{re.escape(nm)}\b", clean):
                info["unhandled"].append(f"{nm} (never assigned with <=)")
    # a first-stage register that no assignment of the supported shapes covers is reported only if it is the sole stage
    first_found = bool(done)
    info["first_stage_found"] = first_found
    return "".join(out), info


def xpm_instances(text: str) -> list[str]:
    clean = strip_comments(text)
    return [n for n in XPM_NAMES if re.search(rf"^\s*{n}\b", clean, re.M)]


def defines(text: str) -> set[str]:
    return set(re.findall(r"^\s*module\s+(\w+)", strip_comments(text), re.M))


def prepare(sources: list[Path], work_dir: Path, seed: int | None) -> tuple[list[Path], list[str], dict[str, Any]]:
    """Sources to build, plusargs, report. ``seed`` None: no injection, only the stand-ins an XPM-using build needs."""
    sources = [Path(s) for s in sources]
    info: dict[str, Any] = {"seed": seed, "sites": 0, "xpm": [], "regs": [], "unhandled": [], "files": []}
    texts = {s: s.read_text(errors="replace") for s in sources}
    have = set().union(*(defines(t) for t in texts.values())) if texts else set()
    used_xpm = sorted({n for t in texts.values() for n in xpm_instances(t)} - have)
    info["xpm"] = used_xpm
    if seed is None and not used_xpm:
        return sources, [], info
    work_dir.mkdir(parents=True, exist_ok=True)
    new: list[Path] = []
    key = 1000
    for s in sources:
        t = texts[s]
        if seed is not None and "ASYNC_REG" in t:
            t2, i = inject_text(t, key)
            key += i["sites"] + 1
            info["sites"] += i["sites"]
            info["regs"] += [f"{s.name}:{r}" for r in i["regs"]]
            info["unhandled"] += [f"{s.name}: {u}" for u in i["unhandled"]]
            if t2 != t:
                p = work_dir / s.name
                p.write_text(t2)
                new.append(p)
                info["files"].append(s.name)
                continue
        new.append(s)
    extra = [PKG] + ([XPM_MODELS] if used_xpm else [])
    return extra + new, ([f"+CDC_INJ_SEED={seed}"] if seed is not None else []), info


def design_crosses(design: Path) -> bool:
    """True when a design has a clock-domain crossing to check: an ASYNC_REG register or an XPM CDC macro in its RTL, or more
    than one clock domain declared in its architecture.yaml."""
    design = Path(design)
    for f in sorted((design / "rtl").glob("*.sv")) + sorted((design / "rtl").glob("*.v")):
        t = strip_comments(f.read_text(errors="replace"))
        if "ASYNC_REG" in t or re.search(r"^\s*(?:xpm_cdc_\w+|xpm_fifo_async)\b", t, re.M):
            return True
    try:
        import yaml
        a = yaml.safe_load((design / "architecture.yaml").read_text())
        return len([d for d in (a or {}).get("clock_domains") or [] if isinstance(d, dict)]) > 1
    except (OSError, ValueError, ImportError, AttributeError, TypeError):
        return False
