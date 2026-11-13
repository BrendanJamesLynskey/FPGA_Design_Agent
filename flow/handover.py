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
PLACEHOLDER = re.compile(r"\b(TODO|TBD|FIXME|XXX+|lorem ipsum|to be written|coming soon)\b"
                         r"|^\s*(-+|n/?a|none|nothing|\.\.\.|\?+|tbc)\s*\.?\s*$", re.I)
JUNK_WORDS = {"n", "a", "na", "none", "nothing", "tbd", "tbc", "todo", "fixme", "xxx", "known", "gap", "gaps", "x", "the",
              "and", "of", "to", "is", "it", "in", "yet", "not", "applicable"}
NUM = re.compile(r"(?<![\w.])[+-]?\d[\d,]*(?:\.\d+)?")
# a "number word": starts with a digit (or a sign and a digit) and runs to the next space or bracket: 4999, -0.433,
# 1,048,576, 0x80, 16-bit, 1e9, 12_345. Words that start with a letter (ADXL362, b30, x4999) are identifiers and are
# not checked (a documented limit).
NUMWORD = re.compile(r"(?<![\w.])[+-]?\d[\w.,+\-/%]*")
LEAD = re.compile(r"[+-]?\d[\d,]*(?:\.\d+)?")
HEXISH = re.compile(r"^[0-9a-f]{8,}$")
PROSE = re.compile(r"<!-- prose:(\w+) -->\n(.*?)<!-- /prose:\1 -->", re.S)
BANNED = [(re.compile(r"\bVivado[\s-]+v?(?!2026\.1\b)20\d\d\.\d", re.I), "names a Vivado release other than 2026.1"),
          (re.compile(r"\bImplementer\b"), "uses the retired role name for the Designer"),
          (re.compile(r"AI coding assistant", re.I), "uses the phrase 'AI coding assistant'")]
RECORD_DIRS = ("results/", "ip_lib/<entry>/char/")   # plus, for an agent run, its own records (in_run_records)
MIN_WORDS = {"summary": 12, "gap": 4, "next": 4, "evidence": 4, "scope": 3, "board_conditions": 8}
# free-text fields of handover.yaml: their numbers are checked like prose, and they never vouch for a number
FREE = re.compile(r"^(title|summary|scope_not\[\d+\]|target\.note|clocks\[\d+\]\.note|resets\[\d+\]\.(note|name)|"
                  r"interfaces\[\d+\]\.(note|type|name)|parameters\[\d+\]\.(note|legal)|gaps\[\d+\]\.about|files\[\d+\]\.what|commands\[\d+\]\.(what|needs)|"
                  r"evidence\[\d+\]\.(what|conditions)|measurements\[\d+\]\.(what|conditions|unit)|gaps\[\d+\]\.text|"
                  r"next_steps\[\d+\]|open_questions\[\d+\]|history\[\d+\]\.note|agent_run\.note|numbers_allow\[\d+\]\.reason)$")
NO_VOUCH = re.compile(r"(sha256|build_id|kb_pin)$")


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


READ_ERRORS = (KeyError, IndexError, TypeError, ValueError, OSError, yaml.YAMLError, re.error)


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
    if v is None:
        return "(not filled)"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:g}" if abs(v) < 1e6 else f"{v:.6g}"
    if isinstance(v, int):
        return f"{v:,}" if abs(v) >= 10000 else str(v)
    return str(v)


