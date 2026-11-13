"""Brief 68 part D: pick up older work again (``python -m agent resume <design-dir> "<change request>"``).

1. Load: read ``AGENT.md`` (the compact handover; its size in tokens, characters / 4, is recorded beside the size of the
   design's own files) and ``flow.handover.freshness(ddir, deep=True)``. A handover with errors is not trusted: resume
   refuses and lists them.
2. Choose the entry stage with :func:`entry_stage`, the rule below. Every later stage runs again, so every gate whose
   inputs changed runs again before sign-off: stale evidence is re-run, never trusted.
3. Rebuild the graph state (:func:`prepare`): a new run whose design directory is a copy of the design (renderings and
   ``build/`` left out; the old directory path in ``build.yaml`` and the test plan rewritten to the run's), the
   architecture approval carried from the handover when the entry is after stage 1, and the change request given as the
   owner's note to the role that owns the entry stage (and as a repair reason to the stage-2 roles it touches).
4. Run the graph from the entry stage (the minimal stage-entry mechanism: the initial state's ``stage``). The document
   node writes the new handover at the end.

The stage-choice rule (:func:`entry_stage`): the entry stage is the earliest of

- the change request's stage (:func:`classify_change`: keyword classes matched as whole words, earliest match wins, so a
  request that names both a behaviour and a signal goes back to the spec (conservative); no match means stage 0, re-read
  the request; ``--kind`` overrides the classifier, ``--from-stage`` overrides the whole rule);
- each changed or deleted file's stage (:data:`FILE_STAGE`);
- each stale record's stage (the evidence activity or measurement category that cites it, :data:`ACTIVITY_STAGE`,
  :data:`CATEGORY_STAGE`);
- stage 3 (constraints, the first Vivado build) when the handover's builds used another Vivado release
  (``state.evidence_vivado: earlier`` or ``state.vivado`` differs from today's) or the build ID of today's sources
  differs from the handover's;
- the continuation stage: for an agent handover (gates named by stage) the first stage whose gate did not pass; for any
  other, from ``state.stage`` (:data:`STATE_NEXT`).

A changed knowledge-bank pin is reported, not re-run (it changes advice, not evidence). When nothing applies the entry
is :data:`DOC_ONLY`: nothing to re-run, and resume reports that the handover is current.

Notes for brief 62B (the joint closure loop re-enters at any stage): reuse :func:`prepare`'s state shape
(``stage``, ``owners``, ``note``/``note_role``, ``resumed_from``) and :data:`STAGE_OF_KIND`; the graph needs no other hook.
"""

from __future__ import annotations

import fnmatch
import json
import re
import shutil
from pathlib import Path
from typing import Any

from agent.graph.document import STAGE_NAMES
from flow import handover as H

DOC_ONLY = 10
#: change-request classes, their entry stage and the words that select them (checked on the lower-cased request)
CHANGE_RULES: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    ("spec", 0, ("requirement", "behaviour", "behavior", "register map", "new register", "add a register", "register offset",
                 "new port", "add a port", "feature", "spec", "parameter", "default value", "new mode", "protocol",
                 "interface")),
    ("arch", 1, ("architecture", "clock domain", "block diagram", "datapath", "resource budget", "add a block")),
    ("rtl", 2, ("rtl", "bug", "fix", "rename", "refactor", "lint", "comment", "signal", "testbench", "test bench",
                "coverage", "mutant", "assertion")),
    ("constraints", 3, ("pin", "xdc", "constraint", "iostandard", "i/o standard", "input delay", "output delay")),
    ("timing", 6, ("timing", "slack", "wns", "closure")),
    ("board", 9, ("bring-up", "bringup", "board test", "ila", "probe", "hardware test")),
    ("docs", DOC_ONLY, ("documentation", "readme", "docs", "handover", "typo")),
)
STAGE_OF_KIND = {k: s for k, s, _ in CHANGE_RULES}
#: words that make a request a change to what is built, so a late class (constraints, timing, board) still reopens the RTL
CHANGE_VERBS = re.compile(r"\b(add|adds|adding|change|changes|increase|decrease|remove|widen|narrow|replace|pipeline|"
                          r"insert|new|extend|reduce|retime|split|merge)\b")
