#!/usr/bin/env python3
"""Human-owned records of the traceability matrix, the method-mix policy and who wrote each test (brief 143a, owner decision 25).

``flow/trace_v1.py`` computes every status from evidence. Four things it must not compute from the testplan, because the agent that implements the
design also writes the testplan, are kept in files the agent never writes:

* ``verif/agreements.yaml``   a requirement is **agreed** only by an entry here: ``agreed_kind: human`` (``agreed_by``, ``date``) or
  ``agreed_kind: agent_delegated`` (``accepted_by``, ``delegated_by``, ``date``; the planner on the owner's delegation, owner decision 25). The entry pins the
  hash of the requirement's text; a requirement whose text changes afterwards is a **draft** again. ``spec_status: agreed`` in the testplan is a gate failure.
* ``verif/reviews.yaml``      a ``review`` item passes only if a record here names it: who, when, what was read, the findings, and whether the reviewer
  is ``human`` or ``agent_delegated``. The reviewer fields of the testplan item are not read.
* ``verif/waivers.yaml``      a waiver lets a requirement stand as verified without one method group of its mix: reason, scope (the requirement and the
  groups waived), expiry, and approver kind. An expired waiver waives nothing. A safety requirement is never waived by anything but a human.
* ``flow/method_mix_policy.yaml``  the method mix each requirement kind needs before it is verified (see that file).

No code in this repository writes the three record files. ``python -m flow.trace_v1 agreement-hash DESIGN [REQ]`` prints the hash to copy; it writes nothing.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

HUMAN, DELEGATED = "human", "agent_delegated"
APPROVER_KINDS = (HUMAN, DELEGATED)
AGREEMENTS_SCHEMA = "fpga-design-agent/agreements/v1"
REVIEWS_SCHEMA = "fpga-design-agent/reviews/v1"
WAIVERS_SCHEMA = "fpga-design-agent/waivers/v1"
POLICY_SCHEMA = "fpga-design-agent/method-mix/v1"
DELEGATION = "owner decision 25"
AUTHORS = ("implementing_agent", "independent_bench", "human")
AUTHOR_TEXT = {"implementing_agent": "written by the implementing agent", "independent_bench": "independent bench", "human": "written by a human",
               None: "author not recorded (counted as the implementing agent's)"}
AUTHOR_SHORT = {"implementing_agent": "own test", "independent_bench": "independent bench", "human": "human-written", None: "author not recorded"}
# methods whose evidence is a test someone wrote; `written_by` is meaningful for these (a measurement or a proof is not "written")
AUTHORED = ("sim_test", "uvm_test", "assertion", "coverage_bin", "sim_measurement")
AGREEMENT_TEXT = {"draft": "draft", "agreed_human": "agreed (human)", "agreed_delegated": "agreed (delegated, not human)"}


# ---- small helpers ---------------------------------------------------------------------------------------
def today() -> dt.date:
    """Today, or the day in ``TRACE_TODAY`` (tests; an expired waiver depends on it)."""
    t = os.environ.get("TRACE_TODAY")
    return dt.date.fromisoformat(t) if t else dt.date.today()


def _load(path: Path, schema: str, key: str) -> tuple[list[dict], list[str]]:
    if not path.exists():
        return [], []
    try:
        raw = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as e:
        return [], [f"{path.name}: unreadable ({e})"]
    if raw is None:
        return [], []
    if not isinstance(raw, dict) or raw.get("schema") != schema:
        return [], [f"{path.name}: schema must be {schema}"]
    rows = raw.get(key) or []
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        return [], [f"{path.name}: `{key}` must be a list of entries"]
    return rows, []


def _date(v: Any) -> dt.date | None:
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v))
    except ValueError:
        return None


def _approver_problems(e: dict, what: str, kind_key: str, hum: str, dele: str) -> list[str]:
    k = e.get(kind_key)
    if k not in APPROVER_KINDS:
        return [f"{what}: {kind_key} must be {HUMAN} or {DELEGATED}, not {k!r}"]
    out = []
    if k == HUMAN:
        if not e.get(hum):
            out.append(f"{what}: a human entry needs {hum}")
        if e.get(dele) or e.get("accepted_by"):
            out.append(f"{what}: a human entry never uses delegated_by or accepted_by")
    else:
        if not e.get("accepted_by") or not e.get("delegated_by"):
            out.append(f"{what}: an agent_delegated entry needs accepted_by and delegated_by (for example {DELEGATION!r})")
        if e.get(hum):
            out.append(f"{what}: an agent_delegated entry never uses {hum}")
    if _date(e.get("date")) is None:
        out.append(f"{what}: needs a date (YYYY-MM-DD)")
    return out


# ---- requirement agreement -------------------------------------------------------------------------------
def req_text(q: dict) -> str:
    """What an agreement pins: the requirement's identity, kind, title, text, bound and external element, whitespace-normalised. The source anchor and
    the status fields are not part of it, so moving a document anchor does not drop an agreement and changing a bound does."""
    body = {"id": q.get("id"), "kind": q.get("kind"), "title": " ".join(str(q.get("title") or "").split()), "text": " ".join(str(q.get("text") or "").split()),
            "performance": q.get("performance"), "external": q.get("external")}
    return json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)


def req_hash(q: dict) -> str:
    return hashlib.sha256(req_text(q).encode()).hexdigest()


def load_agreements(design: Path) -> tuple[dict[str, dict], list[str]]:
    rows, bad = _load(design / "verif" / "agreements.yaml", AGREEMENTS_SCHEMA, "agreements")
    return {str(r.get("requirement")): r for r in rows}, bad


def agreement_problems(design: Path, reqs: list[dict]) -> list[str]:
    """Gate: the form of agreements.yaml and a testplan that claims agreement. A hash that no longer matches is not a failure: it is a draft again."""
    rows, bad = _load(design / "verif" / "agreements.yaml", AGREEMENTS_SCHEMA, "agreements")
    ids = {q["id"] for q in reqs}
    seen: set[str] = set()
    for e in rows:
        rid = str(e.get("requirement"))
        if rid not in ids:
            bad.append(f"agreements.yaml: {rid}: not a requirement of this testplan")
        if rid in seen:
            bad.append(f"agreements.yaml: {rid}: agreed twice")
        seen.add(rid)
        if not re.fullmatch(r"[0-9a-f]{64}", str(e.get("text_sha256") or "")):
            bad.append(f"agreements.yaml: {rid}: text_sha256 must be the 64-hex hash from `python -m flow.trace_v1 agreement-hash`")
        bad += _approver_problems(e, f"agreements.yaml: {rid}", "agreed_kind", "agreed_by", "delegated_by")
    for q in reqs:
        if q.get("spec_status") == "agreed":
            bad.append(f"{q['id']}: the testplan cannot claim agreement; a human (or the planner on delegation) records it in verif/agreements.yaml")
    return bad


def agreement_of(q: dict, agreements: dict[str, dict]) -> dict:
    """``{"state": draft | agreed_human | agreed_delegated, "note": ..., "by": ..., "date": ...}`` for one requirement."""
    e = agreements.get(q["id"])
    if not e or e.get("agreed_kind") not in APPROVER_KINDS:
        return {"state": "draft", "note": "", "by": None, "date": None}
    if e.get("text_sha256") != req_hash(q):
        return {"state": "draft", "note": "the requirement text changed since it was agreed", "by": None, "date": None, "dropped": True}
    if e["agreed_kind"] == HUMAN:
        return {"state": "agreed_human", "note": "", "by": e.get("agreed_by"), "date": str(e.get("date"))}
    return {"state": "agreed_delegated", "note": f"accepted by {e.get('accepted_by')} on {e.get('delegated_by')}", "by": e.get("accepted_by"), "date": str(e.get("date"))}


# ---- review records --------------------------------------------------------------------------------------
def _read_entries(e: dict) -> list[dict]:
    out = []
    for r in e.get("read") or []:
        out.append({"file": r} if isinstance(r, str) else dict(r))
    return out


def load_reviews(design: Path) -> tuple[dict[str, dict], list[str]]:
    rows, bad = _load(design / "verif" / "reviews.yaml", REVIEWS_SCHEMA, "reviews")
    return {str(r.get("item")): r for r in rows}, bad


def review_problems(design: Path, items: list[dict], root: Path) -> list[str]:
    rows, bad = _load(design / "verif" / "reviews.yaml", REVIEWS_SCHEMA, "reviews")
    by_id = {i["id"]: i for i in items}
    seen: set[str] = set()
    for e in rows:
        iid = str(e.get("item"))
        w = f"reviews.yaml: {iid}"
        if iid not in by_id or by_id[iid].get("method") != "review":
            bad.append(f"{w}: not a `review` item of this testplan")
        if iid in seen:
            bad.append(f"{w}: two records for one item")
        seen.add(iid)
        if not e.get("reviewer"):
            bad.append(f"{w}: needs reviewer (who)")
        if e.get("reviewer_kind") not in APPROVER_KINDS:
            bad.append(f"{w}: reviewer_kind must be {HUMAN} or {DELEGATED}, not {e.get('reviewer_kind')!r}")
        elif e["reviewer_kind"] == DELEGATED and not e.get("delegated_by"):
            bad.append(f"{w}: an agent_delegated review needs delegated_by (for example {DELEGATION!r})")
        elif e["reviewer_kind"] == HUMAN and e.get("delegated_by"):
            bad.append(f"{w}: a human review never uses delegated_by")
        if _date(e.get("date")) is None:
            bad.append(f"{w}: needs a date (YYYY-MM-DD)")
        reads = _read_entries(e)
        if not reads:
            bad.append(f"{w}: needs `read`, the files the reviewer read")
        for r in reads:
            if not r.get("file") or not (root / r["file"]).exists():
                bad.append(f"{w}: read file {r.get('file')!r} does not exist")
        if not str(e.get("findings") or "").strip():
            bad.append(f"{w}: needs findings (write `none` if there were none)")
    return bad


def review_status(rec: dict | None, root: Path) -> dict:
    """The judgement of one review item from its record: ``{"status": pass | not_run | stale, "detail": ..., ...}``."""
    if not rec:
        return {"status": "not_run", "detail": "no review record in verif/reviews.yaml (the reviewer named in the testplan is not a record)"}
    reads = _read_entries(rec)
    moved = []
    for r in reads:
        if r.get("sha256"):
            p = root / r["file"]
            if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != r["sha256"]:
                moved.append(r["file"])
    det = f"{rec.get('reviewer')} ({rec.get('reviewer_kind')}), {rec.get('date')}; read {len(reads)} file(s); findings: {' '.join(str(rec.get('findings') or '').split())[:140]}"
    out = {"status": "pass", "detail": det, "reviewer": rec.get("reviewer"), "reviewer_kind": rec.get("reviewer_kind"), "date": str(rec.get("date")),
           "review_read": [r["file"] for r in reads]}
    if moved:
        out.update(status="stale", stale_because="a file the reviewer read has changed since: " + ", ".join(moved[:4]))
    return out


# ---- waivers ---------------------------------------------------------------------------------------------
def load_waivers(design: Path) -> tuple[list[dict], list[str]]:
    return _load(design / "verif" / "waivers.yaml", WAIVERS_SCHEMA, "waivers")


def waiver_problems(design: Path, reqs: list[dict], groups: set[str]) -> list[str]:
    rows, bad = load_waivers(design)
    kind = {q["id"]: q.get("kind") for q in reqs}
    for e in rows:
        w = f"waivers.yaml: {e.get('id') or e.get('requirement')}"
        if not e.get("id"):
            bad.append(f"{w}: needs an id")
        rid = e.get("requirement")
        if rid not in kind:
            bad.append(f"{w}: requirement {rid!r} is not in this testplan")
        wv = e.get("waives")
        if not isinstance(wv, list) or not wv or (groups and not set(wv) <= groups):
            bad.append(f"{w}: `waives` (the scope) must list method groups from the policy: {', '.join(sorted(groups))}")
        if not str(e.get("reason") or "").strip():
            bad.append(f"{w}: needs a reason")
        if _date(e.get("expires")) is None:
            bad.append(f"{w}: needs an expiry date (expires: YYYY-MM-DD)")
        bad += _approver_problems(e, w, "approver_kind", "approved_by", "delegated_by")
        if kind.get(rid) == "safety" and e.get("approver_kind") != HUMAN:
            bad.append(f"{w}: a safety requirement can be waived only by a human")
    return bad


def active_waivers(design: Path, rid: str, kind: str | None) -> tuple[list[dict], list[dict]]:
    """(in effect today, expired) waivers of one requirement. A malformed or safety-without-human waiver is in neither (the gate reports it)."""
    rows, _ = load_waivers(design)
    now = today()
    live, dead = [], []
    for e in rows:
        if e.get("requirement") != rid or e.get("approver_kind") not in APPROVER_KINDS or not isinstance(e.get("waives"), list):
            continue
        if kind == "safety" and e["approver_kind"] != HUMAN:
            continue
        d = _date(e.get("expires"))
        if d is None:
            continue
        (live if d >= now else dead).append(e)
    return live, dead


# ---- the method-mix policy -------------------------------------------------------------------------------
def load_policy(path: Path) -> dict | None:
    """The policy, or ``None`` when there is no file (the earlier rule: one passing item verifies)."""
    if not path.exists():
        return None
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict) or raw.get("schema") != POLICY_SCHEMA:
        raise ValueError(f"{path}: schema must be {POLICY_SCHEMA}")
    for k, alts in (raw.get("kinds") or {}).items():
        for alt in alts:
            for g in alt:
                if g not in (raw.get("groups") or {}):
                    raise ValueError(f"{path}: kind {k} names unknown group {g}")
    return raw


def effective_author(item: dict) -> str | None:
    return item.get("written_by")


def in_group(item: dict, group: dict) -> bool:
    if item.get("status") != "pass" or item.get("method") not in group.get("methods", []):
        return False
    if group.get("judged_by_bound") and not item.get("judged_by_bound"):
        return False
    barred = group.get("not_written_by")
    if barred:
        a = effective_author(item)
        if (a if a in AUTHORS else "implementing_agent") in barred:
            return False
    return True


def mix(kind: str, items: list[dict], policy: dict | None) -> tuple[bool, list[str]]:
    """(satisfied, names of the groups the closest alternative still lacks). No policy, or no entry for the kind: satisfied."""
    alts = ((policy or {}).get("kinds") or {}).get(kind)
    if not alts:
        return True, []
    groups = policy["groups"]
    best: list[str] | None = None
    for alt in alts:
        lacking = [g for g in alt if not any(in_group(i, groups[g]) for i in items)]
        if not lacking:
            return True, []
        if best is None or len(lacking) < len(best):
            best = lacking
    return False, best or []


def own_tests_only(items: list[dict]) -> bool:
    """True when something passes and every passing item is a test the implementing agent wrote (or whose author is not recorded)."""
    ok = [i for i in items if i.get("status") == "pass"]
    return bool(ok) and all(i["method"] in AUTHORED and (i.get("written_by") not in ("independent_bench", "human")) for i in ok)


def author_problems(items: list[dict]) -> list[str]:
    out = []
    for i in items:
        w = i.get("written_by")
        if w is not None and w not in AUTHORS:
            out.append(f"{i.get('id')}: written_by must be one of {', '.join(AUTHORS)}, not {w!r}")
        elif w in ("independent_bench", "human") and i.get("method") not in AUTHORED:
            out.append(f"{i.get('id')}: written_by applies to tests ({', '.join(AUTHORED)}), not to a {i.get('method')} item")
    return out
