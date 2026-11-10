"""Data for site/src/expertise.html (brief 23): the areas of expertise, one drawer each, generated and checked.

    site/data/expertise.yaml   the mapping: areas, the KB sections each draws on, the flow checks, the evidence items
    site/data/skills.json      every skill at the KB pin (unit, section, name, one-line description from the front matter)
    site/data/expertise.json   what the page reads (written by site/export.py)

Nothing on the page is typed by hand except the area's name, plain sentence, known gaps and the evidence wording:
- skills come from skills.json, which export.py regenerates from the private bank at the commit pinned in
  knowledge/PACKS.md when a checkout is present (FDA_KNOWLEDGE_REPO, default ~/Claude_sandbox/FPGA_Design_Agent_Knowledge)
  and otherwise leaves as committed; site/tests checks its counts against PACKS.md, so a skill that is not at the pin
  cannot be named;
- every number in an evidence line is a {n} placeholder filled from a committed result file by a small expression
  (see EXPR below); a template or a gap may not contain any other number;
- the evidence level of an area is computed from its items, never typed: the highest of
  knowledge only < measured in Vivado < checked by the flow < shown in agent runs, that its items support,
  then capped by the area's `cap` if it has one (with the reason shown).
"""
from __future__ import annotations

import fnmatch
import glob
import json
import os
import re
import subprocess
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = "https://github.com/BrendanJamesLynskey/FPGA_Design_Agent"
LEVELS = ["knowledge", "measured", "checked", "agent"]
LEVEL_LABEL = {"knowledge": "Knowledge only", "measured": "Measured in Vivado", "checked": "Checked by the flow",
               "agent": "Shown in agent runs"}
LEVEL_MEANS = {
    "knowledge": "Skills in the knowledge bank and nothing measured or enforced for this area yet.",
    "measured": "Committed results from Vivado runs (or the board) that the skills and checks rest on.",
    "checked": "A stage gate of the flow enforces part of the area on every run that reaches it.",
    "agent": "Development-task runs of the agent, recorded in committed run files, exercised the area.",
}
# numbers that may stay in prose (gaps, summaries, templates) because they are names, not measurements
PROSE_OK = re.compile(r"Brief \d+|PR #\d+|Vivado \d+\.\d+|AXI4|AXI3|DSP48E?\d?|DSP48|MMCM|7-series|Zynq-7000|UltraScale\+?|"
                      r"IEEE-1735|AVAL-46|PLIO-3|BUFC-1|FDA-CON-\d(?:\s+to\s+FDA-CON-\d)?|STD-[A-Z]+-\d+|V[0-3](?: to V[0-3])?|"
                      r"CDC-\d+|M\d+[a-c]?|C\d+|UG\d+|PG\d+|XAPP\d+|PS7|PS8|K26|KR260|xc7[az]\d+[a-z]*\d*|Artix-7|SPI|I2C|HDMI|10G|"
                      r"xpm_cdc_\w+|report_\w+|2025\.2")
NUM = re.compile(r"(?<![\w.#-])\d[\d,]*(?:\.\d+)?")


def pin() -> str:
    t = (ROOT / "knowledge" / "PACKS.md").read_text()
    return re.search(r"Private repo commit: `([0-9a-f]{7,40})`", t).group(1)


def packs_section_counts() -> dict[tuple[str, str], int]:
    """(unit, section) -> skills, from the 'By section' table of knowledge/PACKS.md (units without Ross-as-shipped)."""
    t = (ROOT / "knowledge" / "PACKS.md").read_text().split("## By section", 1)[1].split("## Sources", 1)[0]
    out = {}
    for m in re.finditer(r"^\| `([^`]+?)/?` \| `([^`]+)` \| \w[\w-]* \| (\d+) \|", t, re.M):
        out[(m.group(1), m.group(2))] = int(m.group(3))
    return out


# ---------------------------------------------------------------------------------------------------------------- skills