# ------------------------------------------------------------------------------------------------------ fill
def fill(h: dict, ddir: Path, build_id: bool = False) -> dict:
    """Values and hashes from the records (the only way a number gets into handover.yaml). Raises ValueError listing
    every record it could not read (Part C's sign-off step reports these to the Designer)."""
    bad = []
    for m in h.get("measurements") or []:
        try:
            m["value"] = record_value(m)
            m["sha256"] = sha256(ROOT / m["record"])
        except READ_ERRORS as ex:
            bad.append(f"{m.get('id')}: {m.get('record')}: {ex}")
    for e in h.get("evidence") or []:
        p = ROOT / e["record"]
        if p.is_file():
            e["sha256"] = sha256(p)
        else:
            bad.append(f"{e.get('id')}: {e['record']} is not a file")
    for f in h.get("files") or []:
        p = ROOT / f["path"]
        if p.is_file():
            f["sha256"] = sha256(p)
        else:
            bad.append(f"files: {f['path']} is not a file")
    if bad:
        raise ValueError("fill: " + "; ".join(bad))
    st = h.setdefault("state", {})
    st["vivado"] = VIVADO
    from flow import manifest
    st["kb_pin"] = manifest.kb_pin(ROOT)
    if build_id and (ddir / "build.yaml").exists():
        st["build_id"] = manifest.show(ddir, st.get("variant", "base"), VIVADO, 2)["build_id"]
    return h


