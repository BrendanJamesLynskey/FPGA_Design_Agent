"""Data for site/src/verified.html and the verification panels of site/src/traceability.html (brief 144).

    site/data/verified.json   what the 'Verified by construction' page reads (written by site/export.py)

Nothing is typed here. Every label, count and criterion result is read from the committed verification records (`<dir>/verified.json`,
written by `python -m flow.verified`), which are computed from the traceability collector. The page's own prose holds no number.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def slim(rec: dict) -> dict:
    """The part of a record a page needs (not the manifest or the per-item detail, which stay in VERIFIED.md)."""
    return {"path": rec["path"], "name": rec["name"], "kind": rec["kind"], "label": rec["label"], "label_kind": rec["label_kind"],
            "counts": rec.get("counts", {}),
            "criteria": [{"id": k["id"], "title": k["title"], "state": k["state"], "detail": k["detail"]} for k in rec["criteria"]],
            "git_commit": rec["git_commit"][:12], "manifest_files": len(rec["manifest"])}


def records() -> list[dict]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from flow import verified
    out = []
    for d in verified.entries():
        p = d / "verified.json"
        if p.exists():
            out.append(slim(json.loads(p.read_text())))
    return out


def build() -> dict:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from flow import verified
    recs = records()
    by_kind = {k: sum(1 for r in recs if r["label_kind"] == k) for k in ("verified", "verified_except", "not_verified", "not_assessed")}
    content = {"records": recs, "by_label": by_kind, "limits": verified.LIMITS, "criteria": [{"id": k, "title": t} for k, t in verified.CRITERIA],
               "by_name": {r["path"]: r for r in recs}}
    return {"content": content, "check": content}