def _unit_of(parts: list[str]) -> tuple[str, str, str]:
    if parts == ["procedures", "board-onboarding"]:
        return "procedures", "board-onboarding", "board-onboarding"
    n = 1 if parts[0] in ("techniques", "functions", "procedures") else 2
    return "/".join(parts[:n]), parts[n], parts[n + 1]


def short(desc: str, limit: int = 190) -> str:
    d = " ".join(str(desc).split())
    d = re.sub(r"^Use when:?\s*", "", d, flags=re.I)
    d = d[:1].upper() + d[1:]
    if len(d) > limit:
        cut = d[:limit]
        for sep in ("; ", ", ", " "):
            i = cut.rfind(sep)
            if i > limit * 0.6:
                cut = cut[:i]
                break
        d = cut.rstrip(" ,;:") + " ..."
    return d


def kb_checkout() -> Path | None:
    p = Path(os.environ.get("FDA_KNOWLEDGE_REPO", "~/Claude_sandbox/FPGA_Design_Agent_Knowledge")).expanduser()
    if not (p / ".git").exists():
        return None
    r = subprocess.run(["git", "-C", str(p), "cat-file", "-t", pin()], capture_output=True, text=True)
    return p if r.returncode == 0 and r.stdout.strip() == "commit" else None


def skills_from_bank(kb: Path) -> list[dict]:
    """Every skill of the bank at the pinned commit except the Ross-as-shipped copy (AMD's own tree, not ours)."""
    c = pin()
    names = subprocess.run(["git", "-C", str(kb), "ls-tree", "-r", "--name-only", c], capture_output=True, text=True, check=True).stdout.split()
    out = []
    for n in sorted(names):
        if not n.endswith("/SKILL.md") or n.startswith("vendor/ross_shipped/"):
            continue
        text = subprocess.run(["git", "-C", str(kb), "show", f"{c}:{n}"], capture_output=True, text=True, check=True).stdout
        fm = yaml.safe_load(text.split("---", 2)[1])
        unit, section, dirname = _unit_of(n.split("/")[:-1])
        assert fm["name"] == dirname, (n, fm["name"])
        out.append({"unit": unit, "section": section, "name": fm["name"], "description": short(fm["description"])})
    return out


def skills() -> list[dict]:
    """The committed skills.json, regenerated from the bank when it is available at the pin."""
    p = HERE / "data" / "skills.json"
    kb = kb_checkout()
    if kb is not None:
        return skills_from_bank(kb)
    return json.loads(p.read_text())["skills"]


def skills_doc() -> dict:
    return {"pin": pin(), "note": "Names and one-line descriptions only, from the SKILL.md front matter at the pin; Ross-as-shipped is not listed.",
            "skills": skills()}


# ---------------------------------------------------------------------------------------------------------------- evidence

def _path(doc, path: str):
    cur = doc
    for part in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur[part]
        else:
            raise KeyError(path)
    return cur


def _cond_ok(item, cond: str) -> bool:
    for op in ("^=", "!=", ">", "<", "="):
        if op in cond:
            f, v = cond.split(op, 1)
            break
    else:
        f, op, v = cond.rstrip("?"), "?", None
    try:
        x = _path(item, f)
    except (KeyError, IndexError, TypeError):
        return False
    if op == "?":
        return x is not None
    if op == "^=":
        return str(x).startswith(v)
    if op in (">", "<"):
        return isinstance(x, (int, float)) and not isinstance(x, bool) and (x > float(v) if op == ">" else x < float(v))
    eq = str(x).lower() == v.lower()
    return eq if op == "=" else not eq


def _conds_ok(item, conds: str | None) -> bool:
    return all(_cond_ok(item, c) for c in (conds.split(",") if conds else []))


def _read(p: Path):
    if p.suffix == ".json":
        return json.loads(p.read_text())
    if p.suffix == ".jsonl":
        return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    return p.read_text()


def files_of(item) -> list[Path]:
    srcs = item["source"] if isinstance(item["source"], list) else [item["source"]]
    out = []
    for s in srcs:
        hits = sorted(Path(x) for x in glob.glob(str(ROOT / s)))
        if not hits:
            raise FileNotFoundError(f"evidence source matches nothing: {s}")
        out += hits
    return out