#: files never treated as design inputs when looking for added files
NOT_INPUTS = ("handover.yaml", "README.md", "AGENT.md", "docs/*", "build/*", "__pycache__/*", "*.pyc", "BUILD_NOTE.md")
#: the role that owns each entry stage's work (gets the change request as the owner's note)
ROLE_OF_STAGE = {0: "clarify"}
#: stage-2 roles that a change of each kind reopens (repair visits with the request as the reason)
OWNERS_OF_KIND = {"spec": ("model", "tests", "rtl"), "arch": ("rtl",), "rtl": ("rtl",)}
FILE_STAGE: tuple[tuple[str, int], ...] = (
    ("spec.md", 0), ("spec.yaml", 0), ("architecture.yaml", 1), ("ARCHITECTURE.md", 1),
    ("rtl/*", 2), ("model.py", 2), ("tests/*", 2), ("verif/*", 2), ("lint/*", 2),
    ("*.xdc", 3), ("build.yaml", 3), ("probes.yaml", 9), ("hw_checks.py", 9), ("BRINGUP.md", 9))
ACTIVITY_STAGE = {"review": 0, "model": 2, "simulation": 2, "formal": 2, "faults": 2, "lint": 2, "cdc": 4,
                  "build": 3, "board": 9}
CATEGORY_STAGE = {"verification": 2, "latency": 2, "throughput": 2, "resources": 3, "timing": 3, "power": 3, "board": 9}
STATE_NEXT = {"spec": 0, "rtl": 2, "simulated": 3, "built": 9, "board-verified": DOC_ONLY, "signed-off": DOC_ONLY}
COPY_SKIP = ("handover.yaml", "README.md", "AGENT.md", "docs/handover/*", "build/*", "__pycache__/*", "*.pyc")


class PickupError(Exception):
    """The design cannot be resumed (a handover with errors, or not in the agent's file layout)."""


def classify_change(text: str | None) -> tuple[str | None, int | None, list[str]]:
    """(kind, stage, matched words): the earliest stage any class matches. No request: (None, None, []). A request that
    matches nothing is ``spec`` (stage 0): re-read the request rather than guess a later stage."""
    if not text or not text.strip():
        return None, None, []
    low = text.lower()
    hits = [(s, k, [w for w in words if re.search(r"\b" + re.escape(w) + r"(s|es)?\b", low)]) for k, s, words in CHANGE_RULES]
    hits = [h for h in hits if h[2] and h[1] != "docs"]      # docs-only is never guessed: it needs --kind docs
    if not hits:
        return "spec", 0, []
    s, k, words = min(hits, key=lambda h: h[0])
    if s > 2 and CHANGE_VERBS.search(low):                  # "add a pipeline stage" under a timing word changes the RTL
        return "rtl", 2, words + ["(a change verb: the RTL changes too)"]
    return k, s, words


def _stage_of_file(path: str, ddir_rel: str) -> int | None:
    sub = path[len(ddir_rel) + 1:] if path.startswith(ddir_rel + "/") else path
    for pat, s in FILE_STAGE:
        if fnmatch.fnmatch(sub, pat):
            return s
    if sub.endswith((".sdc", ".tcl")):
        return 3
    return 2 if sub.endswith((".sv", ".v", ".vhd", ".vhdl", ".svh", ".vh", ".hex", ".mem", ".xci", ".py")) else None