def dump(h: dict) -> str:
    order = ["schema", "id", "title", "kind", "produced_by", "summary", "scope_not", "target", "clocks", "resets",
             "interfaces", "registers", "parameters", "files", "commands", "evidence", "measurements", "gaps", "next_steps",
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


def meaningful(s: str) -> int:
    """Distinct words that are not placeholder filler, with link targets and URLs removed."""
    s = re.sub(r"\]\([^)]*\)|https?://\S+", " ", s or "")
    return len({w.lower() for w in re.findall(r"[A-Za-z0-9]+", s)} - JUNK_WORDS)


def _strings(v, path=""):
    if isinstance(v, str):
        yield path, v
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from _strings(x, f"{path}[{i}]")
    elif isinstance(v, dict):
        for k, x in v.items():
            yield from _strings(x, f"{path}.{k}" if path else k)


def visible(text: str) -> str:
    """Markdown/HTML as a reader sees it: comments and tags removed, entities decoded."""
    t = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    t = re.sub(r"<[^>]*>", "", t)
    return re.sub(r"<[^>]*>", "", html.unescape(t))


def _norm(w: str) -> str:
    return w.rstrip(".,:;-/%").lstrip("+").replace(",", "")


def _canon(lead: str) -> str:
    """One spelling per number: 1000, 1000.0 and +1000 are the same; 0.10 and 0.1 too."""
    try:
        return f"{float(lead):g}" if len(lead.replace("-", "").replace(".", "")) <= 15 else lead
    except ValueError:
        return lead


def _tokens_of_text(t: str) -> set:
    """What a text vouches for: each number word whole, and its leading number."""
    out = set()
    for w in NUMWORD.findall(t):
        n = _norm(w)
        if HEXISH.match(n):
            continue
        out.add(n)
        m = LEAD.match(n)
        if m:
            lead = m.group(0).replace(",", "").lstrip("+")
            out |= {lead, _canon(lead)}
    return out


def unvouched(text: str, ok: set) -> list[str]:
    """Number words in `text` not vouched for by `ok`: the leading number must be in `ok`; a word with more digits
    after it (0x1F40, 1e9, 12_345) must be in `ok` whole."""
    bad = []
    for w in NUMWORD.findall(visible(text)):
        n = _norm(w)
        if not n or HEXISH.match(n.lower()):         # a hash or build ID is an identifier, not a quantity
            continue
        lead = LEAD.match(n).group(0).replace(",", "").lstrip("+")
        rest = n[LEAD.match(n).end():]
        if n in ok or (lead in ok or lead.lstrip("-") in ok or _canon(lead) in ok) and not re.search(r"\d", rest):
            continue
        bad.append(w)
    return bad


def _value_tokens(v) -> set:
    if isinstance(v, bool) or v is None:
        return set()
    if isinstance(v, (int, float)):
        f = float(v)
        out = {str(v), fmt(v).replace(",", ""), f"{f:g}", f"{abs(f):g}", f"{f:.1f}", f"{f:.2f}", f"{f:.3f}",
               _canon(f"{f:.1f}"), _canon(f"{f:.2f}"), _canon(f"{f:.3f}")}
        if f == int(f):
            out.add(str(int(f)))
        return out
    return _tokens_of_text(str(v))


def allowed_numbers(h: dict, ddir: Path | None = None) -> set:
    """Numbers text may use: the structured fields of handover.yaml (never its free text, hashes or IDs), the text of
    every cited record, design file and local interface document whose hash still matches, and numbers_allow."""
    toks = set()
    for path, s in _strings(h):
        if not FREE.match(path) and not NO_VOUCH.search(path) and not path.startswith("numbers_allow"):
            toks |= _tokens_of_text(s)
    for m in h.get("measurements") or []:
        toks |= _value_tokens(m.get("value"))
    for x in (h.get("clocks") or []):
        toks |= _value_tokens(x.get("mhz"))
    for x in (h.get("parameters") or []):
        toks |= _value_tokens(x.get("value"))
    for x in (h.get("evidence") or []):
        toks |= _value_tokens(x.get("runs"))
    for x in (h.get("history") or []):
        toks |= _value_tokens(x.get("pr"))
    srcs = [(c["record"], c.get("sha256")) for c in (h.get("evidence") or []) + (h.get("measurements") or [])]
    srcs += [(f["path"], f.get("sha256")) for f in h.get("files") or []]
    for p_, sh in srcs:
        p = ROOT / p_
        if p.is_file() and p.stat().st_size < 8_000_000 and sh == sha256(p):
            toks |= _tokens_of_text(p.read_text(errors="replace"))
    for i in h.get("interfaces") or []:
        d = i.get("doc")
        if d and not d.startswith("http") and (ROOT / d.split("#")[0]).is_file():
            toks |= _tokens_of_text((ROOT / d.split("#")[0]).read_text(errors="replace"))
    toks |= _tokens_of_text((ROOT / ".github" / "workflows" / "ci.yml").read_text())   # pinned tool versions
    toks |= {_norm(a["token"]) for a in h.get("numbers_allow") or []}
    return toks


def _clock_ok(c: dict) -> bool:
    """An XDC/SDC source must have a create_clock on a port of this name (or with -name) whose period gives the
    frequency; any other source must be a results record with the frequency as a value."""
    p = ROOT / c["source"]
    if not p.is_file():
        return False
    t = p.read_text(errors="replace")
    if p.suffix in (".xdc", ".sdc"):
        for line in re.findall(r"(?m)^\s*create_clock\b.*$", t):
            per = re.search(r"-period\s+([\d.]+)", line)
            named = re.search(rf"get_ports\s+\{{?\s*{re.escape(c['name'])}\s*\}}?\]|-name\s+{re.escape(c['name'])}\b", line)
            if per and named and float(per.group(1)) > 0 and abs(1000.0 / float(per.group(1)) - c["mhz"]) <= 1e-4 * c["mhz"]:
                return True
        return False
    if c["source"].startswith("results/"):
        return f"{c['mhz']:g}" in _tokens_of_text(t)
    return False


def _validate(h: dict) -> list[str]:
    try:
        import jsonschema
    except ImportError:                                             # CI installs it; keep a minimal check otherwise
        return [] if isinstance(h, dict) and h.get("schema") == "fda-handover/1" else ["not an fda-handover/1 file"]
    v = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text()))
    return [f"schema: {'/'.join(map(str, e.absolute_path)) or '(top)'}: {e.message}" for e in v.iter_errors(h)]


def agent_run_dir(h: dict, ddir: Path) -> Path | None:
    """The run directory of an agent-produced handover (brief 68 C): the directory of ``agent_run.record``, and only when
    the design directory is inside it (the design is that run's own). None otherwise."""
    ar = h.get("agent_run") or {}
    if h.get("produced_by") == "human" or not ar.get("record"):
        return None
    rd = (ROOT / ar["record"]).resolve().parent
    return rd if rd != ROOT and rd in ddir.resolve().parents else None