def docs_of(item) -> list:
    """JSON documents of the item's sources that pass its `where` conditions (a .jsonl file contributes its lines)."""
    docs = []
    for p in files_of(item):
        if p.suffix not in (".json", ".jsonl"):
            continue
        d = _read(p)
        for x in (d if p.suffix == ".jsonl" else [d]):
            if _conds_ok(x, item.get("where")):
                docs.append(x)
    return docs


EXPR = """expression forms (value of one {n} placeholder), op[@list][:conditions] or get:path or re:regex:
  n                    number of JSON documents (after `where`)
  get:a.b.0.c          the value at a path in the first document
  count[@lst]:c1,c2    documents (or items of the list at path lst in every document) meeting all conditions
  sum|max|min[@lst]:p  of the number at path p over the documents (or list items)
  nfiles               number of source files
  nmatch:REGEX         number of source files whose text matches REGEX
  re:REGEX             first group of REGEX in the first source file's text
conditions: f=v  f!=v  f>x  f<x  f^=prefix  f? (present and not null)"""


def evaluate(expr: str, item):
    op, _, rest = expr.partition(":")
    lst = None
    if "@" in op:
        op, lst = op.split("@", 1)
    if op == "n":
        return len(docs_of(item))
    if op == "nfiles":
        return len(files_of(item))
    if op == "nmatch":
        return sum(1 for p in files_of(item) if re.search(rest, p.read_text()))
    if op == "re":
        m = re.search(rest, files_of(item)[0].read_text(), re.M)
        if not m:
            raise ValueError(f"no match for {rest}")
        return _num(m.group(1))
    docs = docs_of(item)
    if op == "get":
        return _path(docs[0], rest)
    items = [x for d in docs for x in (_path(d, lst) if lst else [d])]
    if op == "count":
        return sum(1 for x in items if _conds_ok(x, rest))
    if op in ("sum", "max", "min"):
        vals = [_path(x, rest) for x in items]
        return {"sum": sum, "max": max, "min": min}[op](vals)
    raise ValueError(expr)


def _num(s: str):
    s = s.replace(",", "")
    return float(s) if "." in s else int(s)


def fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:g}" if v != int(v) or abs(v) < 1000 else f"{int(v):,}"
    if isinstance(v, int) and not isinstance(v, bool) and abs(v) >= 10000:
        return f"{v:,}"
    return str(v)


def render_evidence(item) -> dict:
    vals = [evaluate(e, item) for e in item.get("values", [])]
    for s in item.get("contains", []):
        assert any(s in p.read_text() for p in files_of(item)), (item["source"], "does not contain", s)
    text = item["text"]
    for i, v in enumerate(vals):
        text = text.replace("{%d}" % i, fmt(v))
    assert "{" not in text, ("unfilled placeholder", item["text"])
    srcs = item["source"] if isinstance(item["source"], list) else [item["source"]]
    links = item.get("link", srcs)
    links = [links] if isinstance(links, str) else links
    return {"kind": item["kind"], "text": text, "sources": [link(x) for x in links]}


def link(path: str) -> dict:
    """A repository path (a file, a folder or a glob of files) as a GitHub link; the path must exist."""
    parts, keep = path.split("/"), []
    for x in parts:
        if "*" in x:
            break
        keep.append(x)
    base = "/".join(keep)
    p = ROOT / base
    assert p.exists(), f"link target does not exist: {path}"
    kind = "tree" if p.is_dir() else "blob"
    return {"path": path, "url": f"{REPO}/{kind}/main/{base}"}


# ---------------------------------------------------------------------------------------------------------------- build

def select(sk: list[dict], spec: str) -> list[dict]:
    key, _, only = spec.partition("~")
    unit, section = key.rsplit("/", 1)
    out = [s for s in sk if s["unit"] == unit and fnmatch.fnmatch(s["section"], section)]
    if only:
        out = [s for s in out if any(o in s["name"] for o in only.split("|"))]
    assert out, f"no skills for {spec}"
    return out


