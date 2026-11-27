"""Brief 217: evidence-keyed repair memory (harness arm ``R4``; off by default).

A *repair record* is written when a repair visit turns a failing gate into a pass: the trigger (gate, finding id, signature class and the first
error line), the mechanism (what the evidence said was wrong), the local fix (a bounded diff of the files the repair changed), the gates that
passed afterwards, the design family and the run id. Records go to a staging folder in the run (``<run>/repair_memory/records``); a reviewed batch
goes to the knowledge bank by pull request, under ``repairs/``, with ``provenance: agent-repair`` (never ``produced_by: human``).

*Retrieval is by exact evidence, never by text similarity.* On a repair visit the harness computes the evidence keys of the failure it is about to
send back (:func:`evidence_keys`: ``(gate, finding_id, signature_class)``) and injects at most :data:`MAX_INJECT` records whose trigger has the same
three fields. The keys, the records offered and the records' content hash are written to the run (``repair_memory/retrievals.jsonl`` and a routing
event), also when nothing matched.

Pure functions over dicts and files; the one process the arm starts is none (the keys come from evidence the gates already produced).
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

SCHEMA = "fda/repair-record/v1"
PROVENANCE = "agent-repair"
MAX_INJECT = 3
DIFF_LINES = 30                 # lines of unified diff kept per record
DIFF_CHARS = 1800
SNAP_FILES = ("model.py", "build.yaml", "design.xdc", "architecture.yaml", "spec.yaml")
SNAP_DIRS = ("rtl", "tests", "verif", "lint")
TEXT_SUFFIX = (".sv", ".v", ".vh", ".svh", ".vhd", ".vhdl", ".py", ".yaml", ".yml", ".xdc", ".vlt", ".md", ".json", ".txt", "")
GATE_ROLE = {"lint": "rtl", "standards": "rtl", "constants": "rtl", "report_gates": "rtl", "simulate": "rtl", "contract": "model", "verif": "tests"}

_PATHNUM = re.compile(r"(?:[\w./-]+/)?[\w.-]+\.(?:sv|v|vh|svh|vhd|py|yaml|xdc|md|tcl|vlt)(?::\d+(?::\d+)?)?:?")
_HEXNUM = re.compile(r"\b0[xX][0-9a-fA-F_]+\b|\b\d+'[sS]?[bBdDhHoO][0-9a-fA-FxXzZ_]+|\b\d+\b")
_QUOTED = re.compile(r"'[^']{1,60}'|\"[^\"]{1,60}\"|`[^`]{1,60}`")
_VL = re.compile(r"%(?:Warning|Error)-([A-Z0-9_]+):\s*(\S+?):(\d+)(?::\d+)?:?\s*(.*)")
_CODE = re.compile(r"\b((?:FDA|HDL|STD|CONST|RPT|SIM|CDC)-[A-Z0-9]+(?:-\d+)?)\b")


def norm_line(s: str, limit: int = 140) -> str:
    """A first error line with what is specific to one design removed: file paths and line numbers, quoted names, numbers."""
    s = _PATHNUM.sub("<file>", str(s))
    s = _QUOTED.sub("'_'", s)
    s = _HEXNUM.sub("#", s)
    return re.sub(r"\s+", " ", s).strip()[:limit]


def _key(gate: str, fid: str, cls: str, line: str = "") -> dict[str, str]:
    return {"gate": gate, "finding_id": fid, "signature_class": cls, "line": str(line)[:200]}


def key_tuple(k: dict[str, Any]) -> tuple[str, str, str]:
    return (str(k["gate"]), str(k["finding_id"]), str(k["signature_class"]))


# --- evidence keys ------------------------------------------------------------------------------------------------------------------------------

def lint_keys(text: str) -> list[dict[str, str]]:
    """Keys of a failed lint: one per Verilator warning code (the class says whether the finding is in a source the design was handed, ``data/``,
    or in the design's own, and what the message states), one per rule id the harness adds (``FDA-CON-8``), one for an Icarus elaboration error."""
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(k: dict[str, str]) -> None:
        t = key_tuple(k)[1:]
        if t not in seen:
            seen.add(t)
            out.append(k)
    for ln in str(text).splitlines():
        m = _VL.match(ln.strip())
        if m:
            code, path, _l, msg = m.groups()
            where = "supplied" if re.search(r"(^|/)data/", path) else "own"
            msg = re.split(r":\s*['\"`]", msg)[0]                  # "Signal is not used: 'tdo'" -> the statement, not the name
            add(_key("lint", "VL-" + code, f"{where}: {norm_line(msg, 80)}", ln))
            continue
        m = _CODE.search(ln)
        if m and not ln.lstrip().startswith(("%", "[")):
            add(_key("lint", m.group(1), "default", ln))
    if "[icarus elaboration" in text:
        add(_key("lint", "ICARUS-ELAB", "default", text[text.index("[icarus elaboration"):][:200]))
    if not out and text.strip():
        add(_key("lint", "LINT-OTHER", norm_line(text.strip().splitlines()[-1], 80), text.strip().splitlines()[-1]))
    return out


def line_keys(gate: str, lines: list[str]) -> list[dict[str, str]]:
    """Keys of failure lines that open with a rule or finding id (``STD-CDC-01 ...``, ``constants CONST-ID-01 ...``, ``report gate RPT-LL-02 ...``)."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for ln in lines:
        m = _CODE.search(str(ln))
        fid = m.group(1) if m else "OTHER"
        if fid in seen:
            continue
        seen.add(fid)
        out.append(_key(gate, fid, "default" if m else norm_line(str(ln), 80), str(ln)))
    return out


def sim_keys(sim: dict[str, Any]) -> list[dict[str, str]]:
    """The key of a failed simulate: the exception class (or ``SIM-STOP`` for a simulator stop, with the clock fact as its class) and the kind
    (``mismatch`` with the first wrong signal when the first-failing-check digest named one, or ``code`` for an exception in a file)."""
    fc = sim.get("first_check") or {}
    ff = sim.get("first_failure") or {}
    if fc.get("kind") == "sim_stop":
        return [_key("simulate", "SIM-STOP", fc.get("class") or "stop", fc.get("message") or "")]
    from agent.graph.repair import classify_sim
    _role, kind = classify_sim(ff, str(sim.get("text") or "")) if (ff or sim.get("text")) else ("rtl", "mismatch")
    msgs = [*ff.get("cause", []), *ff.get("message", [])]
    exc = next((m.group(1) for x in msgs for m in [re.match(r"^(\w*(?:Error|Exception|Exit))\b", str(x))] if m), "AssertionError" if kind == "mismatch" else "SIM-FAIL")
    cls = kind
    if kind == "mismatch" and fc.get("signal"):
        cls = f"mismatch:{fc['signal']}"
    first = (msgs[0] if msgs else "") or str(sim.get("text") or "")[-200:]
    return [_key("simulate", exc, cls, first)]


def verif_keys(fails: list[str]) -> list[dict[str, str]]:
    """Keys of the first failed verification stage: the check's name, the stage as the class (lines look like ``V2 failing_tests: ...``)."""
    out = []
    for f in fails:
        m = re.match(r"^(V\d)\s+(\w+)\b", str(f))
        out.append(_key("verif", m.group(2) if m else "VERIF-OTHER", m.group(1) if m else "default", str(f)))
    return out


def evidence_keys(ev: dict[str, Any]) -> list[dict[str, str]]:
    """The evidence keys of one failed stage-2 gate evaluation, in the order ``repair.stage2_owners`` visits the gates. ``ev`` is the evidence dict the
    graph holds after the gates. Deterministic, from tool output only (never from a model)."""
    from agent.graph.repair import SIM_CONSEQUENCES, verif_failures
    from agent.graph.stages import constants_stage, report_gates_stage
    keys: list[dict[str, str]] = []
    lint = ev.get("lint") or {}
    if not lint.get("ok"):
        keys += lint_keys(str(lint.get("text") or ""))
    std = ev.get("standards_fails") or []
    if std:
        keys += line_keys("standards", list(std))
    k_ok, k_why = constants_stage(ev.get("constants"))
    if not k_ok:
        keys += line_keys("constants", k_why)
    g_ok, g_why = report_gates_stage(ev.get("report_gates"))
    if not g_ok:
        keys += line_keys("report_gates", g_why)
    c = ev.get("contract") or {}
    if not c.get("ok"):
        err = str(c.get("error") or "not checked")
        m = re.search(r"\b(\w*(?:Error|Exception))\b", err)
        keys.append(_key("contract", m.group(1) if m else "CONTRACT", "default", err))
    sim = ev.get("simulate") or {}
    if c.get("ok") and not sim.get("ok"):
        keys += sim_keys(sim)
    v = ev.get("verif") or {}
    need = ev.get("verif_level") or "V3"
    if not (v.get("reached") and v["reached"] >= need):
        fails = verif_failures(v, need)
        covered = sim.get("ok") is False
        keys += verif_keys([f for f in fails if not (covered and any(k in f for k in SIM_CONSEQUENCES))])
    seen: set[tuple[str, str, str]] = set()
    return [k for k in keys if not (key_tuple(k) in seen or seen.add(key_tuple(k)))]


# --- snapshots and diffs ----------------------------------------------------------------------------------------------------------------------

def snapshot(design: Path, dest: Path) -> int:
    """Copy the repair roles' text files (rtl, tests, verif, lint, model.py, the build and architecture files) to ``dest`` (replaced). Returns the count."""
    design, dest = Path(design), Path(dest)
    shutil.rmtree(dest, ignore_errors=True)
    n = 0
    files = [design / f for f in SNAP_FILES]
    for d in SNAP_DIRS:
        if (design / d).is_dir():
            files += sorted(p for p in (design / d).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    for p in files:
        if p.is_file() and p.suffix in TEXT_SUFFIX and p.stat().st_size <= 200_000:
            t = dest / p.relative_to(design)
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, t)
            n += 1
    return n


def diff_summary(old: Path, new_design: Path, limit_lines: int = DIFF_LINES, limit_chars: int = DIFF_CHARS) -> dict[str, Any]:
    """Files changed between a snapshot and the design as it stands, and a bounded unified diff (build outputs are never in a snapshot)."""
    old, new_design = Path(old), Path(new_design)
    cur = {}
    for f in SNAP_FILES:
        if (new_design / f).is_file():
            cur[f] = new_design / f
    for d in SNAP_DIRS:
        if (new_design / d).is_dir():
            for p in new_design.joinpath(d).rglob("*"):
                if p.is_file() and "__pycache__" not in p.parts and p.suffix in TEXT_SUFFIX and p.stat().st_size <= 200_000:
                    cur[str(p.relative_to(new_design))] = p
    prev = {}
    for p in (old.rglob("*") if old.is_dir() else []):                  # the same file set as a snapshot: a raw checkout of a run holds build outputs too
        rel = p.relative_to(old)
        if p.is_file() and "__pycache__" not in rel.parts and (str(rel) in SNAP_FILES or rel.parts[0] in SNAP_DIRS) and p.suffix in TEXT_SUFFIX:
            prev[str(rel)] = p
    changed, lines = [], []
    for name in sorted(set(cur) | set(prev)):
        a = prev[name].read_text(errors="replace").splitlines() if name in prev else []
        b = cur[name].read_text(errors="replace").splitlines() if name in cur else []
        if a == b:
            continue
        changed.append(name)
        d = [x for x in difflib.unified_diff(a, b, f"a/{name}", f"b/{name}", n=1, lineterm="")]
        lines += d[:limit_lines]
    text = "\n".join(lines[:limit_lines * 2])[:limit_chars]
    return {"files": changed, "diff": text, "truncated": len("\n".join(lines)) > len(text)}


# --- records --------------------------------------------------------------------------------------------------------------------------------

def record_id(trigger: dict[str, Any], fix: dict[str, Any], run_id: str) -> str:
    h = hashlib.sha256(json.dumps([trigger, fix.get("diff"), run_id], sort_keys=True).encode()).hexdigest()
    return h[:12]


def family_of(design: Path) -> str:
    """The design family for matching and for the reader: the top module's interface profile from spec.yaml (``jtag_bus`` register core, AXI-Lite,
    stream ...) and the part's family; free text, never used for matching."""
    try:
        import yaml
        spec = yaml.safe_load((Path(design) / "spec.yaml").read_text()) or {}
        ifs = sorted({str(p.get("interface") or p.get("kind") or p.get("type")) for p in (spec.get("ports") or []) if isinstance(p, dict)
                      and (p.get("interface") or p.get("kind") or p.get("type"))})
        return f"{spec.get('name', Path(design).name)} ({', '.join(ifs[:3]) or 'no interface listed'})"
    except Exception:
        return Path(design).name


def make_record(key: dict[str, str], fix: dict[str, Any], *, run_id: str, design: Path | str, gates_after: list[str], mechanism: str = "",
                repair_note: str = "", role: str | None = None, visit: int | None = None, ts: str | None = None) -> dict[str, Any]:
    trigger = {"gate": key["gate"], "finding_id": key["finding_id"], "signature_class": key["signature_class"], "first_line": norm_line(key.get("line", ""), 200)}
    return {"schema": SCHEMA, "id": record_id(trigger, fix, run_id), "provenance": PROVENANCE, "produced_by": "agent", "reviewed": False,
            "trigger": trigger, "role": role or GATE_ROLE.get(key["gate"], "rtl"),
            "mechanism": (mechanism or f"{key['gate']} {key['finding_id']}: {norm_line(key.get('line', ''), 200)}")[:400],
            "fix": {"files": fix.get("files", []), "diff": fix.get("diff", ""), "truncated": bool(fix.get("truncated"))},
            "agent_note": repair_note[:400],          # the repair role's own words about what it did: the agent's reading, not a measurement
            "constraints_preserved": gates_after, "design_family": family_of(Path(design)) if Path(str(design)).is_dir() else str(design),
            "run_id": run_id, "visit": visit, "stamp": ts or time.strftime("%Y-%m-%d %H:%M:%S %Z")}


def valid(rec: dict[str, Any]) -> bool:
    """A record the retrieval may use: right schema, agent provenance (a record marked human, or with no provenance, is refused), all three trigger fields."""
    t = rec.get("trigger") or {}
    return (rec.get("schema") == SCHEMA and rec.get("provenance") == PROVENANCE and rec.get("produced_by") != "human"
            and all(t.get(f) for f in ("gate", "finding_id", "signature_class")))


def load_records(*dirs: Path) -> list[dict[str, Any]]:
    out, seen = [], set()
    for d in dirs:
        d = Path(d) if d else None
        if not d or not d.is_dir():
            continue
        for p in sorted(d.rglob("*.json")):
            try:
                rec = json.loads(p.read_text())
            except (OSError, ValueError):
                continue
            if isinstance(rec, dict) and valid(rec) and rec["id"] not in seen:
                seen.add(rec["id"])
                out.append(rec)
    return out


# --- retrieval ------------------------------------------------------------------------------------------------------------------------------

def retrieve(records: list[dict[str, Any]], keys: list[dict[str, str]], *, family: str | None = None, exclude_runs: tuple[str, ...] = (),
             limit: int = MAX_INJECT) -> list[dict[str, Any]]:
    """Records whose trigger equals a current key on (gate, finding id, signature class): exact match on all three, nothing else (no text similarity,
    no partial match on the id alone). Order: records of the same design family first, then newest, then id; at most ``limit``; one record per
    distinct fix."""
    want = {key_tuple(k) for k in keys}
    hits = [r for r in records if (r["trigger"]["gate"], r["trigger"]["finding_id"], r["trigger"]["signature_class"]) in want
            and r.get("run_id") not in exclude_runs]
    hits.sort(key=lambda r: (str(r.get("stamp") or ""), r["id"]), reverse=True)            # newest first ...
    hits.sort(key=lambda r: 0 if family and r.get("design_family") == family else 1)       # ... the same family before the rest (stable)
    out, fixes = [], set()
    for r in hits:
        fx = hashlib.sha1(str(r["fix"].get("diff")).encode()).hexdigest()
        if fx in fixes:
            continue
        fixes.add(fx)
        out.append(r)
        if len(out) >= limit:
            break
    return out


def memory_text(recs: list[dict[str, Any]], role: str) -> str:
    """The text a repair visit is given: what the evidence was, what was changed, and what still held. A hint from a past design: the Designer checks it
    against this design."""
    mine = [r for r in recs if r.get("role", "rtl") == role]
    if not mine:
        return ""
    lines = ["[repair memory: earlier fixes of the SAME evidence (same gate, finding id and signature class). They come from other designs or earlier visits; "
             "check each against this design before using it, and do not copy a change that this design's requirement or standards contradict]"]
    for r in mine:
        t = r["trigger"]
        lines.append(f"- {t['gate']} {t['finding_id']} ({t['signature_class']}) in {r.get('design_family')}, run {r.get('run_id')}: {r['mechanism'][:240]}")
        if r["fix"].get("files"):
            lines.append("  changed: " + ", ".join(r["fix"]["files"][:5]))
        if r["fix"].get("diff"):
            lines.append("  " + r["fix"]["diff"][:700].replace("\n", "\n  "))
        if r.get("agent_note"):
            lines.append("  the repairing agent's own note (its reading): " + r["agent_note"][:200])
    return "\n".join(lines)


def with_memory(owners: dict[str, list[str]], recs: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Owners' failure texts with the memory text added to the role that owns each matched record (the Modeller never gets a record that holds RTL)."""
    out = {r: list(v) for r, v in owners.items()}
    for role in out:
        txt = memory_text(recs, role)
        if txt:
            out[role].append(txt)
    return out


# --- the run's staging folder and the per-gate step ---------------------------------------------------------------------------------------------

def staging(run_dir: Path) -> Path:
    return Path(run_dir) / "repair_memory"


def bank_records(bank_root: Path | None) -> list[dict[str, Any]]:
    return load_records(Path(bank_root) / "repairs") if bank_root else []


def step(run_dir: Path, design: Path, run_id: str, prior: dict[str, Any] | None, ev: dict[str, Any], ok: bool, visit: int,
         repair_note: str = "", bank_root: Path | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """One stage-2 gate evaluation. ``prior`` is the previous failing evaluation's ``{"keys": [...], "visit": n}`` (None before the first failure).
    Writes a staging record for each earlier key that no longer fails (the repair worked on it), snapshots the files for the next diff when this
    evaluation failed, and returns ``(new state, records written)``. The state never holds file contents."""
    st = staging(run_dir)
    keys = [] if ok else evidence_keys(ev)
    now = {key_tuple(k) for k in keys}
    written: list[dict[str, Any]] = []
    if prior and prior.get("keys"):
        fix = diff_summary(st / "snap", design)
        passed_gates = sorted({k["gate"] for k in prior["keys"]} - {k["gate"] for k in keys})
        for k in prior["keys"]:
            if key_tuple(k) in now or not fix["files"]:      # still failing, or no file changed: nothing was repaired by an edit
                continue
            rec = make_record(k, fix, run_id=run_id, design=design, gates_after=passed_gates + (["all stage-2 gates"] if ok else []),
                              repair_note=repair_note, visit=visit)
            (st / "records").mkdir(parents=True, exist_ok=True)
            (st / "records" / f"{rec['id']}.json").write_text(json.dumps(rec, indent=1) + "\n")
            written.append(rec)
    if ok:
        shutil.rmtree(st / "snap", ignore_errors=True)
        return {"keys": [], "visit": visit}, written
    snapshot(design, st / "snap")
    return {"keys": keys, "visit": visit}, written


def log_retrieval(run_dir: Path, visit: int, keys: list[dict[str, str]], offered: list[dict[str, Any]], pool: int) -> dict[str, Any]:
    ev = {"visit": visit, "keys": [key_tuple(k) for k in keys], "pool": pool, "offered": [r["id"] for r in offered],
          "offered_runs": [r.get("run_id") for r in offered], "stamp": time.strftime("%Y-%m-%d %H:%M:%S %Z")}
    st = staging(run_dir)
    st.mkdir(parents=True, exist_ok=True)
    with open(st / "retrievals.jsonl", "a") as f:
        f.write(json.dumps(ev) + "\n")
    return ev
