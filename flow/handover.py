#!/usr/bin/env python3
"""handover.yaml: one source of truth per design, rendered for two readers (brief 68).

    python -m flow.handover fill  designs/<d>    # read every cited record: value from its field, sha256 of record and files
    python -m flow.handover write designs/<d>    # fill, then render README.md, AGENT.md and docs/handover/*.svg
    python -m flow.handover check designs/<d>    # problems (exit 1) and stale claims (warnings), nothing written
    python -m flow.handover fresh designs/<d>    # the freshness report as JSON (for resume: stale records, changed files)

The standard is docs/documentation_standard.md; flow/doccheck.py runs `check` over every design in CI.

What lives where:
- handover.yaml (schema flow/handover.schema.json): the facts. Numbers in `measurements` are never typed: each names
  its record and a `field` (JSON/YAML path such as `builds.b2_mic_pdm.wns_ns` or `runs[0].pass`) or a `match` (a
  regular expression with one group, for text records); `fill` copies the value and the record's sha256 in.
- README.md: rendered from handover.yaml, keeping the hand-written prose between `<!-- prose:NAME -->` and
  `<!-- /prose:NAME -->` markers (one per section). Text outside the markers is regenerated.
- AGENT.md: rendered from handover.yaml only, compact, every claim with its record path and hash prefix.

What `check` enforces (each is a problem, exit 1):
- the file validates against the schema, and its `id` is the directory name;
- no placeholder text (TODO, TBD, "n/a", "...") and minimum lengths in the prose fields;
- every measurement's value equals its record's value at `field`/`match` while the record's sha256 is unchanged
  (a changed record makes the claim *stale*, a warning, not wrong);
- every record, file and interface document exists; every clock frequency agrees with its source (an XDC period);
- each of resources, timing, power, latency and throughput has a measurement or a gap that says why not;
- every evidence entry that did not pass, and every gate in `state.gates` that did not pass, has a gap about it;
- hardware evidence and every measurement state their conditions;
- every number in the README's prose blocks is in handover.yaml, in a cited record, or in `numbers_allow` (with a
  reason);
- README.md, AGENT.md and the SVGs equal a fresh rendering; no Vivado release other than 2026.1 is named.

Parts C and D reuse this module: `fill()`/`write()` at sign-off (the agent writes handover.yaml; code fills the
numbers), `freshness()` when resuming (stale records, changed files, pins against today's).
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = Path(__file__).with_name("handover.schema.json")
VIVADO = "2026.1"
CATEGORIES_REQUIRED = ["resources", "timing", "power", "latency", "throughput"]
SECTIONS = [("what", None), ("parameters", "Technical parameters"), ("build", "How to build, run and reproduce"),
            ("verified", "Verified"), ("measured", "Measured"), ("gaps", "Known gaps and limits"),
            ("next", "Next steps"), ("history", "History")]
# Device capacity for the utilisation chart (AMD DS180 7-series overview; DS987 Zynq UltraScale+ for the K26 SOM part)
CAPACITY = {"xc7a100tcsg324-1": {"lut": 63400, "ff": 126800, "bram36": 135, "dsp": 240},
            "xck26-sfvc784-2LV-c": {"lut": 117120, "ff": 234240, "bram36": 144, "dsp": 1248}}
PLACEHOLDER = re.compile(r"\b(TODO|TBD|FIXME|XXX+|lorem ipsum|placeholder|fill (this )?in|to be written|coming soon)\b"
                         r"|^\s*(-+|n/?a|none|nothing|\.\.\.|\?+|tbc)\s*\.?\s*$", re.I)
NUM = re.compile(r"(?<![\w.])[+-]?\d[\d,]*(?:\.\d+)?")
PROSE = re.compile(r"<!-- prose:(\w+) -->\n(.*?)<!-- /prose:\1 -->", re.S)
BANNED = [(re.compile(r"\bVivado\s+(?!2026\.1\b)20\d\d\.\d"), "names a Vivado release other than 2026.1"),
          (re.compile(r"\bImplementer\b"), "uses the retired role name 'Implementer'"),
          (re.compile(r"AI coding assistant", re.I), "uses the phrase 'AI coding assistant'")]
RECORD_DIRS = ("results/", "ip_lib/<entry>/char/")
MIN_WORDS = {"summary": 20, "gap": 5, "next": 4, "evidence": 4, "measurement": 2}


# ------------------------------------------------------------------------------------------------------ helpers
def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def rel(p: Path) -> str:
    return str(p.resolve().relative_to(ROOT))


def load(ddir: Path) -> dict:
    return yaml.safe_load((ddir / "handover.yaml").read_text())


def _parse_record(p: Path):
    if p.suffix == ".json":
        return json.loads(p.read_text())
    if p.suffix == ".jsonl":
        return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    if p.suffix in (".yaml", ".yml"):
        return yaml.safe_load(p.read_text())
    return None


def lookup(obj, path: str):
    """`a.b[2].c` into nested dicts and lists; a key may itself contain dots if written as ["key.with.dots"]."""
    for tok in re.findall(r'\["([^"]+)"\]|\[(-?\d+)\]|([^.\[\]]+)', path):
        key, idx, name = tok
        if idx:
            obj = obj[int(idx)]
        else:
            obj = obj[key or name]
    return obj


def record_value(m: dict, root: Path = ROOT):
    """The value a measurement cites, read from its record now."""
    p = root / m["record"]
    if "field" in m:
        data = _parse_record(p)
        if data is None:
            raise ValueError(f"{m['record']}: `field` needs a JSON or YAML record (use `match` for text)")
        v = lookup(data, m["field"])
        if isinstance(v, (dict, list)):
            raise ValueError(f"{m['record']}#{m['field']} is not a single value")
        return v
    g = re.search(m["match"], p.read_text(errors="replace"), re.M)
    if not g or g.re.groups != 1:
        raise ValueError(f"{m['record']}: /{m['match']}/ does not match (or has not exactly one group)")
    s = g.group(1).replace(",", "")
    try:
        return int(s) if re.fullmatch(r"[+-]?\d+", s) else float(s)
    except ValueError:
        return g.group(1)


def same(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return a == b


def fmt(v) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:g}" if abs(v) < 1e6 else f"{v:.6g}"
    if isinstance(v, int):
        return f"{v:,}" if abs(v) >= 10000 else str(v)
    return str(v)


# ------------------------------------------------------------------------------------------------------ fill
def fill(h: dict, ddir: Path, build_id: bool = False) -> dict:
    """Values and hashes from the records (the only way a number gets into handover.yaml)."""
    for m in h.get("measurements") or []:
        m["value"] = record_value(m)
        m["sha256"] = sha256(ROOT / m["record"])
    for e in h.get("evidence") or []:
        e["sha256"] = sha256(ROOT / e["record"])
    for f in h.get("files") or []:
        p = ROOT / f["path"]
        f["sha256"] = sha256(p) if p.is_file() else None
    st = h.setdefault("state", {})
    st["vivado"] = VIVADO
    from flow import manifest
    st["kb_pin"] = manifest.kb_pin(ROOT)
    if build_id and (ddir / "build.yaml").exists():
        st["build_id"] = manifest.show(ddir, st.get("variant", "base"), VIVADO, 2)["build_id"]
    return h


def dump(h: dict) -> str:
    order = ["schema", "id", "title", "kind", "produced_by", "summary", "scope_not", "target", "clocks", "resets",
             "interfaces", "parameters", "files", "commands", "evidence", "measurements", "gaps", "next_steps",
             "open_questions", "history", "agent_run", "numbers_allow", "state"]
    out = {k: h[k] for k in order if k in h}
    out.update({k: v for k, v in h.items() if k not in out})
    head = ("# Brief 68 handover: the facts behind README.md and AGENT.md (docs/documentation_standard.md).\n"
            "# Measurement values and every sha256 are filled from the records by `python -m flow.handover fill`;\n"
            "# do not type them. Render with `python -m flow.handover write <this directory>`.\n")
    return head + yaml.safe_dump(out, sort_keys=False, allow_unicode=True, width=118)


# ------------------------------------------------------------------------------------------------------ check
def _words(s: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+", s or ""))


def _strings(v, path=""):
    if isinstance(v, str):
        yield path, v
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from _strings(x, f"{path}[{i}]")
    elif isinstance(v, dict):
        for k, x in v.items():
            yield from _strings(x, f"{path}.{k}" if path else k)


def _tokens_of_text(t: str) -> set:
    return {x.lstrip("+").replace(",", "") for x in NUM.findall(t)} | {x.replace(",", "") for x in
                                                                    re.findall(r"\d[\d,]*(?:\.\d+)?", t)}


def _num_tokens(v) -> set:
    out = set()
    if isinstance(v, bool) or v is None:
        return out
    if isinstance(v, (int, float)):
        f = float(v)
        out |= {str(v), fmt(v).replace(",", ""), f"{f:g}", f"{abs(f):g}", f"{f:.1f}", f"{f:.2f}", f"{f:.3f}"}
        if f == int(f):
            out.add(str(int(f)))
        return out
    if isinstance(v, str):
        return _tokens_of_text(v)
    for x in (v.values() if isinstance(v, dict) else v):
        out |= _num_tokens(x)
    return out


def allowed_numbers(h: dict) -> set:
    """Numbers a prose block may use: anything in handover.yaml (other than numbers_allow itself, which is added by
    token), anything in a cited record whose hash still matches, and the allow-list."""
    toks = _num_tokens({k: v for k, v in h.items() if k != "numbers_allow"})
    for c in (h.get("evidence") or []) + (h.get("measurements") or []):
        p = ROOT / c["record"]
        if p.is_file() and p.stat().st_size < 8_000_000 and c.get("sha256") == sha256(p):
            toks |= _tokens_of_text(p.read_text(errors="replace"))
    toks |= {a["token"].replace(",", "") for a in h.get("numbers_allow") or []}
    return toks


def _clock_ok(c: dict) -> bool:
    p = ROOT / c["source"]
    if not p.is_file():
        return False
    t = p.read_text(errors="replace")
    periods = re.findall(r"-period\s+([\d.]+)", t)
    if any(abs(1000.0 / float(x) - c["mhz"]) < 0.01 for x in periods if float(x) > 0):
        return True
    return f"{c['mhz']:g}" in _tokens_of_text(t)


def _validate(h: dict) -> list[str]:
    try:
        import jsonschema
    except ImportError:                                             # CI installs it; keep a minimal check otherwise
        return [] if isinstance(h, dict) and h.get("schema") == "fda-handover/1" else ["not an fda-handover/1 file"]
    v = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text()))
    return [f"schema: {'/'.join(map(str, e.absolute_path)) or '(top)'}: {e.message}" for e in v.iter_errors(h)]


def problems(ddir: Path, h: dict | None = None, readme: str | None = None) -> tuple[list[str], list[str]]:
    """(problems, stale): problems fail the check; stale claims are warnings (the record changed after the handover).
    `h` and `readme` default to the files on disk (tests pass edited copies)."""
    errs, stale = [], []
    try:
        h = h if h is not None else load(ddir)
    except (OSError, yaml.YAMLError) as ex:
        return [f"handover.yaml: {ex}"], []
    errs += _validate(h)
    if errs:
        return errs, stale
    if h["id"] != ddir.name:
        errs.append(f"id {h['id']!r} is not the directory name {ddir.name!r}")
    if h["target"]["tool"] not in (f"Vivado {VIVADO}", "none"):
        errs.append(f"target.tool must be 'Vivado {VIVADO}' or 'none' (published text names only {VIVADO})")
    # placeholders and minimum lengths
    for path, s in _strings({k: v for k, v in h.items() if k not in ("commands", "files", "state", "numbers_allow")}):
        if PLACEHOLDER.search(s) and not path.endswith((".field", ".match", ".record", ".path", ".doc", ".source")):
            errs.append(f"{path}: placeholder text {s!r}")
    if _words(h["summary"]) < MIN_WORDS["summary"]:
        errs.append(f"summary: under {MIN_WORDS['summary']} words")
    for i, g in enumerate(h["gaps"]):
        if _words(g["text"]) < MIN_WORDS["gap"]:
            errs.append(f"gaps[{i}]: under {MIN_WORDS['gap']} words")
    for i, s in enumerate(h["next_steps"]):
        if _words(s) < MIN_WORDS["next"]:
            errs.append(f"next_steps[{i}]: under {MIN_WORDS['next']} words")
    for e in h["evidence"]:
        if _words(e["what"]) < MIN_WORDS["evidence"]:
            errs.append(f"{e['id']}: what is under {MIN_WORDS['evidence']} words")
    ids = [x["id"] for x in h["evidence"] + h["measurements"]]
    if len(ids) != len(set(ids)):
        errs.append("evidence and measurement ids must be unique")
    about = {g["about"] for g in h["gaps"]}
    # evidence
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    for e in h["evidence"]:
        p = ROOT / e["record"]
        if not p.exists():
            errs.append(f"{e['id']}: record {e['record']} does not exist")
            continue
        if p.is_file() and e.get("sha256") != sha256(p):
            stale.append(f"{e['id']}: {e['record']} changed since the handover (sha256)")
        if e["result"] != "pass" and e["id"] not in about:
            errs.append(f"{e['id']}: result {e['result']} needs a gap with about: {e['id']}")
        if e["activity"] == "board" and _words(e.get("conditions", "")) < 3:
            errs.append(f"{e['id']}: board evidence must state its operating conditions")
        if e.get("how") == "ci" and not (e["record"] in ci or (Path(e["record"]).name.startswith("test_")
                                                                and not e["record"].endswith("_rtl.py"))):
            errs.append(f"{e['id']}: how: ci, but {e['record']} is not run by .github/workflows/ci.yml")
    for gname, r in (h["state"].get("gates") or {}).items():
        if r != "pass" and gname not in about:
            errs.append(f"state.gates.{gname}: {r} needs a gap with about: {gname}")
    # measurements: the value must be the record's
    for m in h["measurements"]:
        p = ROOT / m["record"]
        if not (m["record"].startswith("results/") or (m["record"].startswith("ip_lib/") and "/char/" in m["record"])) or p.name in ("README.md", "AGENT.md", "handover.yaml"):
            errs.append(f"{m['id']}: a measurement's record must be a results file under {', '.join(RECORD_DIRS)} "
                        "(not a README, AGENT.md or handover.yaml)")
            continue
        if not p.is_file():
            errs.append(f"{m['id']}: record {m['record']} does not exist")
            continue
        try:
            now = record_value(m)
        except (KeyError, IndexError, TypeError, ValueError) as ex:
            errs.append(f"{m['id']}: cannot read {m['record']} at {m.get('field') or m.get('match')}: {ex}")
            continue
        if m.get("sha256") != sha256(p):
            stale.append(f"{m['id']}: {m['record']} changed since the handover (sha256); value {m.get('value')!r}, "
                         f"record now {now!r}")
        elif not same(m.get("value"), now):
            errs.append(f"{m['id']}: value {m.get('value')!r} is not the record's {now!r} "
                        f"({m['record']}#{m.get('field') or m.get('match')})")
    cats = {m["category"] for m in h["measurements"]}
    for c in CATEGORIES_REQUIRED:
        if c not in cats and c not in about:
            errs.append(f"technical parameter {c!r}: no measurement and no gap with about: {c}")
    # files, interfaces, clocks
    for f in h["files"]:
        p = ROOT / f["path"]
        if p.parent == ddir.resolve() and p.name in ("README.md", "AGENT.md", "handover.yaml"):
            errs.append(f"files: {f['path']} is a rendering of this handover; list source files only")
            continue
        if not (p.exists() or list(ROOT.glob(f["path"]))):
            errs.append(f"files: {f['path']} does not exist")
        elif p.is_file() and f.get("sha256") and f["sha256"] != sha256(p):
            stale.append(f"files: {f['path']} changed since the handover")
    for i in h["interfaces"]:
        d = i.get("doc")
        if d and not d.startswith("http") and not (ROOT / d.split("#")[0]).exists():
            errs.append(f"interface {i['name']}: doc {d} does not exist")
    for c in h["clocks"]:
        if not _clock_ok(c):
            errs.append(f"clock {c['name']}: {c['mhz']} MHz does not agree with {c['source']}")
    if h.get("agent_run") and not (ROOT / h["agent_run"]["record"]).exists():
        errs.append(f"agent_run: {h['agent_run']['record']} does not exist")
    # renderings
    rd = ddir / "README.md"
    if readme is None:
        readme = rd.read_text() if rd.exists() else ""
    prose = prose_blocks(readme)
    want = render_all(h, ddir, prose)
    for name, text in want.items():
        p = ddir / name
        if not p.exists() or (readme if name == "README.md" else p.read_text()) != text:
            errs.append(f"{name} is not current (run: python -m flow.handover write {rel(ddir)})")
    okn = allowed_numbers(h)
    for k, body in prose.items():
        for tok in NUM.findall(re.sub(r"\]\([^)]*\)|<!--.*?-->", " ", body)):
            t = tok.lstrip("+").replace(",", "")
            if t not in okn and t.lstrip("-") not in okn:
                errs.append(f"README prose:{k}: number {tok} is not in handover.yaml, a cited record or numbers_allow")
    for name, text in want.items():
        for rx, why in BANNED:
            if rx.search(text):
                errs.append(f"{name} {why}")
    return errs, stale


def freshness(ddir: Path, deep: bool = False) -> dict:
    """For resume (Part D): what changed since the handover. deep=True also recomputes the build ID (prepare.py)."""
    h = load(ddir)
    _, stale = problems(ddir, h)
    from flow import manifest
    out = {"design": rel(ddir), "stage": h["state"]["stage"], "stale": stale,
           "changed_files": [f["path"] for f in h["files"] if (ROOT / f["path"]).is_file() and f.get("sha256")
                             and f["sha256"] != sha256(ROOT / f["path"])],
           "kb_pin": {"handover": h["state"]["kb_pin"], "now": manifest.kb_pin(ROOT)},
           "vivado": {"handover": h["state"]["vivado"], "now": VIVADO}}
    if deep and (ddir / "build.yaml").exists():
        out["build_id"] = {"handover": h["state"]["build_id"],
                           "now": manifest.show(ddir, h["state"].get("variant", "base"), VIVADO, 2)["build_id"]}
    return out


# ------------------------------------------------------------------------------------------------------ render
def prose_blocks(readme: str) -> dict:
    return {k: v for k, v in PROSE.findall(readme)}


def _link(target: str, ddir: Path) -> str:
    import os
    return os.path.relpath(ROOT / target, ddir)


def _cell(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def _block(name: str, prose: dict) -> list[str]:
    return ["", f"<!-- prose:{name} -->", prose.get(name, "").rstrip("\n") + ("\n" if prose.get(name, "").strip() else "")
            + f"<!-- /prose:{name} -->"]


def render_readme(h: dict, ddir: Path, prose: dict, svgs: dict) -> str:
    rid = rel(ddir)
    byk = {m.get("key"): m for m in h["measurements"] if m.get("key")}
    L = [f"# {h['id']}: {h['title']}", "",
         f"<!-- Generated from handover.yaml by flow/handover.py (brief 68). Edit handover.yaml, or the text between the "
         f"prose markers, then run: python -m flow.handover write {rid} -->", "", h["summary"].strip(), "",
         "Not in scope:", ""]
    L += [f"- {s}" for s in h["scope_not"]]
    who = {"human": "written by hand", "agent": "produced by the agent", "human+agent": "written by hand with agent runs"}
    L += ["", f"Kind: {h['kind']}; {who[h['produced_by']]}"
          + (f" (agent run `{h['agent_run']['run_id']}`, [record]({_link(h['agent_run']['record'], ddir)}))"
             if h.get("agent_run") else "") + f". State: {h['state']['stage']}. For an agent: [AGENT.md](AGENT.md)."]
    if "architecture.svg" in svgs:
        L += ["", "![Block diagram: the design's blocks and the links between them](docs/handover/architecture.svg)"]
    L += _block("what", prose)
    # technical parameters
    t = h["target"]
    L += ["", "## Technical parameters", "", "| Item | Value |", "|---|---|", f"| Part | `{t['part']}` |",
          f"| Board | {_cell(t['board'])} |", f"| Top | `{t['top']}` |", f"| Tool | {t['tool']} |"]
    if t.get("note"):
        L.append(f"| Note | {_cell(t['note'])} |")
    L += ["", "Clocks:", ""]
    L += [f"- `{c['name']}`: {fmt(c['mhz'])} MHz (from `{c['source']}`)" + (f"; {c['note']}" if c.get("note") else "")
          for c in h["clocks"]] or ["- none (no clock of its own)"]
    L += ["", "Resets:", ""]
    L += [f"- `{r['name']}`, active {r['active']}: {r['note']}" for r in h["resets"]] or ["- none"]
    L += ["", "Interfaces:", ""]
    for i in h["interfaces"]:
        doc = i.get("doc")
        dl = (f" ([datasheet]({doc if doc.startswith('http') else _link(doc, ddir)}))" if doc else "")
        L.append(f"- `{i['name']}` ({i['type']}){dl}: {i['note']}")
    if h["parameters"]:
        L += ["", "| Parameter | Value | Legal range | Note |", "|---|---|---|---|"]
        L += [f"| `{p['name']}` | {_cell(fmt(p['value']))} | {_cell(p['legal'])} | {_cell(p['note'])} |" for p in h["parameters"]]
    else:
        L += ["", "Parameters: none (the board values are the RTL defaults)."]
    L += ["", "| Quantity | Value | Source |", "|---|---|---|"]
    gap_for = {g["about"]: g for g in h["gaps"]}
    for c in CATEGORIES_REQUIRED:
        ms = [m for m in h["measurements"] if m["category"] == c]
        if ms:
            L.append(f"| {c.capitalize()} | " + "; ".join((f"{_cell(m['what'])}: {fmt(m['value'])} {m['unit']}").rstrip()
                                                          for m in ms) + " | " + ", ".join(m["id"] for m in ms) + " |")
        else:
            L.append(f"| {c.capitalize()} | not measured | [Known gaps](#known-gaps-and-limits) |")
    if "resources.svg" in svgs:
        L += ["", "![Resource use as a share of the part, and timing slack](docs/handover/resources.svg)"]
    L += _block("parameters", prose)
    # build
    L += ["", "## How to build, run and reproduce", "", "| Step | Command | Heavy slot | Time |", "|---|---|---|---|"]
    for c in h["commands"]:
        tm = "-" if c["minutes"] is None else f"about {fmt(c['minutes'])} min"
        L.append(f"| {_cell(c['what'])}{('; needs ' + _cell(c['needs'])) if c.get('needs') else ''} | "
                 f"`{_cell(c['cmd'])}` | {'yes' if c['heavy'] else 'no'} | {tm} |")
    st = h["state"]
    L += ["", f"Tool: Vivado {st['vivado']}. Build ID of the inputs at handover: "
          + (f"`{st['build_id']}` (`python flow/manifest.py show {rid}`: what a rebuild of today's sources and flow would "
             "carry; it changes when any build input or the flow changes, so it can differ from the build ID in an older "
             "evidence record)."
             if st.get("build_id") else "none (no Vivado build of this directory).")
          + (f" Knowledge-bank pin: `{st['kb_pin']}`." if st.get("kb_pin") else ""), "",
          "| File | What |", "|---|---|"]
    L += [f"| [`{f['path']}`]({_link(f['path'], ddir)}) | {_cell(f['what'])} |" for f in h["files"]]
    L += _block("build", prose)
    # verified
    L += ["", "## Verified", ""]
    if "verification.svg" in svgs:
        L += ["![Verification matrix: each activity and its result](docs/handover/verification.svg)", ""]
    L += ["| ID | Activity | Result | What | Evidence | Conditions |", "|---|---|---|---|---|---|"]
    for e in h["evidence"]:
        runs = f" ({e['runs']} runs)" if e.get("runs") else ""
        how = " (run in CI)" if e.get("how") == "ci" else ""
        L.append(f"| {e['id']} | {e['activity']} | {e['result']}{runs} | {_cell(e['what'])} | "
                 f"[`{e['record']}`]({_link(e['record'], ddir)}){how} | {_cell(e.get('conditions') or '-')} |")
    if st.get("gates"):
        L += ["", "Gates at handover: " + ", ".join(f"`{k}` {v}" for k, v in st["gates"].items()) + "."]
    L += _block("verified", prose)
    # measured
    L += ["", "## Measured", ""]
    if h["measurements"]:
        L += ["Every value is read from the record by `python -m flow.handover fill`, not typed.", "",
              "| ID | What | Value | Runs | Source | Conditions |", "|---|---|---|---|---|---|"]
        for m in h["measurements"]:
            where = m.get("field") or "matched text"
            L.append(f"| {m['id']} | {_cell(m['what'])} | {(fmt(m['value']) + ' ' + m['unit']).rstrip()} | {m.get('runs', 1)} | "
                     f"[`{m['record']}`]({_link(m['record'], ddir)}) `{_cell(where)}` | {_cell(m['conditions'])} |")
    else:
        L += ["Nothing measured; see Known gaps."]
    L += _block("measured", prose)
    L += ["", "## Known gaps and limits", ""]
    L += [f"- **{g['about']}**: {g['text']}" for g in h["gaps"]]
    L += _block("gaps", prose)
    L += ["", "## Next steps", ""]
    L += [f"{i}. {s}" for i, s in enumerate(h["next_steps"], 1)]
    if h["open_questions"]:
        L += ["", "Open questions:", ""] + [f"- {q}" for q in h["open_questions"]]
    L += _block("next", prose)
    L += ["", "## History", "", "| Date | Brief | PR | What |", "|---|---|---|---|"]
    L += [f"| {x['date']} | {x.get('brief', '-')} | {('#' + str(x['pr'])) if x.get('pr') else '-'} | {_cell(x['note'])} |"
          for x in h["history"]]
    L += _block("history", prose)
    return "\n".join(L) + "\n"


def render_agent(h: dict, ddir: Path) -> str:
    s = lambda x: (x or "")[:10]
    rid = rel(ddir)
    t, st = h["target"], h["state"]
    L = [f"# AGENT {h['id']} (fda-handover/1)",
         f"source: {rid}/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh {rid}",
         "", "## identity",
         f"kind={h['kind']} produced_by={h['produced_by']} part={t['part']} board={t['board']} top={t['top']} tool={t['tool']}"]
    if h.get("agent_run"):
        L.append(f"agent_run={h['agent_run']['run_id']} record={h['agent_run']['record']}")
    L += ["", "## summary", " ".join(h["summary"].split()), "not: " + "; ".join(h["scope_not"]),
          "", "## state", f"stage={st['stage']} vivado={st['vivado']} kb_pin={st.get('kb_pin')} build_id={st.get('build_id')}"]
    if st.get("gates"):
        L.append("gates: " + " ".join(f"{k}={v}" for k, v in st["gates"].items()))
    L += ["", "## interface"]
    L += [f"clk {c['name']} {fmt(c['mhz'])}MHz" for c in h["clocks"]]
    L += [f"rst {r['name']} active-{r['active']}: {r['note']}" for r in h["resets"]]
    L += [f"if {i['name']} {i['type']}: {i['note']}" + (f" doc={i['doc']}" if i.get("doc") else "") for i in h["interfaces"]]
    L += [f"param {p['name']}={fmt(p['value'])} legal={p['legal']}" for p in h["parameters"]]
    L += ["", "## files"] + [f"{f['path']} {s(f.get('sha256'))}: {f['what']}" for f in h["files"]]
    L += ["", "## commands"] + [f"{'[heavy] ' if c['heavy'] else ''}{c['what']}"
                                + (f" (~{fmt(c['minutes'])}min)" if c["minutes"] is not None else "") + f": {c['cmd']}"
                                for c in h["commands"]]
    recs = {}
    for c in h["evidence"] + h["measurements"]:
        recs.setdefault(c["record"], (f"R{len(recs) + 1}", c.get("sha256")))
    L += ["", "## records (path sha256-prefix; claims below cite R<n>)"] + [f"{r} {p} {s(sh)}" for p, (r, sh) in recs.items()]
    L += ["", "## evidence"] + [f"{e['id']} {e['activity']} {e['result']}" + (f" x{e['runs']}" if e.get("runs") else "")
                                + f" {recs[e['record']][0]}{' ci' if e.get('how') == 'ci' else ''}: {e['what']}"
                                + (f" | cond: {e['conditions']}" if e.get("conditions") else "") for e in h["evidence"]]
    ms, prev = [], None
    for m in h["measurements"]:                 # conditions repeated from the line above are written as "ditto"
        cond = "ditto" if m["conditions"] == prev else m["conditions"]
        prev = m["conditions"]
        ms.append(f"{m['id']} {m['category']} {m.get('key') or '-'}={fmt(m['value'])}{m['unit'] and ' ' + m['unit']}"
                  f" {recs[m['record']][0]}#{m.get('field') or 're'}: {m['what']} | {cond}")
    L += ["", "## measured"] + (ms or ["none"])
    L += ["", "## gaps"] + [f"[{g['about']}] {g['text']}" for g in h["gaps"]]
    L += ["", "## next_actions"] + [f"{i}. {x}" for i, x in enumerate(h["next_steps"], 1)]
    if h["open_questions"]:
        L += ["", "## open_questions"] + [f"- {q}" for q in h["open_questions"]]
    L += ["", "## history"] + [f"{x['date']} {x.get('brief', '-')} pr={x.get('pr') or '-'}: {x['note']}" for x in h["history"]]
    return "\n".join(L) + "\n"


# --- graphics: plain SVG (GitHub shows them through <img>, so no scripts and no external CSS); black on white
_SVG_HEAD = ('<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
             'font-family="Helvetica, Arial, sans-serif" font-size="12" role="img" aria-label="{label}">'
             '<rect width="{w}" height="{h}" fill="#fff"/>')


def _x(s) -> str:
    return html.escape(str(s), quote=True)


def svg_verification(h: dict) -> str:
    cols = ["pass", "partial", "fail", "waived", "not-run"]
    rows = h["evidence"]
    w, rh, x0 = 640, 22, 300
    hh = 40 + rh * len(rows) + 10
    out = [_SVG_HEAD.format(w=w, h=hh, label="Verification matrix"),
           '<text x="8" y="16" font-weight="bold">Verification</text>']
    for j, c in enumerate(cols):
        out.append(f'<text x="{x0 + 22 + j * 66}" y="34" text-anchor="middle">{c}</text>')
    for i, e in enumerate(rows):
        y = 40 + i * rh
        out.append(f'<line x1="8" y1="{y}" x2="{w - 8}" y2="{y}" stroke="#ccc"/>')
        lab = f"{e['id']} {e['activity']}: {e['what']}"
        out.append(f'<text x="8" y="{y + 15}">{_x(lab[:44] + ("..." if len(lab) > 44 else ""))}</text>')
        for j, c in enumerate(cols):
            cx = x0 + 22 + j * 66
            if e["result"] == c:
                fill = {"pass": "#000", "partial": "#777", "fail": "#fff", "waived": "#bbb", "not-run": "#fff"}[c]
                out.append(f'<rect x="{cx - 7}" y="{y + 4}" width="14" height="14" fill="{fill}" stroke="#000"/>')
                if c == "fail":
                    out.append(f'<path d="M{cx - 7} {y + 4} l14 14 M{cx + 7} {y + 4} l-14 14" stroke="#000"/>')
            else:
                out.append(f'<circle cx="{cx}" cy="{y + 11}" r="2" fill="#bbb"/>')
    out.append("</svg>")
    return "".join(out) + "\n"


def svg_resources(h: dict) -> str | None:
    cap = CAPACITY.get(h["target"]["part"])
    byk = {m.get("key"): m for m in h["measurements"] if m.get("key")}
    res = [(k, byk[k]) for k in ("lut", "ff", "bram36", "dsp") if k in byk and isinstance(byk[k]["value"], (int, float))]
    if not cap or not res:
        return None
    tim = [(k, byk[k]) for k in ("wns_ns", "whs_ns") if k in byk]
    w, bw = 640, 360
    hh = 34 + 24 * len(res) + (16 + 20 * len(tim) if tim else 0) + 10
    out = [_SVG_HEAD.format(w=w, h=hh, label="Resource use and timing slack"),
           f'<text x="8" y="16" font-weight="bold">Resources, share of {_x(h["target"]["part"])}</text>']
    names = {"lut": "LUT", "ff": "Flip-flops", "bram36": "Block RAM (36 Kb)", "dsp": "DSP slices"}
    for i, (k, m) in enumerate(res):
        y = 30 + i * 24
        frac = min(1.0, float(m["value"]) / cap[k])
        out.append(f'<text x="8" y="{y + 13}">{names[k]}</text>')
        out.append(f'<rect x="150" y="{y + 2}" width="{bw}" height="14" fill="#fff" stroke="#000"/>')
        out.append(f'<rect x="150" y="{y + 2}" width="{max(frac * bw, 1):.1f}" height="14" fill="#000"/>')
        out.append(f'<text x="{150 + bw + 8}" y="{y + 13}">{_x(fmt(m["value"]))} of {cap[k]:,} ({100 * frac:.1f} %)</text>')
    y = 34 + 24 * len(res)
    if tim:
        out.append(f'<text x="8" y="{y + 10}" font-weight="bold">Timing slack (positive: met)</text>')
        for i, (k, m) in enumerate(tim):
            out.append(f'<text x="8" y="{y + 30 + i * 20}">{"Setup (WNS)" if k == "wns_ns" else "Hold (WHS)"}: '
                       f'{_x(fmt(m["value"]))} ns</text>')
    out.append("</svg>")
    return "".join(out) + "\n"


def svg_architecture(ddir: Path) -> str | None:
    """The block diagram: the brief 65A viewer's top level where a block design exists, else architecture.yaml's
    blocks and interfaces."""
    if (ddir / "gen" / "graph.json").exists():
        from flow.blockdesign import viewer
        g = viewer.load_graph(ddir)
        inner = viewer.svg_level(g, "", "wide")
        css = ("<style>text{font-family:Helvetica,Arial,sans-serif;font-size:11px;fill:#000;stroke:none}"
               "rect{fill:#fff;stroke:#000}path,line{stroke:#000;fill:none}polygon,circle{fill:#000;stroke:none}"
               ".bdl-bus{stroke-width:2.5}.bdl-sig{stroke-dasharray:4 3}.bdl-clk,.bdl-rst{stroke-dasharray:2 2}</style>")
        m = re.match(r"(<svg\b[^>]*>)(.*)", inner, re.S)
        if m:
            head = m.group(1) if "xmlns" in m.group(1) else m.group(1).replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
            vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', head)
            if vb:
                head = head.replace("<svg", f'<svg width="{vb.group(1)}" height="{vb.group(2)}"', 1)
            return head + css + '<rect width="100%" height="100%" style="fill:#fff;stroke:none"/>' + m.group(2) + "\n"
        return None
    a = ddir / "architecture.yaml"
    if not a.exists():
        return None
    y = yaml.safe_load(a.read_text())
    blocks = y.get("blocks") or []
    ifs = y.get("interfaces") or []
    w = 640
    hh = 30 + 34 * len(blocks) + (20 + 18 * len(ifs) if ifs else 0) + 10
    out = [_SVG_HEAD.format(w=w, h=hh, label="Architecture: blocks and interfaces"),
           '<text x="8" y="16" font-weight="bold">Blocks (architecture.yaml)</text>']
    for i, b in enumerate(blocks):
        yy = 26 + i * 34
        out.append(f'<rect x="8" y="{yy}" width="150" height="26" fill="#fff" stroke="#000"/>')
        out.append(f'<text x="16" y="{yy + 17}">{_x(b["name"])}</text>')
        out.append(f'<text x="170" y="{yy + 17}">{_x(b.get("function", ""))[:70]}</text>')
    yy = 30 + 34 * len(blocks)
    if ifs:
        out.append(f'<text x="8" y="{yy + 6}" font-weight="bold">Interfaces</text>')
        for i, f in enumerate(ifs):
            out.append(f'<text x="8" y="{yy + 24 + i * 18}">{_x(" - ".join(f.get("between", [])))}: '
                       f'{_x(f.get("name", ""))} ({_x(f.get("protocol", ""))})</text>')
    out.append("</svg>")
    return "".join(out) + "\n"


def render_svgs(h: dict, ddir: Path) -> dict:
    out = {"verification.svg": svg_verification(h)}
    r = svg_resources(h)
    if r:
        out["resources.svg"] = r
    a = svg_architecture(ddir)
    if a:
        out["architecture.svg"] = a
    return out


def render_all(h: dict, ddir: Path, prose: dict) -> dict:
    svgs = render_svgs(h, ddir)
    files = {"README.md": render_readme(h, ddir, prose, svgs), "AGENT.md": render_agent(h, ddir)}
    files.update({f"docs/handover/{k}": v for k, v in svgs.items()})
    return files


def write(ddir: Path, build_id: bool = True) -> list[str]:
    h = load(ddir)
    bad = _validate(h)
    if bad:                                     # never render (or re-dump) a file the schema rejects
        raise SystemExit(f"{rel(ddir)}/handover.yaml: " + "; ".join(bad))
    h = fill(h, ddir, build_id=build_id)
    (ddir / "handover.yaml").write_text(dump(h))
    rd = ddir / "README.md"
    prose = prose_blocks(rd.read_text()) if rd.exists() else {}
    files = render_all(h, ddir, prose)
    for name, text in files.items():
        p = ddir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return list(files)


def agent_tokens(ddir: Path) -> int:
    """AGENT.md size in tokens, approximated as characters / 4 (as knowledge/PACKS.md does)."""
    return len((ddir / "AGENT.md").read_text()) // 4


def main(argv: list[str] | None = None) -> int:
    a = argv if argv is not None else sys.argv[1:]
    if len(a) < 2 or a[0] not in ("fill", "write", "check", "fresh"):
        print(__doc__)
        return 2
    rc = 0
    for d in a[1:]:
        ddir = (ROOT / d).resolve() if not Path(d).is_absolute() else Path(d)
        if a[0] == "fill":
            (ddir / "handover.yaml").write_text(dump(fill(load(ddir), ddir, build_id=True)))
        elif a[0] == "write":
            print(rel(ddir) + ":", ", ".join(write(ddir)), f"(AGENT.md about {agent_tokens(ddir)} tokens)")
        elif a[0] == "fresh":
            print(json.dumps(freshness(ddir, deep=True), indent=1))
        else:
            errs, stale = problems(ddir)
            for e in errs:
                print(f"{rel(ddir)}: {e}")
            for s in stale:
                print(f"{rel(ddir)}: stale: {s}")
            rc |= bool(errs)
    return rc


if __name__ == "__main__":
    sys.exit(main())