def site_anchors() -> dict[str, set[str]]:
    out = {}
    for f in (HERE / "src").glob("*.html"):
        out[f.name] = set(re.findall(r'\bid="([^"]+)"', f.read_text()))
    return out


def prose_numbers(s: str) -> list[str]:
    return NUM.findall(PROSE_OK.sub(" ", s))


def build() -> dict:
    y = yaml.safe_load((HERE / "data" / "expertise.yaml").read_text())
    sk = skills()
    anchors = site_anchors()
    areas, seen = [], set()
    for a in y["areas"]:
        assert a["id"] not in seen, a["id"]
        seen.add(a["id"])
        for k in ("summary", "gaps", "name"):
            for t in ([a[k]] if isinstance(a[k], str) else a[k]):
                assert not prose_numbers(t), (a["id"], k, prose_numbers(t), "numbers belong in evidence items")
        picked, groups = [], {}
        for spec in a["kb"]:
            for s in select(sk, spec):
                if (s["unit"], s["name"]) not in {(p["unit"], p["name"]) for p in picked}:
                    picked.append(s)
        for s in picked:
            groups.setdefault((s["unit"], s["section"]), []).append(s)
        checks = []
        for c in a.get("checks", []):
            f = ROOT / c["file"]
            assert f.exists(), c["file"]
            if c.get("gate"):
                g = ROOT / c.get("gate_in", c["file"])
                assert c["gate"] in g.read_text(), (g.name, c["gate"])
            assert not prose_numbers(c["what"]), (a["id"], c["what"])
            checks.append({"file": c["file"], "url": link(c["file"])["url"], "what": c["what"], "gate": c.get("gate"),
                           "enforced": bool(c.get("enforced"))})
        ev = []
        for it in a.get("evidence", []):
            assert it["kind"] in ("measured", "agent", "example"), it
            tmpl = PROSE_OK.sub(" ", re.sub(r"\{\d+\}", " ", it["text"]))
            assert not NUM.findall(tmpl), (a["id"], "a number in an evidence template", NUM.findall(tmpl))
            ev.append(render_evidence(it))
        cards = []
        for c in a.get("cards", []):
            page, _, frag = c["href"].partition("#")
            assert page in anchors and (not frag or frag in anchors[page]), c["href"]
            cards.append({"href": c["href"], "label": c["label"]})
        for g in a["gaps"]:
            assert g
        sup = ["knowledge"]
        if any(e["kind"] == "measured" for e in ev):
            sup.append("measured")
        if any(c["enforced"] for c in checks):
            sup.append("checked")
        if any(e["kind"] == "agent" for e in ev):
            sup.append("agent")
        level = max(sup, key=LEVELS.index)
        cap = a.get("cap")
        if cap and LEVELS.index(cap["level"]) < LEVELS.index(level):
            level = cap["level"]
        elif cap:
            cap = None
        areas.append({
            "id": a["id"], "name": a["name"], "summary": a["summary"], "level": level, "level_label": LEVEL_LABEL[level],
            "level_n": LEVELS.index(level) + 1, "cap_reason": cap["why"] if cap else None,
            "skills": [{"unit": u, "section": s, "items": [{"name": x["name"], "description": x["description"]} for x in v]}
                       for (u, s), v in groups.items()],
            "checks": checks, "evidence": ev, "cards": cards, "gaps": a["gaps"],
            "counts": {"skills": len(picked), "sections": len(groups), "checks": len(checks),
                       "enforced": sum(c["enforced"] for c in checks), "evidence": len(ev)},
        })
    by = {k: sum(1 for a in areas if a["level"] == k) for k in LEVELS}
    return {"pin": pin(), "levels": [{"id": k, "label": LEVEL_LABEL[k], "means": LEVEL_MEANS[k], "areas": by[k]} for k in LEVELS],
            "areas": areas, "skills_total": len(sk), "skills_used": len({(g["unit"], s["name"]) for a in areas for g in a["skills"] for s in g["items"]})}
