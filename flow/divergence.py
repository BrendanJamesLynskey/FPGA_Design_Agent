"""Brief 213: where a failing simulation first goes wrong, as a digest for a repair visit; and the fresh-stimulus lock-step runs behind the regrade.

Four parts:

* **First failing check** (:func:`diagnose`, :func:`snapshot_digest`). A failed simulate is re-run once with ``$FDA_DIAG_SNAPSHOT`` set
  (``flow/model_record.py``): at the first failing cocotb test the hook stops the simulation and writes the last cycles of the RTL's top-level signals,
  the model's last calls (``step``, ``read_reg``, ``write_reg``), the failing assertion and the bench source line. The digest is built from that: the
  check, the signals it names with the RTL's values over the last cycles and the model's value for the same name, the transaction in flight, and the
  driver cone of the first wrong signal from an RTL dataflow walk (:func:`driver_cone`, textual: it reads the RTL sources, not a netlist, and says so).
* **Capture** (:func:`record_env`). With ``$FDA_MODEL_RECORD`` set the simulate tool records every call the bench makes to ``model.Model``, so the
  regrade can reuse the stimulus the bench applied.
* **Lock step** (:func:`lockstep`, :func:`lockstep_digest`). ``flow/lockstep.py`` drives the RTL and ``Model.step`` with the same inputs cycle by
  cycle, in ``replay`` mode (the recorded stimulus: a calibration) or ``fresh`` mode (new seeded sequences: the regrade; ``flow/regrade.py``).
* The digest never decides which side is wrong: it states the divergence between two artefacts, and that the model is as unconfirmed as the RTL unless
  a requirement says otherwise. Pure functions over files; the only process started is the simulator, through the caller's ``run``.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DIGEST_LIMIT = 2200          # characters of one first-divergence digest
CONE_LIMIT = 10              # drivers listed

Run = Callable[[list[str], dict[str, str], int], tuple[int, str]]


def record_env(design: Path) -> dict[str, str]:
    """Environment for the simulate tool: record the bench's model calls under ``<design>/build/verif/model_record.jsonl`` (rewritten per run)."""
    path = Path(design) / "build" / "verif" / "model_record.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    return {"FDA_MODEL_RECORD": str(path)}


def record_path(design: Path) -> Path:
    return Path(design) / "build" / "verif" / "model_record.jsonl"


_ENTRY = r'''
import importlib.util, sys
from pathlib import Path
sys.path.insert(0, sys.argv[3])
from flow.cocotb_run import LockstepDone
design, entry, root = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sys.path[:0] = [root, str(design), str(design / "tests")]      # the simulator's own PYTHONPATH is this process's sys.path
spec = importlib.util.spec_from_file_location("fda_lockstep_entry", entry)
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
    for n in sorted(dir(mod)):
        fn = getattr(mod, n)
        if n.startswith("test_") and callable(fn) and not getattr(fn, "__code__", None).co_argcount:
            try:
                fn()
            except LockstepDone:
                sys.exit(0)
            except BaseException as e:
                print("entry", n, "raised", repr(e)[:300])
except LockstepDone:
    sys.exit(0)
print("no cocotb build was reached by the design's test entry points")
sys.exit(3)
'''


def diagnose(design: Path, run: Run, *, sim: str = "icarus", timeout: int = 900, py: str | None = None) -> dict[str, Any] | None:
    """The diagnostic re-run: the design's own test entry, with the failure snapshot hook on. Returns the snapshot, or None (the failure did not
    reproduce, or nothing could be captured)."""
    design = Path(design)
    snap = design / "build" / "verif" / "failure_snapshot.json"
    snap.parent.mkdir(parents=True, exist_ok=True)
    try:
        snap.unlink()
    except FileNotFoundError:
        pass
    tests = sorted((design / "tests").glob("test_*_rtl.py"))
    if not tests:
        return None
    env = {"FDA_DIAG_SNAPSHOT": str(snap), "SIM": sim, "FDA_SIM_RESULTS_DIR": "", "FDA_COVERAGE": "0", "FDA_DIAG_ENTRY": "1"}
    run([py or sys.executable, "-c", _ENTRY, str(design), str(tests[0]), str(ROOT)], env, timeout)
    try:
        return json.loads(snap.read_text())
    except (OSError, ValueError):
        return None


