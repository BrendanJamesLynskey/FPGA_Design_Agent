"""Data for site/src/why.html (brief 193): "Why FPGA Guild", the one-page summary in drawers.

    site/why/why.yaml      the authored page: the answer, the drawers (claim, meaning, example, what it does not do yet, link)
    site/data/why.json     what the page reads (written by site/export.py)

Nothing measured is typed by hand. A number in the prose is a {name} placeholder whose value is read from a committed file by one of
site/expertise.py's expressions (see `expertise.EXPR`); the prose itself may hold only names (parts, boards, standards, Vivado 2026.1).
A value may carry `expect: {path, is}`, which pins a value read by list position to the item it must be. Every record a drawer cites
and every page it links must exist. The page's number check sees the resolved values, never the page's own text.
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

import yaml

import expertise

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DIR = HERE / "why"

#: names that contain digits but are not measurements
PROSE_OK = re.compile(
    r"\bVivado 2026\.1\b|\bUG949\b|\bAXI4-Lite\b|\bAXI4-Stream\b|\bKR260\b|\bK26\b|\b10G\b|\bArtix-7\b|\bZynq-7000\b|\b7-series\b|"
    r"\bUltraScale\+|\bLean 4\b|\bSystemVerilog\b|\bUVM 1\.2\b", re.I)
NUM = re.compile(r"-?\d+(?:[.,]\d+)*")
DRAWER_KEYS = ["id", "title", "claim", "means", "example", "not_yet", "link"]


class ContractError(ValueError):
    pass


def _fill(where: str, text, vals: dict) -> str:
    text = str(text)
    bad = [b for b in NUM.findall(PROSE_OK.sub(" ", re.sub(r"\{\w+\}", " ", text))) if any(c.isdigit() for c in b)]
    if bad:
        raise ContractError(f"{where}: typed number(s) {bad}; use a {{name}} placeholder with a value expression")

    def one(m):
        if m.group(1) not in vals:
            raise ContractError(f"{where}: no value named {m.group(1)}")
        v = vals[m.group(1)]
        return v if isinstance(v, str) else expertise.fmt(v)
    out = re.sub(r"\{(\w+)\}", one, text)
    if re.search(r"[{}]", out):
        raise ContractError(f"{where}: malformed placeholder in {text!r}")
    return out


def _values(spec: dict) -> dict:
    out = {}
    for k, v in spec.items():
        if not glob.glob(str(ROOT / v["source"])):
            raise ContractError(f"value {k}: no file {v['source']}")
        out[k] = expertise.evaluate(v["expr"], {"source": v["source"]})
        if "expect" in v:
            doc = json.loads((ROOT / v["source"]).read_text())
            got = expertise._path(doc, v["expect"]["path"])
            if got != v["expect"]["is"]:
                raise ContractError(f"value {k}: {v['expect']['path']} is {got!r}, expected {v['expect']['is']!r} (the list order changed)")
    return out


def _derived(n_drawers: int) -> dict:
    """Values computed from a committed file by a stated formula."""
    fam = json.loads((ROOT / "site/data/family_diffs.json").read_text())
    rows = [r for a in fam["areas"].values() for r in a["rows"]]
    return {"fm_rows": len(rows),                                         # every row of the family matrix
            "fm_tool": sum(1 for r in rows if r["confirmed"] == "tool"),  # rows confirmed by running the tool
            "fm_fam": sum(1 for k in fam["families"] if k != "common"),    # device families (the common row is not one)
            "drawer_n": n_drawers}


def _link(href: str, where: str):
    page, _, frag = href.partition("#")
    if not (HERE / "src" / page).is_file():
        raise ContractError(f"{where}: no page {page}")
    return href


def build() -> dict:
    y = yaml.safe_load((DIR / "why.yaml").read_text())
    ids = [d["id"] for d in y["drawers"]]
    if len(ids) != len(set(ids)) or not all(re.fullmatch(r"[a-z]+", i) for i in ids):
        raise ContractError("drawer ids must be unique lower-case words")
    if not 8 <= len(ids) <= 10:
        raise ContractError("the page has 8 to 10 drawers")
    vals = _values(y["values"])
    vals.update(_derived(len(ids)))
    F = lambda w, t: _fill(w, t, vals)
    drawers = []
    for d in y["drawers"]:
        w = f"drawer {d['id']}"
        miss = [k for k in DRAWER_KEYS if not d.get(k)]
        if miss:
            raise ContractError(f"{w}: missing {miss}")
        srcs = []
        for s in d["example"]["sources"]:
            try:
                srcs.append(expertise.link(s))
            except AssertionError as e:
                raise ContractError(f"{w}: {e}")
        drawers.append({"id": d["id"], "title": d["title"], "claim": F(w + " claim", d["claim"]),
                        "means": [F(w + " means", t) for t in d["means"]],
                        "example": {"text": F(w + " example", d["example"]["text"]), "sources": srcs},
                        "not_yet": F(w + " not_yet", d["not_yet"]),
                        "link": {"href": _link(d["link"]["href"], w), "label": d["link"]["label"]}})
    intro = {k: F("intro " + k, v) for k, v in y["intro"].items()}
    cap = F("diagram", y["diagram_caption"])
    return {"content": {"intro": intro, "caption": cap, "drawers": drawers, "values": vals},
            "check": {"values": vals}}