def in_run_records(p: Path, run_dir: Path, ddir: Path) -> bool:
    """A record the flow wrote for the run: a file of the run directory outside the design directory, or a file under the
    design's ``build/`` (write-denied to every role by the path jail). Files the roles write are never records."""
    p, d = p.resolve(), ddir.resolve()
    if run_dir not in p.parents:
        return False
    return d not in p.parents or (d / "build") in p.parents


def _record_rule(rec: str, ddir: Path) -> str | None:
    p = ROOT / rec
    if p.resolve().parent == ddir.resolve() and p.name in ("README.md", "AGENT.md", "handover.yaml"):
        return f"{rec} is a rendering of this handover and cannot be its own evidence"
    if not p.is_file():
        return f"{rec} is not a file" if p.exists() else f"{rec} does not exist"
    return None


def problems(ddir: Path, h: dict | None = None, readme: str | None = None) -> tuple[list[str], list[str]]:
    """(problems, stale): problems fail the check; stale claims are warnings (the record changed after the handover;
    `doccheck --strict`, which CI runs, fails on them too). `h` and `readme` default to the files on disk."""
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
    if h["target"]["tool"] != "none" and not h["clocks"]:
        errs.append("clocks: a design built with Vivado has at least one clock")
    if h["produced_by"] != "human" and not h.get("agent_run"):
        errs.append(f"produced_by {h['produced_by']} needs agent_run (the run record)")
    # placeholders and minimum lengths (meaningful words: distinct, not filler)
    for path, s in _strings(h):
        if FREE.match(path) and PLACEHOLDER.search(s):
            errs.append(f"{path}: placeholder text {s!r}")
    if meaningful(h["summary"]) < MIN_WORDS["summary"]:
        errs.append(f"summary: under {MIN_WORDS['summary']} distinct meaningful words")
    for i, s in enumerate(h["scope_not"]):
        if meaningful(s) < MIN_WORDS["scope"]:
            errs.append(f"scope_not[{i}]: under {MIN_WORDS['scope']} distinct meaningful words")
    for i, g in enumerate(h["gaps"]):
        if meaningful(g["text"]) < MIN_WORDS["gap"]:
            errs.append(f"gaps[{i}]: under {MIN_WORDS['gap']} distinct meaningful words")
    for i, s in enumerate(h["next_steps"]):
        if meaningful(s) < MIN_WORDS["next"]:
            errs.append(f"next_steps[{i}]: under {MIN_WORDS['next']} distinct meaningful words")
    for e in h["evidence"]:
        if meaningful(e["what"]) < MIN_WORDS["evidence"]:
            errs.append(f"{e['id']}: what is under {MIN_WORDS['evidence']} distinct meaningful words")
    ids = [x["id"] for x in h["evidence"] + h["measurements"]]
    if len(ids) != len(set(ids)):
        errs.append("evidence and measurement ids must be unique")
    about = {g["about"] for g in h["gaps"]}
    # evidence
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    ci_words = set(re.findall(r"[\w./-]+", ci))
    for e in h["evidence"]:
        why = _record_rule(e["record"], ddir)
        if why:
            errs.append(f"{e['id']}: record {why}")
            continue
        if not e.get("sha256"):
            errs.append(f"{e['id']}: no sha256 (run: python -m flow.handover fill {rel(ddir)})")
        elif e["sha256"] != sha256(ROOT / e["record"]):
            stale.append(f"{e['id']}: {e['record']} changed since the handover (sha256)")
        if e["result"] != "pass" and e["id"] not in about:
            errs.append(f"{e['id']}: result {e['result']} needs a gap with about: {e['id']}")
        if e["activity"] == "board" and meaningful(e.get("conditions", "")) < MIN_WORDS["board_conditions"]:
            errs.append(f"{e['id']}: hardware evidence must state its operating conditions (power, temperature, rails, "
                        "or that they were not read)")
        if e.get("how") == "ci":
            name = Path(e["record"]).name
            if not (re.fullmatch(r"test_\w+\.py", name) and (e["record"] in ci_words or not name.endswith("_rtl.py"))):
                errs.append(f"{e['id']}: how: ci, but CI does not run {e['record']} as a test")
    gates = h["state"].get("gates") or {}
    for gname, r in gates.items():
        if r != "pass" and gname not in about:
            errs.append(f"state.gates.{gname}: {r} needs a gap with about: {gname}")
    stage = h["state"]["stage"]
    if stage == "board-verified" and not any(e["activity"] == "board" and e["result"] == "pass" for e in h["evidence"]):
        errs.append("state.stage board-verified needs a passing board evidence entry")
    if stage == "signed-off" and (not gates or any(r != "pass" for r in gates.values())):
        errs.append("state.stage signed-off needs every gate in state.gates to pass")
    # requirements without passing evidence (brief 68 C): a cited verif_gates record's traceability rows that did not pass
    for e in h["evidence"]:
        if Path(e["record"]).name == "verif_gates.json" and (ROOT / e["record"]).is_file():
            try:
                rows = json.loads((ROOT / e["record"]).read_text()).get("traceability") or []
            except (ValueError, AttributeError):
                rows = []
            for r in rows:
                if isinstance(r, dict) and r.get("result") != "pass" and r.get("requirement") not in about:
                    errs.append(f"requirement {r.get('requirement')}: {r.get('method')} evidence is {r.get('result')} in "
                                f"{e['record']}; it needs a gap with about: {r.get('requirement')}")
    # measurements: the value must be the record's
    run_dir = agent_run_dir(h, ddir)
    for m in h["measurements"]:
        p = ROOT / m["record"]
        ok_dir = (in_run_records(p, run_dir, ddir) if run_dir is not None else          # an agent run: its own records only
                  m["record"].startswith("results/") or (m["record"].startswith("ip_lib/") and "/char/" in m["record"]))
        if not ok_dir or p.name in ("README.md", "AGENT.md", "handover.yaml"):
            errs.append(f"{m['id']}: a measurement's record must be a results file under {', '.join(RECORD_DIRS)}, or for "
                        "an agent run a record the flow wrote in the run's own directory (not a README, AGENT.md or "
                        "handover.yaml)")
            continue
        if not p.is_file():
            errs.append(f"{m['id']}: record {m['record']} does not exist")
            continue
        try:
            now = record_value(m)
        except READ_ERRORS as ex:
            errs.append(f"{m['id']}: cannot read {m['record']} at {m.get('field') or m.get('match')}: {ex}")
            continue
        if "value" not in m or not m.get("sha256"):
            errs.append(f"{m['id']}: value or sha256 not filled (run: python -m flow.handover fill {rel(ddir)})")
        elif m["sha256"] != sha256(p):
            stale.append(f"{m['id']}: {m['record']} changed since the handover (sha256); value {m.get('value')!r}, "
                         f"record now {now!r}")
        elif not same(m.get("value"), now):
            errs.append(f"{m['id']}: value {m.get('value')!r} is not the record's {now!r} "
                        f"({m['record']}#{m.get('field') or m.get('match')})")
        if m["category"] in CATEGORIES_REQUIRED and not (isinstance(now, (int, float)) and not isinstance(now, bool)):
            errs.append(f"{m['id']}: a {m['category']} measurement must be a number (record has {now!r}); "
                        "a missing quantity is a gap")
    cats = {m["category"] for m in h["measurements"]}
    for c in CATEGORIES_REQUIRED:
        if c not in cats and c not in about:
            errs.append(f"technical parameter {c!r}: no measurement and no gap with about: {c}")
    # files, interfaces, clocks
    for f in h["files"]:
        why = _record_rule(f["path"], ddir)
        if why:
            errs.append(f"files: {why}")
        elif not f.get("sha256"):
            errs.append(f"files: {f['path']} has no sha256 (run fill)")
        elif f["sha256"] != sha256(ROOT / f["path"]):
            stale.append(f"files: {f['path']} changed since the handover")
    for i in h["interfaces"]:
        d = i.get("doc")
        if d and not d.startswith("http") and not (ROOT / d.split("#")[0]).exists():
            errs.append(f"interface {i['name']}: doc {d} does not exist")
    for c in h["clocks"]:
        if not _clock_ok(c):
            errs.append(f"clock {c['name']}: {c['mhz']} MHz does not agree with {c['source']} (an XDC create_clock "
                        "on that port, or a results record)")
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
    # numbers: free text in handover.yaml and the prose blocks may use only vouched-for numbers
    okn = allowed_numbers(h, ddir)
    for path, s in _strings(h):
        if FREE.match(path) and not path.startswith("numbers_allow"):
            for w in unvouched(s, okn):
                errs.append(f"{path}: number {w} is not in a cited record, a design file, a structured field or numbers_allow")
    for k, body in prose.items():
        for w in unvouched(body, okn):
            errs.append(f"README prose:{k}: number {w} is not in a cited record, a design file, a structured field or "
                        "numbers_allow")
        if re.search(r"\b(TODO|TBD|FIXME)\b", visible(body)):
            errs.append(f"README prose:{k}: placeholder (TODO/TBD/FIXME)")
    for name, text in want.items():
        for rx, why in BANNED:
            if rx.search(text):
                errs.append(f"{name} {why}")
    return errs, stale