def lockstep(design: Path, run: Run, *, mode: str = "replay", seed: int = 1, cycles: int = 20000, fresh_cycles: int = 4000,
             sim: str = "icarus", timeout: int = 900, out: Path | None = None, py: str | None = None) -> dict[str, Any]:
    """Run the lock-step bench against the design as it stands. ``run(argv, env, timeout)`` -> (returncode, text) runs a process in the repo root (the
    agent passes its runner). Returns the bench's JSON, or ``{"ok": None, "error": ...}`` when no comparison could be made."""
    design = Path(design)
    out = out or design / "build" / "verif" / f"lockstep_{mode}{'' if mode == 'replay' else f'_seed{seed}'}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        out.unlink()
    except FileNotFoundError:
        pass
    tests = sorted((design / "tests").glob("test_*_rtl.py"))
    if not tests:
        return {"ok": None, "error": "the design has no tests/test_*_rtl.py to take the build from"}
    rec = record_path(design)
    env = {"FDA_LOCKSTEP": "1", "FDA_LOCKSTEP_OUT": str(out), "FDA_LOCKSTEP_MODE": mode, "FDA_LOCKSTEP_SEED": str(seed),
           "FDA_LOCKSTEP_CYCLES": str(cycles), "FDA_LOCKSTEP_FRESH_CYCLES": str(fresh_cycles), "SIM": sim, "FDA_SIM_RESULTS_DIR": "",
           "FDA_COVERAGE": "0"}
    if rec.is_file():
        env["FDA_MODEL_RECORD_IN"] = str(rec)
    elif mode == "replay":
        return {"ok": None, "error": "no recording of the bench's model calls (simulate has not run since recording was added)"}
    rc, text = run([py or sys.executable, "-c", _ENTRY, str(design), str(tests[0]), str(ROOT)], env, timeout)
    if out.is_file():
        try:
            return json.loads(out.read_text())
        except ValueError as e:
            return {"ok": None, "error": f"unreadable lock-step result: {e}"}
    return {"ok": None, "error": f"the lock-step bench did not run (exit {rc}): " + text.strip()[-400:]}


# --- the driver cone ----------------------------------------------------------------------------------------------------------------------------

_ID = re.compile(r"[A-Za-z_]\w*")
_KEYWORDS = frozenset("""begin end if else case casez casex endcase default for while posedge negedge or and not assign always always_ff always_comb
always_latch logic reg wire input output inout parameter localparam integer signed unsigned genvar generate endgenerate function endfunction task
endtask module endmodule int bit byte void return unique priority inside new""".split())
_NUM = re.compile(r"\b\d+'[sS]?[bBdDhHoO][0-9a-fA-FxXzZ_]+|\b\d+\b")


