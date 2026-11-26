"""Data for site/src/changes.html (brief 237): what changed in the agent since 23 November 2026.

    site/changes/changes.yaml      the authored page: one entry per change, grouped; the figures are {name} placeholders
    site/changes/merged_prs.json   a dated snapshot of the merged pull requests of that period (number, date, title)
    site/data/changes.json         what the page reads (written by site/export.py)

Same rules as the story page: the prose holds no typed number (a figure is a {name} whose value one of site/expertise.py's
expressions reads from a committed file), every PR must be in the snapshot, every linked path must exist, and the page's number
check sees the resolved values, never the YAML's own text.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

import expertise
import story

HERE = Path(__file__).resolve().parent
DIR = HERE / "changes"
ROOT = HERE.parent

#: names that contain digits but are not measurements (added to story.PROSE_OK)
EXTRA_OK = re.compile(r"\bb\d+[a-z]?\b|\bK26\b|\bxc7a100t\b|\bb(?:58a|96|110|119|194|196)_\w+|\bUL3524\b|\bQuartus Prime Lite 25\.1std\b|\bSTEMlab 125-14\b|\bCyclone V\b|\bMAX 10\b|"
                      r"\b23 November 2026\b|\(2026\)|\bV[0-3]\b|\bt1\b|\bstage-2\b|\bnine\b|\bPS-AXI\b|\bFDA-HDL\b|\bGSR\b|\bXDC\b|\bVivado 2026\.1\b|\b224\b|\b55 K26\b", re.I)


class ContractError(story.ContractError):
    pass


def _fill(where, text, vals):
    t = str(text)
    bad = story.NUM.findall(EXTRA_OK.sub(" ", story.PROSE_OK.sub(" ", re.sub(r"\{[\w|]+\}", " ", t))))
    bad = [b for b in bad if any(c.isdigit() for c in b)]
    if bad:
        raise ContractError(f"{where}: typed number(s) {bad}; use a {{name}} placeholder with a value expression")
    return _sub(where, t, vals)


def _sub(where, t, vals):
    def one(m):
        k = m.group(1)
        if k not in vals:
            raise ContractError(f"{where}: no value named {k}")
        v = vals[k]
        return v if isinstance(v, str) else expertise.fmt(v)
    out = re.sub(r"\{(\w+)\}", one, t)
    if re.search(r"[{}]", out):
        raise ContractError(f"{where}: malformed placeholder in {t!r}")
    return out


def build() -> dict:
    y = yaml.safe_load((DIR / "changes.yaml").read_text())
    prs = json.loads((DIR / "merged_prs.json").read_text())
    known = {p["number"]: p for p in prs}
    vals = story._values({k: v for k, v in y["values"].items() if k != "sva_designs"})
    vals["sva_designs"] = "three pilot designs"       # a word, not a measured count: the README names them
    seen, groups, rows = set(), [], []

    def prl(ns, where):
        out = []
        for n in ns:
            if n not in known:
                raise ContractError(f"{where}: PR #{n} is not in changes/merged_prs.json")
            seen.add(n)
            out.append({"n": n, "title": known[n]["title"], "date": known[n]["date"]})
        return out

    for g in y["groups"]:
        items = []
        for it in g["items"]:
            w = f"{g['id']}/{it['id']}"
            item = {"id": it["id"], "title": it["title"], "prs": prl(it["prs"], w),
                    **{k: _fill(f"{w} {k}", it[k], vals) for k in ("changed", "result", "limits")},
                    "evidence": [expertise.link(p) for p in it["evidence"]],
                    "pages": [{"href": p["href"], "label": p["label"]} for p in it.get("pages", [])]}
            items.append(item)
            for p in item["prs"]:
                rows.append({"pr": p["n"], "title": it["title"], "group": g["id"], "item": it["id"], "pages": item["pages"]})
        groups.append({"id": g["id"], "title": g["title"], "intro": g["intro"], "items": items})
    smaller = []
    for it in y["smaller"]["items"]:
        w = "smaller " + ",".join(map(str, it["prs"]))
        smaller.append({"prs": prl(it["prs"], w), "text": _fill(w, it["text"], vals), "evidence": [expertise.link(p) for p in it["evidence"]]})
        for p in it["prs"]:
            rows.append({"pr": p, "title": it["text"].split(":")[0].split(",")[0], "group": "smaller", "item": "", "pages": []})
    vals["changes_n"] = len(seen)
    text = {k: _fill("text " + k, v, vals) for k, v in y["text"].items()}
    rows.sort(key=lambda r: r["pr"])
    dates = sorted({p["date"] for p in prs} | {"2026-11-23"})
    return {"content": {"text": text, "groups": groups, "smaller": {"intro": y["smaller"]["intro"], "items": smaller}, "rows": rows,
                        "values": vals},
            "check": {"values": vals, "dates": dates, "prs": sorted(known)}}


if __name__ == "__main__":
    print(json.dumps(build(), indent=1)[:3000])