def entry_stage(h: dict, fresh: dict, change: str | None = None, kind: str | None = None,
                from_stage: int | None = None) -> dict[str, Any]:
    """The stage-choice rule (module docstring). Returns {stage, kind, reasons: [(stage, why)]}."""
    reasons: list[tuple[int, str]] = []
    if from_stage is not None:
        if not 0 <= from_stage <= 9:
            raise PickupError(f"--from-stage {from_stage}: a stage is 0 to 9")
        rule = entry_stage(h, fresh, change, kind)
        notes = [f"--from-stage {from_stage} is later than the rule's stage {rule['stage']}: skipped reasons: "
                 + "; ".join(w for s, w in rule["reasons"] if s < from_stage)] if rule["stage"] < from_stage else []
        return {"stage": from_stage, "kind": kind or rule["kind"], "reasons": [(from_stage, "--from-stage given by the owner")],
                "notes": notes}
    if kind:
        k, s, words = kind, STAGE_OF_KIND[kind], ["--kind"]
    else:
        k, s, words = classify_change(change)
    if s is not None:
        reasons.append((s, f"change request is a {k} change" + (f" (matched: {', '.join(words)})" if words else
                                                                  " (no class matched: re-read the request)")))
    drel = fresh.get("design") or H.rel(Path(fresh["ddir"]))
    for f in (fresh.get("changed_files") or []) + (fresh.get("added_files") or []):
        fs = _stage_of_file(f, drel)
        if fs is not None:
            reasons.append((fs, f"file changed since the handover: {f}"))
    byid = {x["id"]: x for x in (h.get("evidence") or []) + (h.get("measurements") or [])}
    recs = {x["record"]: x for x in (h.get("evidence") or [])}
    for line in fresh.get("stale") or []:
        cid = line.split(":", 1)[0]
        c = byid.get(cid)
        if c is None:
            continue
        st = (ACTIVITY_STAGE.get(c["activity"]) if "activity" in c else
              ACTIVITY_STAGE.get((recs.get(c["record"]) or {}).get("activity"), CATEGORY_STAGE.get(c["category"])))
        if st is not None:
            reasons.append((st, f"stale record: {line}"))
    state = h.get("state") or {}
    if state.get("evidence_vivado") == "earlier" or (fresh.get("vivado") or {}).get("handover") not in (None, H.VIVADO):
        reasons.append((3, f"the recorded builds used another Vivado release than {H.VIVADO}: rebuild from constraints"))
    bid = fresh.get("build_id") or {}
    if bid.get("handover") and bid.get("now") and bid["handover"] != bid["now"]:
        reasons.append((3, f"build ID of today's sources {bid['now']} differs from the handover's {bid['handover']}"))
    gates = state.get("gates") or {}
    if gates and set(gates) <= set(STAGE_NAMES):
        cont = next((i for i, n in enumerate(STAGE_NAMES) if gates.get(n) != "pass"), DOC_ONLY)
        if cont < DOC_ONLY:
            reasons.append((cont, f"continuation: stage {STAGE_NAMES[cont]} is {gates.get(STAGE_NAMES[cont])} in the handover"))
    elif state.get("stage") in STATE_NEXT and STATE_NEXT[state["stage"]] < DOC_ONLY:
        reasons.append((STATE_NEXT[state["stage"]], f"continuation: the handover's state is {state['stage']}"))
    kb = fresh.get("kb_pin") or {}
    notes = [f"knowledge-bank pin {kb.get('handover')} -> {kb.get('now')} (advice may differ; not re-run)"] \
        if kb.get("handover") and kb.get("now") and kb["handover"] != kb["now"] else []
    stage = min((r[0] for r in reasons), default=DOC_ONLY)
    return {"stage": stage, "kind": k, "reasons": reasons, "notes": notes}


def _files_tokens(ddir: Path, h: dict) -> int:
    """What an agent would otherwise read first: README.md and every file the handover lists (characters / 4)."""
    n = len((ddir / "README.md").read_text(errors="replace")) if (ddir / "README.md").is_file() else 0
    for f in h.get("files") or []:
        p = H.ROOT / f["path"]
        if p.is_file():
            n += len(p.read_text(errors="replace"))
    return n // 4