def freshness(ddir: Path, deep: bool = False) -> dict:
    """For resume (Part D): what changed since the handover. `errors` lists problems (a missing record, an invalid
    file): a resume must not trust a handover with errors. deep=True also recomputes the build ID (prepare.py)."""
    h = load(ddir)
    errs, stale = problems(ddir, h)
    from flow import manifest
    st = h.get("state") or {}
    out = {"design": rel(ddir), "errors": errs, "stage": st.get("stage"), "stale": stale,
           "changed_files": [f["path"] for f in h.get("files") or []
                             if not (ROOT / f["path"]).is_file() or f.get("sha256") != sha256(ROOT / f["path"])],
           "kb_pin": {"handover": st.get("kb_pin"), "now": manifest.kb_pin(ROOT)},
           "vivado": {"handover": st.get("vivado"), "now": VIVADO}}
    if deep and (ddir / "build.yaml").exists():
        out["build_id"] = {"handover": st.get("build_id"),
                           "now": manifest.show(ddir, st.get("variant", "base"), VIVADO, 2)["build_id"]}
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


def run_line(ar: dict) -> str:
    """The provenance of an agent run (68F), from the run record: model, loops, turns, wall time, tokens, cost."""
    bits = []
    if ar.get("model"):
        bits.append(f"model {ar['model']}" + (f" ({ar['harness']} harness)" if ar.get("harness") else ""))
    for k, w in (("loops", "loops"), ("turns", "turns"), ("tokens", "tokens")):
        if ar.get(k) is not None:
            bits.append(f"{fmt(ar[k])} {w}")
    if ar.get("wall_s") is not None:
        bits.append(f"{fmt(ar['wall_s'])} s wall time")
    if ar.get("cost_usd") is not None:
        bits.append(f"{fmt(ar['cost_usd'])} USD model cost (provider-reported)")
    if ar.get("plan_cost_estimate_usd") is not None:
        bits.append(f"{fmt(ar['plan_cost_estimate_usd'])} USD plan-cost estimate (not billed)")
    if ar.get("stop"):
        bits.append(f"stopped because: {ar['stop']}")
    return ", ".join(bits)


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
    if run_line(h.get("agent_run") or {}):
        L += ["", "Run: " + run_line(h["agent_run"]) + " (from the run record)."]
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
    if h.get("registers"):
        L += ["", "Registers (from spec.yaml; where the RTL differs, the gaps say so):", "",
              "| Offset | Name | Access | Reset | Bits |", "|---|---|---|---|---|"]
        L += [f"| {_cell(r['offset'])} | `{r['name']}` | {_cell(r['access'])} | {_cell(r.get('reset', '-'))} | "
              f"{_cell(r.get('bits', '-'))} |" for r in h["registers"]]
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
            L.append(f"| {c.capitalize()} | " + "; ".join((f"{_cell(m['what'])}: {fmt(m.get('value'))} {m['unit']}").rstrip()
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
        runs = f" ({e['runs']} run{'s' if e['runs'] != 1 else ''})" if e.get("runs") else ""
        how = " (run in CI)" if e.get("how") == "ci" else ""
        L.append(f"| {e['id']} | {e['activity']} | {e['result']}{runs} | {_cell(e['what'])} | "
                 f"[`{e['record']}`]({_link(e['record'], ddir)}){how} | {_cell(e.get('conditions') or '-')} |")
    if st.get("gates"):
        notes = st.get("gate_notes") or {}
        L += ["", "Gates at handover: " + ", ".join(f"`{k}` {v}" + (f" ({notes[k]})" if k in notes else "")
                                                    for k, v in st["gates"].items()) + "."]
    L += _block("verified", prose)
    # measured
    L += ["", "## Measured", ""]
    if h["measurements"]:
        L += ["Every value is read from the record by `python -m flow.handover fill`, not typed.", "",
              "| ID | What | Value | Runs | Source | Conditions |", "|---|---|---|---|---|---|"]
        for m in h["measurements"]:
            where = m.get("field") or "matched text"
            L.append(f"| {m['id']} | {_cell(m['what'])} | {(fmt(m.get('value')) + ' ' + m['unit']).rstrip()} | {m.get('runs', 1)} | "
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
        if run_line(h["agent_run"]):
            L.append("run: " + run_line(h["agent_run"]))
    L += ["", "## summary", " ".join(h["summary"].split()), "not: " + "; ".join(h["scope_not"]),
          "", "## state", f"stage={st['stage']} vivado={st['vivado']} kb_pin={st.get('kb_pin')} build_id={st.get('build_id')}"]
    if st.get("gates"):
        L.append("gates: " + " ".join(f"{k}={v}" + (f" ({(st.get('gate_notes') or {})[k]})" if k in (st.get("gate_notes") or {}) else "")
                                      for k, v in st["gates"].items()))
    L += ["", "## interface"]
    L += [f"clk {c['name']} {fmt(c['mhz'])}MHz" for c in h["clocks"]]
    L += [f"rst {r['name']} active-{r['active']}: {r['note']}" for r in h["resets"]]
    L += [f"if {i['name']} {i['type']}: {i['note']}" + (f" doc={i['doc']}" if i.get("doc") else "") for i in h["interfaces"]]
    L += [f"reg {r['offset']} {r['name']} {r['access']} reset={r.get('reset', '-')} {r.get('bits', '')}".rstrip()
          for r in h.get("registers") or []]
    L += [f"param {p['name']}={fmt(p['value'])} legal={p['legal']}" for p in h["parameters"]]
    compact = h.get("produced_by") == "agent"        # 68F: agent-produced handovers only (hand-written ones keep their rendering)
    short = (lambda p: p[len(rid) + 1:] if p.startswith(rid + "/") else p) if compact else (lambda p: p)
    L += ["", "## files (paths under the design directory are relative to it)" if compact else "## files"] \
        + [f"{short(f['path'])} {s(f.get('sha256'))}: {f['what']}" for f in h["files"]]
    L += ["", "## commands"] + [f"{'[heavy] ' if c['heavy'] else ''}{c['what']}"
                                + (f" (~{fmt(c['minutes'])}min)" if c["minutes"] is not None else "") + f": {c['cmd']}"
                                for c in h["commands"]]
    recs = {}
    for c in h["evidence"] + h["measurements"]:
        recs.setdefault(c["record"], (f"R{len(recs) + 1}", c.get("sha256")))
    L += ["", "## records (path sha256-prefix; claims below cite R<n>)"] + [f"{r} {short(p)} {s(sh)}" for p, (r, sh) in recs.items()]
    L += ["", "## evidence"] + [f"{e['id']} {e['activity']} {e['result']}" + (f" x{e['runs']}" if e.get("runs") else "")
                                + f" {recs[e['record']][0]}{' ci' if e.get('how') == 'ci' else ''}: {e['what']}"
                                + (f" | cond: {e['conditions']}" if e.get("conditions") else "") for e in h["evidence"]]
    ms, prev = [], None
    for m in h["measurements"]:                 # conditions repeated from the line above are written as "ditto"
        cond = "ditto" if m["conditions"] == prev else m["conditions"]
        prev = m["conditions"]
        ms.append(f"{m['id']} {m['category']} {m.get('key') or '-'}={fmt(m.get('value'))}{m['unit'] and ' ' + m['unit']}"
                  f" {recs[m['record']][0]}#{m.get('field') or 're'}: {m['what']} | {cond}")
    L += ["", "## measured"] + (ms or ["none"])
    L += ["", "## gaps"]
    groups: dict[str, list[dict]] = {}
    pointer = {e["id"]: f"{e['activity']} evidence is {e['result']}: " for e in h["evidence"]} if compact else {}
    for g in h["gaps"]:         # gaps that differ only in their subject ("stage X was not run ...") are one line
        if g["about"] in pointer and g["text"].startswith(pointer[g["about"]]) and "listed in the evidence row" in g["text"]:
            continue            # a gap that only points at an evidence row, which the evidence section above already carries
        groups.setdefault(g["text"].replace(g["about"], "\u00a7", 1) if g["about"] in g["text"] else g["text"], []).append(g)
    for key, gs in groups.items():
        if compact and len(gs) > 1 and "\u00a7" in key:
            L.append(f"[{', '.join(g['about'] for g in gs)}] " + key.replace("\u00a7", "(each of these)"))
        else:
            L += [f"[{g['about']}] {g['text']}" for g in gs]
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
    res = [(k, byk[k]) for k in ("lut", "ff", "bram36", "dsp") if k in byk and isinstance(byk[k].get("value"), (int, float))]
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
        frac = min(1.0, float(m.get("value")) / cap[k])
        out.append(f'<text x="8" y="{y + 13}">{names[k]}</text>')
        out.append(f'<rect x="150" y="{y + 2}" width="{bw}" height="14" fill="#fff" stroke="#000"/>')
        out.append(f'<rect x="150" y="{y + 2}" width="{max(frac * bw, 1):.1f}" height="14" fill="#000"/>')
        out.append(f'<text x="{150 + bw + 8}" y="{y + 13}">{_x(fmt(m.get("value")))} of {cap[k]:,} ({100 * frac:.1f} %)</text>')
    y = 34 + 24 * len(res)
    if tim:
        out.append(f'<text x="8" y="{y + 10}" font-weight="bold">Timing slack (positive: met)</text>')
        for i, (k, m) in enumerate(tim):
            out.append(f'<text x="8" y="{y + 30 + i * 20}">{"Setup (WNS)" if k == "wns_ns" else "Hold (WHS)"}: '
                       f'{_x(fmt(m.get("value")))} ns</text>')
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
    try:
        h = fill(h, ddir, build_id=build_id)
    except ValueError as ex:
        raise SystemExit(f"{rel(ddir)}: {ex}")
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
