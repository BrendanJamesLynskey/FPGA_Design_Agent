#!/usr/bin/env python3
"""The documentation checker (brief 68): every design, ip_lib entry and results folder meets
docs/documentation_standard.md.

    python3 flow/doccheck.py --check        # exit 1 on any problem (CI runs this)
    python3 flow/doccheck.py --coverage     # the coverage table (markdown), no exit status
    python3 flow/doccheck.py --write        # re-render every design's README.md, AGENT.md and SVGs from handover.yaml

What it checks, by kind:
- designs/<d>/: handover.yaml, README.md and AGENT.md exist and pass flow/handover.py's checks (schema, no
  placeholders, values equal their records, gaps for every non-pass, renderings current, prose numbers traceable).
  Stale record hashes are printed as warnings, not failures (`--strict` fails on them too).
- ip_lib/<entry>/: README.md equals flow/net/ipdoc.py's rendering, and has the IP template's sections, each with
  content.
- results/**/<d>/handover.yaml (brief 68 C: a design an agent run produced, kept as a record): the same checks as
  designs/<d>/, and an agent run's measurements cite only the run's own records (flow.handover.in_run_records).
- results/<folder>/: README.md with a lead paragraph and the results template's sections (Records, Reproduce,
  Known gaps and limits), each with content and no placeholder; every number in an optional "Measured" section
  appears in a file of that folder. Pure-data folders are listed, each with a reason, in docs/doccheck_allow.yaml.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from flow import handover as H  # noqa: E402

ALLOW = ROOT / "docs" / "doccheck_allow.yaml"
IP_SECTIONS = ["Parameters", "Interfaces", "Latency and throughput", "Evidence", "Boundary and reuse",
               "Known gaps and limits", "Next steps", "History"]
RESULTS_SECTIONS = [("Records", ("Records", "Files")), ("Reproduce", ("Reproduce",)),
                    ("Known gaps and limits", ("Known gaps and limits",))]
MIN_SECTION_WORDS = 5
MIN_LEAD_WORDS = 15


def designs() -> list[Path]:
    return sorted(p for p in (ROOT / "designs").iterdir() if p.is_dir() and not p.name.startswith(("_", ".")))


def ip_entries() -> list[Path]:
    return sorted(p.parent for p in (ROOT / "ip_lib").glob("*/ip.yaml"))


def results_folders() -> list[Path]:
    return sorted(p for p in (ROOT / "results").iterdir() if p.is_dir() and not p.name.startswith(("_", ".")))


def agent_designs() -> list[Path]:
    """Designs produced by agent runs and kept under results/ (each with its handover.yaml)."""
    return sorted(p.parent for p in (ROOT / "results").rglob("handover.yaml"))


def allow_list() -> dict:
    y = yaml.safe_load(ALLOW.read_text()) if ALLOW.exists() else {}
    return {k: v for k, v in (y or {}).get("allow", {}).items()}


def sections(md: str) -> tuple[str, dict]:
    """(lead text before the first '## ', {heading: body}) with HTML comments removed."""
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    md = re.sub(r"(?ms)^(```|~~~).*?^\1[^\n]*$", "", md)          # headings inside a fenced block are not sections
    parts = re.split(r"(?m)^## +(.+?)\s*$", md)
    lead = re.sub(r"(?m)^# .*$", "", parts[0])
    out = {}
    for i in range(1, len(parts), 2):
        k = parts[i].strip()
        out[k + " (repeated)" if k in out else k] = parts[i + 1]
    return lead, out


def _content_problem(body: str) -> str | None:
    lines = [l for l in body.strip().splitlines() if l.strip() and not re.fullmatch(r"\s*[|:\- ]+\s*", l)]
    text = H.visible(" ".join(lines))
    if H.meaningful(text) < MIN_SECTION_WORDS:
        return "empty, too short or filler (fewer than 5 distinct meaningful words)"
    if all(H.PLACEHOLDER.search(re.sub(r"^[-*\d.\s]+", "", l)) for l in lines):
        return "placeholder only"
    if re.search(r"\b(TODO|TBD|FIXME|lorem ipsum)\b", text):
        return "contains a placeholder (TODO/TBD/FIXME)"
    return None


def check_design(d: Path) -> tuple[list[str], list[str]]:
    miss = [f for f in ("handover.yaml", "README.md", "AGENT.md") if not (d / f).exists()]
    if miss:
        return [f"missing {', '.join(miss)}"], []
    errs, stale = H.problems(d)
    from agent.graph.document import recheck          # brief 68 C: an agent's handover is re-derived from its run's records
    return errs + recheck(d), stale


def check_ip(d: Path) -> list[str]:
    from flow.net import ipdoc
    p = d / "README.md"
    if not p.exists():
        return ["missing README.md"]
    errs = []
    if d.name in ipdoc.ALL and p.read_text() != ipdoc.readme(d.name):
        errs.append("README.md is not current (run: python3 flow/net/ipdoc.py)")
    _, secs = sections(p.read_text())
    if "## History" in p.read_text() and not re.search(r"(?m)^- \S.*\d", sections(p.read_text())[1].get("History", "")):
        errs.append("'## History': no version entry (add a '## <version> (<date>)' entry to CHANGELOG.md)")
    for s in IP_SECTIONS:
        if s not in secs:
            errs.append(f"README.md has no '## {s}' section")
        elif (why := _content_problem(secs[s])):
            errs.append(f"'## {s}': {why}")
    if d.name not in ipdoc.ALL:
        errs.append("not listed in flow/net/ipdoc.py (so its README is not generated)")
    return errs


def _folder_tokens(d: Path) -> set:
    toks = set()
    for f in d.rglob("*"):
        if f.is_file() and f.name != "README.md" and f.stat().st_size < 8_000_000:
            try:
                toks |= H._tokens_of_text(f.read_text(errors="replace"))
            except OSError:
                pass
    return toks


def check_results(d: Path) -> list[str]:
    p = d / "README.md"
    if not p.exists():
        return ["missing README.md (or list the folder in docs/doccheck_allow.yaml with a reason)"]
    lead, secs = sections(p.read_text())
    errs = []
    if any(k.endswith(" (repeated)") for k in secs):
        errs.append("README.md repeats a '## ' heading")
    if H.meaningful(lead) < MIN_LEAD_WORDS:
        errs.append(f"README.md needs a lead paragraph of at least {MIN_LEAD_WORDS} words saying what the folder is")
    for name, alts in RESULTS_SECTIONS:
        hit = next((a for a in alts if a in secs), None)
        if not hit:
            errs.append(f"README.md has no '## {name}' section")
        elif (why := _content_problem(secs[hit])):
            errs.append(f"'## {hit}': {why}")
    toks = None
    for k, body in secs.items():
        if k.startswith("Measured"):
            toks = toks if toks is not None else _folder_tokens(d)
            for w in H.unvouched(body, toks):
                errs.append(f"'## {k}': number {w} is in no file of {d.name}/")
    return errs


def run(strict: bool = False) -> tuple[list[str], list[str], dict]:
    errs, warns, cov = [], [], {}
    allow = allow_list()
    for k in allow:
        if not re.fullmatch(r"results/[\w.-]+", k) or list((ROOT / k).glob("*.md")):
            errs.append(f"docs/doccheck_allow.yaml: {k}: only a results folder of pure data (no .md) may be allow-listed")
        elif not (ROOT / k).is_dir():
            errs.append(f"docs/doccheck_allow.yaml: {k} is not a directory")
        elif not isinstance(allow[k], str) or H._words(allow[k]) < 4:
            errs.append(f"docs/doccheck_allow.yaml: {k} needs a reason")
    rows = {"designs": designs(), "agent runs": agent_designs(), "ip_lib": ip_entries(), "results": results_folders()}
    for kind, dirs in rows.items():
        ok = readme = allowed = 0
        for d in dirs:
            r = str(d.relative_to(ROOT))
            if r in allow:
                allowed += 1
                continue
            readme += (d / "README.md").exists()
            if kind in ("designs", "agent runs"):
                e, s = check_design(d)
            elif kind == "ip_lib":
                e, s = check_ip(d), []
            else:
                e, s = check_results(d), []
            errs += [f"{r}: {x}" for x in e]
            warns += [f"{r}: stale: {x}" for x in s]
            ok += not e and not (strict and s)
        cov[kind] = {"total": len(dirs), "readme": readme, "standard": ok, "allow_listed": allowed}
    if strict:
        errs += warns
    return errs, warns, cov


def coverage_table(cov: dict) -> str:
    L = ["| Kind | Folders | With README | Meet the standard | Allow-listed (pure data) |", "|---|---|---|---|---|"]
    L += [f"| {k} | {v['total']} | {v['readme']} | {v['standard']} | {v['allow_listed']} |" for k, v in cov.items()]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    a = argv if argv is not None else sys.argv[1:]
    if "--write" in a:
        for d in designs() + agent_designs():
            if (d / "handover.yaml").exists():
                print(str(d.relative_to(ROOT)) + ":", ", ".join(H.write(d)))
        return 0
    errs, warns, cov = run(strict="--strict" in a)
    if "--coverage" in a:
        print(coverage_table(cov))
        return 0
    for w in warns:
        print("warning:", w)
    for e in errs:
        print(e)
    print(f"doccheck: {len(errs)} problems, {len(warns)} stale claims")
    print(coverage_table(cov))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