def load(ddir: Path, deep: bool = True) -> dict[str, Any]:
    """AGENT.md, its token size against the design's files, the handover and the freshness report."""
    ddir = ddir.resolve()
    if not (ddir / "handover.yaml").is_file() or not (ddir / "AGENT.md").is_file():
        raise PickupError(f"{ddir}: no handover.yaml and AGENT.md (write them first: python -m flow.handover write)")
    try:
        h = H.load(ddir)
        fresh = H.freshness(ddir, deep=deep)
    except (Exception, SystemExit) as ex:                    # noqa: BLE001 (a broken handover is refused, not trusted)
        raise PickupError(f"{H.rel(ddir)}: the handover cannot be read or checked: {type(ex).__name__}: {ex}"[:600])
    fresh["ddir"] = str(ddir)
    listed = {f.get("path") for f in h.get("files") or [] if isinstance(f, dict)}
    fresh["added_files"] = sorted(H.rel(p) for p in ddir.rglob("*") if p.is_file() and not p.is_symlink()
                                  and H.rel(p) not in listed
                                  and not any(fnmatch.fnmatch(str(p.relative_to(ddir)), x) for x in NOT_INPUTS))
    return {"agent_md": (ddir / "AGENT.md").read_text(), "agent_tokens": H.agent_tokens(ddir),
            "files_tokens": _files_tokens(ddir, h), "handover": h, "fresh": fresh}


def copy_design(src: Path, dst: Path) -> list[str]:
    """Copy the design into the run (renderings and build outputs left out); rewrite the old directory path."""
    src, dst = src.resolve(), dst.resolve()
    old, new = H.rel(src), H.rel(dst)
    out = []
    for p in sorted(src.rglob("*")):
        r = str(p.relative_to(src))
        if not p.is_file() or any(fnmatch.fnmatch(r, pat) for pat in COPY_SKIP) or p.is_symlink():
            continue
        q = dst / r
        q.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, q)
        if p.suffix in (".yaml", ".yml", ".py", ".tcl", ".sh", ".md") and old in (t := q.read_text(errors="replace")):
            q.write_text(re.sub(re.escape(old) + r"(?=[/\s'\",\]]|$)", new, t, flags=re.M))   # the whole path only
        out.append(r)
    return out


def prepare(ddir: Path, rt, entry: dict, change: str | None) -> dict[str, Any]:
    """Rebuild the graph state for ``rt`` (a new run named after the design): copy the design, carry the architecture
    approval when the entry is after stage 1, and build the initial graph state."""
    from flow import architecture as arch_mod
    ddir = ddir.resolve()
    missing = [f for f in ("spec.md", "spec.yaml") if not (ddir / f).is_file()]
    if missing:
        raise PickupError(f"{H.rel(ddir)} is not in the agent's file layout (no {', '.join(missing)}): the graph cannot "
                          "re-run its gates; re-check it with its own commands instead")
    copied = copy_design(ddir, rt.design)
    gates = (H.load(ddir).get("state") or {}).get("gates") or {}
    n = entry["stage"]
    if n >= 2 and (rt.design / "architecture.yaml").is_file() and (
            gates.get("board-and-device-planning") == "pass" or not set(gates) <= set(STAGE_NAMES) or not gates):
        arch_mod.write_approval(rt.design, "handover", "owner", f"carried from the handover of {H.rel(ddir)} (resume)")
    kind = entry.get("kind")
    state: dict[str, Any] = {"run_id": rt.run_id, "stage": n, "visits": {}, "history": [], "resumed_from": H.rel(ddir)}
    carried = [s for s in STAGE_NAMES[:n] if gates.get(s) == "pass"]     # passed in the handover; inputs unchanged (rule)
    if carried:
        state["carried"] = carried
    if change:
        state["note"] = change
        state["note_role"] = ROLE_OF_STAGE.get(n, "rtl")
        owners = {r: [f"CHANGE REQUEST (resume of {H.rel(ddir)}): {change}"] for r in OWNERS_OF_KIND.get(kind or "", ())}
        if owners:
            state["owners"] = owners
    (rt.run_dir / "resume_copied.json").write_text(json.dumps(copied, indent=1))
    return state