def _strip(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def _idents(expr: str) -> list[str]:
    expr = _NUM.sub(" ", expr)
    out: list[str] = []
    for m in _ID.finditer(expr):
        t = m.group(0)
        if t not in _KEYWORDS and t not in out and not expr[max(0, m.start() - 1):m.start()] == "$":
            out.append(t)
    return out


def _stmts(path: Path) -> list[dict[str, Any]]:
    """Assignments in one file: ``{lhs, rhs, line, text, guards}`` (guards: the identifiers of the enclosing if/case conditions, found by indentation)."""
    try:
        lines = _strip(path.read_text(errors="replace")).splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    assign = re.compile(r"^\s*(?:(?P<label>[\w']+(?:\s*,\s*[\w']+)*|default)\s*:\s*)?(?:assign\s+)?(?P<lhs>[A-Za-z_]\w*)\s*(?:\[[^\]]*\])*\s*(<=|=)\s*(?P<rhs>[^;]*);")
    for i, ln in enumerate(lines):
        inline: list[str] = []
        body = ln
        while True:                                           # `if (cond) x <= y;` and `else if (cond) x <= y;` on one line: cond is a guard
            mm = re.match(r"^(\s*)(?:else\s+)?if\s*\(", body)
            if not mm:
                break
            depth, j = 1, mm.end()
            while j < len(body) and depth:
                depth += (body[j] == "(") - (body[j] == ")")
                j += 1
            if depth:
                break
            inline += [g for g in _idents(body[mm.end():j - 1]) if g not in inline]
            body = mm.group(1) + body[j:].lstrip()
        if re.match(r"^\s*(for|while)\b", body):
            continue
        m = assign.match(body)
        if not m or m.group("lhs") in _KEYWORDS:
            continue
        indent = len(ln) - len(ln.lstrip())
        guards: list[str] = list(inline)
        for j in range(i - 1, max(-1, i - 60), -1):          # enclosing conditions: nearer-to-the-left lines above
            lj = lines[j]
            if not lj.strip():
                continue
            ij = len(lj) - len(lj.lstrip())
            if ij < indent:
                gm = re.match(r"^\s*(?:end\s+)?(?:else\s+)?(?:if|case[zx]?|unique case|priority case)\s*\((.*)\)", lj) or re.match(r"^\s*else\s+if\s*\((.*)\)", lj)
                if gm:
                    guards += [g for g in _idents(gm.group(1)) if g not in guards]
                indent = ij
                if re.match(r"^\s*always", lj):
                    break
        out.append({"lhs": m.group("lhs"), "rhs": m.group("rhs").strip(), "line": i + 1, "file": path.name, "text": ln.strip()[:120], "guards": guards,
                    "label": m.group("label")})
    return out


def _lit(tok: str) -> int | None:
    m = re.fullmatch(r"(?:\d+)?'[sS]?([bBdDhHoO])([0-9a-fA-F_]+)", tok.strip())
    if m:
        return int(m.group(2).replace("_", ""), {"b": 2, "d": 10, "h": 16, "o": 8}[m.group(1).lower()])
    return int(tok) if tok.strip().isdigit() else None


def driver_cone(rtl_files: list[Path], signal: str, depth: int = 2, limit: int = CONE_LIMIT, values: tuple[int, ...] = ()) -> list[dict[str, Any]]:
    """The statements that drive ``signal``, then those that drive what they read, ``depth`` levels deep: an RTL dataflow walk over the
    source text (assignments and the identifiers of their right-hand sides and enclosing conditions; instance port connections are not followed,
    so a signal driven by a sub-module is listed as an output of an instance). ``values`` (addresses and data of the transaction in flight) put the
    statements whose case label equals one of them first. Returns ``[{signal, file, line, text, reads, level}]``, bounded."""
    stmts = [s for f in rtl_files for s in _stmts(Path(f))]
    by_lhs: dict[str, list[dict[str, Any]]] = {}
    for s in stmts:
        by_lhs.setdefault(s["lhs"], []).append(s)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    frontier = [signal]
    for level in range(depth):
        nxt: list[str] = []
        for sig in frontier:
            if sig in seen:
                continue
            seen.add(sig)
            cands = by_lhs.get(sig, [])
            if values and level == 0:                         # the statement the in-flight transaction selects first
                hit = [c for c in cands if c.get("label") and any(_lit(x) in values for x in c["label"].split(","))]
                cands = hit + [c for c in cands if c not in hit]
            for s in cands[:4]:
                reads = [r for r in _idents(s["rhs"]) if r != sig] + [g for g in s["guards"] if g != sig and g not in _idents(s["rhs"])]
                out.append({"signal": sig, "file": s["file"], "line": s["line"], "text": s["text"], "reads": reads[:8], "level": level + 1,
                            **({"note": "selected by the in-flight transaction's address"} if values and s.get("label") and any(_lit(x) in values for x in s["label"].split(",")) else {})})
                nxt += [r for r in reads if r in by_lhs and r not in seen]
                if len(out) >= limit:
                    return out
        frontier = nxt
    if not out:
        inst = re.compile(r"\.\s*\w+\s*\(\s*" + re.escape(signal) + r"\b")
        for f in rtl_files:
            try:
                for i, ln in enumerate(_strip(Path(f).read_text(errors="replace")).splitlines()):
                    if inst.search(ln):
                        out.append({"signal": signal, "file": Path(f).name, "line": i + 1, "text": ln.strip()[:120],
                                    "reads": [], "level": 0, "note": "port connection of an instance (driven inside the sub-module)"})
                        break
            except OSError:
                pass
    return out


# --- the digest ---------------------------------------------------------------------------------------------------------------------------------

def _hexv(v: Any, w: int) -> str:
    if isinstance(v, int):
        return f"0x{v:0{max(1, (w + 3) // 4)}X}"
    return str(v)


def _inputs_line(vec: dict[str, Any], limit: int = 8) -> str:
    items = [f"{k}={v if not isinstance(v, int) or v < 10 else hex(v)}" for k, v in sorted(vec.items())]
    return ", ".join(items[:limit]) + (f", ... ({len(items)} inputs)" if len(items) > limit else "")


def lockstep_digest(res: dict[str, Any] | None, rtl_files: list[Path] | None = None, *, label: str = "first divergence") -> str:
    """The bounded repair-feedback text for a lock-step result; "" when there is nothing to say (no divergence, or no comparison could be made
    and nothing useful is known)."""
    if not res:
        return ""
    if res.get("ok") is None or res.get("error"):
        return f"[{label}] not available: {str(res.get('error') or 'no comparison made')[:240]}"
    d = res.get("divergence")
    if not d:
        return ""
    sigs = d["signals"]
    first = sigs[0]["signal"]
    mode = "the bench's recorded stimulus, replayed" if res.get("mode") == "replay" else f"fresh stimulus, seed {res.get('seed')}"
    t = [f"[{label}] RTL and model.py first differ at cycle {d['cycle']} of segment {d['segment']}"
         + (f" (test {d['test']})" if d.get("test") else "") + f" ({mode}; cycle 0 is the first clock after reset)."]
    for s in sigs[:6]:
        t.append(f"  {s['signal']}: model (expected) {_hexv(s['expected'], s['width'])}, RTL (actual) {_hexv(s['actual'], s['width'])}")
    if len(sigs) > 6:
        t.append(f"  ... {len(sigs) - 6} more signals differ at that cycle")
    ctx = d.get("context") or []
    t.append("  transaction in flight (inputs applied, last cycles up to the divergence):")
    for c in (ctx[-4:] + [d["at"]]):
        if c.get("event") == "reset":
            t.append(f"    cycle {c['cycle']}: reset")
        else:
            t.append(f"    cycle {c['cycle']}: {_inputs_line(c.get('in') or {})}")
    prev = [c for c in ctx if c.get("out") and first in c["out"]]
    if prev:
        w, a = prev[-1]["out"][first]
        t.append(f"  {first} one cycle earlier (cycle {prev[-1]['cycle']}): model {_hexv(w, sigs[0]['width'])}, RTL {_hexv(a, sigs[0]['width'])} (they agreed)" if w == a
                 else f"  {first} at cycle {prev[-1]['cycle']} already differed: model {w}, RTL {a}")
    if rtl_files:
        cone = driver_cone(list(rtl_files), first)
        if cone:
            t.append(f"  drivers of {first} (RTL dataflow walk over the source text, not a netlist; depth 2):")
            for c in cone:
                t.append(f"    {c['file']}:{c['line']}  {c['text']}" + (f"   [reads {', '.join(c['reads'])}]" if c["reads"] else "")
                         + (f"   [{c['note']}]" if c.get("note") else ""))
        else:
            t.append(f"  drivers of {first}: no assignment to it found in the RTL files (an instance output, or a name the walk does not resolve).")
    un = res.get("unmapped") or {}
    if un.get("inputs"):
        t.append(f"  note: model inputs not on the DUT top level, not driven: {', '.join(un['inputs'][:6])}")
    t.append("  The divergence is between the RTL and model.py. The model is a reading of the spec and is not confirmed: if the RTL matches the "
             "requirement text, the model is the artefact to change.")
    return "\n".join(t)[:DIGEST_LIMIT]


# --- the first failing check ---------------------------------------------------------------------------------------------------------------------

def _named_signals(snap: dict[str, Any]) -> list[str]:
    """Top-level signals the failing check names: ``dut.<name>`` first, then any sampled signal name or model output named in the message or the line."""
    text = (snap.get("message") or "") + "\n" + ((snap.get("site") or {}).get("source") or "")
    have = list(snap.get("signals") or [])
    out: list[str] = []
    for m in re.finditer(r"\bdut\.(\w+)", text):
        if m.group(1) not in out:
            out.append(m.group(1))
    for t in _idents(text):
        if t in have and t not in out:
            out.append(t)
    for r in reversed(snap.get("model_ring") or []):            # a model output the failing line reads: out["h_rdata"]
        for k in (r.get("out") or {}):
            if re.search(r"[\"']" + re.escape(k) + r"[\"']", text) and k not in out:
                out.append(k)
    return out


def _series(ring: list[dict[str, Any]], name: str, w: int = 8) -> str:
    vals = [r["sig"].get(name) for r in ring[-w:] if name in r["sig"]]
    return " ".join(f"{v:X}" if isinstance(v, int) else str(v) for v in vals)


def snapshot_digest(snap: dict[str, Any] | None, rtl_files: list[Path] | None = None, *, clock_ns: float | None = None) -> str:
    """The bounded repair-feedback text for a failure snapshot ("" when there is none)."""
    if not snap:
        return ""
    site = snap.get("site") or {}
    ring = snap.get("dut_ring") or []
    cyc = f", clock cycle {ring[-1]['cycle']} after the first sampled edge" if ring else ""
    t = [f"[first failing check] test {snap.get('test')} failed at {snap.get('sim_time_ns'):.0f} ns{cyc}: {snap.get('exception') or 'failure'}: "
         f"{str(snap.get('message') or '')[:300]}"]
    if site:
        t.append(f"  bench line {site.get('file')}:{site.get('line')} ({site.get('func')}): {site.get('source')}")
    named = _named_signals(snap)
    last_model = next((r for r in reversed(snap.get("model_ring") or []) if r.get("op") == "step" and r.get("out")), None)
    if named and ring:
        t.append("  signals the check names, RTL value after each of the last clock edges (oldest first; hex), and the model's value in its last step:")
        for n in named[:5]:
            mv = (last_model.get("out") or {}).get(n) if last_model else None
            t.append(f"    {n}: RTL {_series(ring, n) or '(not sampled)'}" + (f" | model {mv:X}" if isinstance(mv, int) else ""))
    changed = []
    if ring:
        for n in snap.get("signals") or []:
            vals = [r["sig"].get(n) for r in ring[-8:] if n in r["sig"]]
            if len(set(map(str, vals))) > 1 and n not in named:
                changed.append(n)
        if changed:
            t.append("  other top-level signals that changed in the last 8 cycles: " + "; ".join(f"{n} {_series(ring, n)}" for n in changed[:6]))
    mr = [r for r in (snap.get("model_ring") or []) if r.get("op") in ("wr", "rd", "reset", "new")
          or (r.get("op") == "step" and r.get("in"))][-6:]
    if mr:
        t.append("  the model's recent calls, newest last (the transaction in flight): " + "; ".join(
            f"{r['op']}" + (f" addr {r['addr']:#x} val {r['val']:#x}" if isinstance(r.get("addr"), int) and isinstance(r.get("val"), int)
                            else (f" in {_inputs_line(r['in'], 5)}" if r.get("in") else "")) + (f" @{r['t']:.0f}ns" if r.get("t") is not None else "")
            for r in mr))
    if last_model and last_model.get("out"):
        t.append("  the model's outputs in its last step: " + _inputs_line(last_model["out"], 6))
    if rtl_files and named:
        vals = tuple(r["addr"] for r in (snap.get("model_ring") or []) if r.get("op") in ("rd", "wr") and isinstance(r.get("addr"), int))[-1:]
        cone = driver_cone(list(rtl_files), named[0], values=vals)
        if cone:
            t.append(f"  drivers of {named[0]} (RTL dataflow walk over the source text, not a netlist; depth 2):")
            for c in cone:
                t.append(f"    {c['file']}:{c['line']}  {c['text']}" + (f"   [reads {', '.join(c['reads'])}]" if c["reads"] else "")
                         + (f"   [{c['note']}]" if c.get("note") else ""))
        else:
            t.append(f"  drivers of {named[0]}: no assignment to it in the RTL files (an instance output, or a name the walk does not resolve).")
    t.append("  This is the first failing check, as the bench states it; the RTL and the model are both unconfirmed readings of the requirement: if the "
             "RTL matches the requirement text, the model or the bench is the artefact to change.")
    return "\n".join(t)[:DIGEST_LIMIT + 800]
