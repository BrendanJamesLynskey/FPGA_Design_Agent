#!/usr/bin/env python3
"""Formal rigour (brief 143c): is a SymbiYosys proof worth what it says?

A green ``sby`` task says only that no assertion fails. It does not say that the assertions ever had something to check
(a ``if (req) assert (...)`` whose ``req`` can never be true passes for ever), that the assumptions left the design able to
do anything (an over-constrained harness proves everything), or why a bounded depth N was enough. This tool checks the three,
per assertion, and turns the answer into one status each:

  proved            the assertion holds in a passing ``prove`` task (k-induction: every depth), its antecedent is reachable
  bounded           it holds to depth N in ``bmc`` tasks only; ``justified`` says whether a written argument for N exists
  vacuous           the assertion cannot be shown non-vacuous: no antecedent cover is paired with it (burden of proof is on
                    the harness), or it contains a constant-true term (``|| 1'b1``)
  unreachable-cover the antecedent cover is paired but no cover task reaches it, or (for a bounded result) it is first reached at a step the
                    bmc task does not get to: within the bound the assertion never fires
  failed / not-run  a task reports the assertion failing / no passing task contains it

Pairing. An assertion ``LABEL`` is paired with the cover ``LABEL__ante`` unless the sidecar maps it elsewhere; the cover is the
assertion's guard (the ``if`` condition or the left side of the implication). An unconditional assertion's guard is the state
in which the harness checks it (after reset), so its pairing proves the harness is not over-constrained at that point.

Sidecar ``<job>.rigour.yaml`` beside ``<job>.sby``:

    schema: fpga-design-agent/formal_rigour/v1
    scope: "what instance is proven (parameters, abstractions)"       # optional, shown in the report
    antecedents: {"A_DB_*": C_DB_ANTE, p1_no_overflow: c_wr}          # label or fnmatch glob -> cover label (default LABEL__ante)
    sanity: [C_DB_PRESS]                                               # covers showing the main states are reachable under every assumption
    depth:                                                             # one entry per bmc task
      bmc: {enough: true|false, why: "pipeline depth, counter period, ... or why it is not enough"}
    unclaimed: {progress_prove: "why a task that does not pass is kept and not relied on"}   # optional; recorded, excluded from the verdict

Workflow: ``run`` executes every task of an .sby (``sby`` from the OSS CAD Suite), reads the elaborated checks from the
model (``model/design.il``) and the reached / unreached covers from the log, and writes a JSON record (with the hash of every
source file). ``judge`` is pure: record + current sidecar + current files -> per-assertion statuses and a verdict. A record
whose sources changed is stale and does not count. ``flow/trace_v1.py`` calls :func:`apply_to_item` so that a formal item with
a ``rigour:`` field cannot be ``pass`` unless every assertion is proved (see its docstring).

    python -m flow.formal_rigour run designs/t1_dimmer_counter/verif/formal/debounce.sby      # -> results/143c/formal_rigour/<slug>.json
    python -m flow.formal_rigour check designs/t1_dimmer_counter/verif/formal/debounce.sby    # judge the committed record
    python -m flow.formal_rigour audit                                                        # every tracked .sby: sidecar, record, verdict
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "fpga-design-agent/formal_rigour/v1"
RECORD_DIR = "results/143c/formal_rigour"
EXCLUDE = ("flow/tests/fixtures/", "runs/")          # test fixtures and old agent runs are not shipped proofs
TAUTOLOGY = re.compile(r"\|\|\s*1'b1|1'b1\s*\|\||assert\s*\(\s*(?:1'b1|1)\s*\)")


# ---- the .sby file ------------------------------------------------------------------------------------------------
def sby_section(text: str, name: str) -> list[str]:
    m = re.search(rf"^\[{name}\]\s*\n(.*?)(?=^\[|\Z)", text, re.M | re.S)
    return [l for l in (m.group(1).splitlines() if m else []) if l.strip() and not l.strip().startswith("#")]


def parse_sby(path: Path) -> dict[str, Any]:
    """Tasks with their mode and depth, and the source files ([files], resolved against the .sby's folder)."""
    text = path.read_text()
    tasks = {l.split(":")[0].split()[0]: set(l.split(":")[0].split()[1:]) | {l.split(":")[0].split()[0]}
             for l in sby_section(text, "tasks")}
    if not tasks:
        tasks = {"": {""}}
    opts = sby_section(text, "options")
    out: dict[str, dict[str, Any]] = {}
    for t, groups in tasks.items():
        mode, depth = None, None
        for l in opts:
            m = re.match(r"(?:(\w+):\s*)?(mode|depth)\s+(\S+)", l.strip())
            if not m or (m.group(1) and m.group(1) not in groups):
                continue
            if m.group(2) == "mode":
                mode = m.group(3)
            else:
                depth = int(m.group(3))
        out[t] = {"mode": mode, "depth": depth}
    files = []
    for l in sby_section(text, "files"):
        parts = l.split()
        files.append(parts[-1])           # "dst src" or "src"
    return {"tasks": out, "files": [(path.parent / f).resolve() for f in files]}


def rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "absent"


def sidecar_path(sby: Path) -> Path:
    return sby.with_suffix(".rigour.yaml")


def slug(sby: Path) -> str:
    return rel(sby).removesuffix(".sby").replace("/", "__")


def record_path(sby: Path) -> Path:
    return ROOT / RECORD_DIR / f"{slug(sby)}.json"


def sources(sby: Path) -> dict[str, str]:
    """Hash of everything a result depends on: the .sby, its sidecar's *harness-relevant* inputs (not the sidecar: it is judged live) and every [files] source."""
    d = {rel(sby): sha(sby)}
    for f in parse_sby(sby)["files"]:
        d[rel(f)] = sha(f)
    return d


# ---- reading a finished sby work directory -----------------------------------------------------------------------------
def short_src(src: str) -> str:
    """``a.sv:12.3-12.40`` -> ``a.sv:12`` (the first location of a ``|``-joined list)."""
    m = re.match(r"([^|:]+):(\d+)", src.split("|")[0])
    return f"{m.group(1)}:{m.group(2)}" if m else src


def read_checks(il: Path, srcdir: Path) -> list[dict[str, Any]]:
    """Every assertion, assumption and cover of the elaborated design: label (None if unnamed), flavor, source line, and a
    constant-true flag from the statement's own text."""
    out: list[dict[str, Any]] = []
    if not il.exists():
        return out
    lines = il.read_text(errors="replace").splitlines()
    src = None
    i = 0
    while i < len(lines):
        l = lines[i].strip()
        m = re.match(r'attribute \\src "([^"]+)"', l)
        if m:
            src = m.group(1)
        m = re.match(r"cell (\$check|\$assert|\$assume|\$cover) (\S+)(?:\s+#\s+(\S+))?", l)
        if m:
            kind, cname, comment = m.groups()
            flavor = {"$assert": "assert", "$assume": "assume", "$cover": "cover"}.get(kind)
            j = i + 1
            while j < len(lines) and lines[j].strip() != "end":
                fm = re.match(r'parameter \\FLAVOR "(\w+)"', lines[j].strip())
                if fm:
                    flavor = fm.group(1)
                j += 1
            label = None
            for cand in (comment, cname):
                if cand and cand.startswith("\\") and not cand.startswith("\\$") and not cand.startswith("\\_witness_."):
                    label = cand[1:].split(".")[-1]       # last component of a generate-scope path; `rename -witness` names an unlabelled statement `_witness_.check_<file>_<line>_assert_<n>`: not a label
                    break
            if flavor in ("assert", "assume", "cover") and src:
                ss = short_src(src)
                taut = False
                if flavor == "assert":
                    taut = bool(TAUTOLOGY.search(statement_text(srcdir, src)))
                out.append({"flavor": flavor, "label": label, "src": ss, "id": label or ss, "tautology": taut})
            i = j
        i += 1
    seen, uniq = set(), []
    for c in out:
        k = (c["flavor"], c["id"], c["src"])
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    return uniq


def statement_text(srcdir: Path, src: str) -> str:
    m = re.match(r"([^|:]+):(\d+)\.(\d+)-(\d+)\.(\d+)", src.split("|")[0])
    if not m:
        return ""
    f = srcdir / Path(m.group(1)).name
    if not f.exists():
        return ""
    l1, c1, l2, c2 = (int(x) for x in m.groups()[1:])
    ls = f.read_text(errors="replace").splitlines()
    seg = ls[l1 - 1:l2]
    if not seg:
        return ""
    if l1 == l2:
        return seg[0][c1 - 1:c2 - 1]
    seg[0] = seg[0][c1 - 1:]
    seg[-1] = seg[-1][:c2 - 1]
    return " ".join(seg)


COVER_RE = re.compile(r"(Reached cover statement in step (\d+) at|Unreached cover statement at) ([^:\s]+): (\S+)(?: \((\S+)\))?")


def read_covers(log: str) -> dict[str, dict[str, Any]]:
    """Covers named in a cover task's log, by label (or file:line): reached (step) or not."""
    out: dict[str, dict[str, Any]] = {}
    for m in COVER_RE.finditer(log):
        what, step, _hier, name, src = m.groups()
        label = name.split(".")[-1]
        keys = []
        if not label.startswith(("check_", "$")) and ":" not in label:
            keys.append(label)
        for cand in (src, name):
            if cand and re.match(r"[^|:]+:\d+", cand):
                keys.append(short_src(cand))
        for k in keys or [name]:
            if what.startswith("Reached"):
                out[k] = {"reached": True, "step": int(step)}
            else:
                out.setdefault(k, {"reached": False, "step": None})
    return out


def pinned_oss_cad() -> str:
    """The bin folder of the OSS CAD Suite the repo pins (FDA_OSS_CAD, then ~/.local/opt/oss-cad-suite), or "". Only that release writes the model and log
    formats this module reads ($check cells, `rename -witness`); the distribution's older yosys does not."""
    for c in (os.environ.get("FDA_OSS_CAD"), str(Path.home() / ".local/opt/oss-cad-suite")):
        if c and (Path(c) / "bin" / "sby").exists():
            return str(Path(c) / "bin")
    return ""


def oss_bin() -> str:
    return pinned_oss_cad()


def run_task(sby: Path, task: str, work: Path, bindir: str, timeout: int = 4 * 3600) -> dict[str, Any]:
    """One sby task in its own work directory; returns status, seconds, the checks of its model and the covers its log names."""
    shutil.rmtree(work, ignore_errors=True)
    env = dict(os.environ, PATH=(bindir + ":" if bindir else "") + os.environ.get("PATH", ""))
    cmd = ["sby", "-f", "-d", str(work), sby.name] + ([task] if task else [])
    if shutil.which("systemd-run"):
        cmd = ["systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=6G", "nice", "-n", "10"] + cmd
    t0 = time.time()
    r = subprocess.run(cmd, cwd=sby.parent, env=env, capture_output=True, text=True, timeout=timeout)
    dt = time.time() - t0
    st_file = work / "status"
    status = st_file.read_text().split()[0] if st_file.exists() else "ABSENT"
    logf = work / "logfile.txt"
    log = logf.read_text(errors="replace") if logf.exists() else r.stdout + r.stderr
    checks = read_checks(work / "model" / "design.il", work / "src")
    res = {"status": status, "seconds": round(dt, 1), "checks": checks,
           "covers": read_covers(log) if any(c["flavor"] == "cover" for c in checks) else {}}
    failed = re.findall(r"Assert failed in \S+: (\S+)", log)
    if failed:
        res["failed_asserts"] = sorted({f.split(".")[-1] if not re.match(r".*:\d+", f) else short_src(f) for f in failed})
    return res


def tool_version(bindir: str) -> str:
    try:
        env = dict(os.environ, PATH=(bindir + ":" if bindir else "") + os.environ.get("PATH", ""))
        return subprocess.run(["yosys", "-V"], capture_output=True, text=True, env=env).stdout.strip()
    except OSError:
        return "unknown"


def run(sby: Path, tasks: list[str] | None = None, work_root: Path | None = None, bindir: str | None = None) -> dict[str, Any]:
    sby = sby.resolve()
    info = parse_sby(sby)
    bindir = oss_bin() if bindir is None else bindir
    if not bindir:
        raise RuntimeError("the pinned OSS CAD Suite (release 2026-11-12) was not found: set FDA_OSS_CAD to its folder or install it under ~/.local/opt/oss-cad-suite")
    root = work_root or Path(tempfile.mkdtemp(prefix="rigour_"))
    rec: dict[str, Any] = {"schema": SCHEMA, "sby": rel(sby), "tasks": {}, "sources": sources(sby), "tool": tool_version(bindir)}
    for t, meta in info["tasks"].items():
        if tasks and t not in tasks:
            continue
        r = run_task(sby, t, root / (t or "default"), bindir)
        rec["tasks"][t] = {**meta, **r}
    return rec


# ---- judging -----------------------------------------------------------------------------------------------------------
def load_sidecar(sby: Path) -> dict[str, Any] | None:
    p = sidecar_path(sby)
    if not p.exists():
        return None
    d = yaml.safe_load(p.read_text()) or {}
    return d if isinstance(d, dict) else None


def antecedent_label(label: str, side: dict[str, Any]) -> str:
    amap = side.get("antecedents") or {}
    if label in amap:
        return str(amap[label])
    for pat, cov in amap.items():
        if any(ch in pat for ch in "*?[") and fnmatch.fnmatch(label, pat):
            return str(cov)
    return f"{label}__ante"


def judge(rec: dict[str, Any], sby: Path | None = None, side: dict[str, Any] | None = None) -> dict[str, Any]:
    """Per-assertion statuses and one verdict (pass / bounded / fail) from a record, the current sidecar and the current files."""
    sby = sby or ROOT / rec["sby"]
    side = side if side is not None else load_sidecar(sby)
    reasons: list[str] = []
    res: dict[str, Any] = {"sby": rec["sby"], "assertions": [], "reasons": reasons, "scope": (side or {}).get("scope", ""),
                           "unclaimed": {t: rec["tasks"][t]["status"] for t in ((side or {}).get("unclaimed") or {}) if t in rec["tasks"]}}
    if side is None:
        reasons.append(f"no sidecar {rel(sidecar_path(sby))}: no pairing, sanity cover or depth justification written")
        side = {}
    cur = sources(sby) if sby.exists() else {}
    stale = sorted(k for k, h in (rec.get("sources") or {}).items() if cur.get(k, "absent") != h)
    if stale:
        reasons.append("record is stale (re-run `python -m flow.formal_rigour run`): changed since it was recorded: " + ", ".join(stale[:4]))
    unclaimed = side.get("unclaimed") or {}          # task -> why it is run but its result is not relied on (e.g. an induction step with open counterexamples)
    tasks = {t: v for t, v in rec["tasks"].items() if t not in unclaimed or not str(unclaimed[t]).strip()}
    for t in unclaimed:
        if t not in rec["tasks"]:
            reasons.append(f"sidecar names unclaimed task {t!r} that the record does not have")
    bad = [f"{t or 'default'}={v['status']}" for t, v in tasks.items() if v["status"] != "PASS"]
    if bad:
        reasons.append("task not passing: " + ", ".join(bad))
    proof_tasks = {t: v for t, v in tasks.items() if v["mode"] in ("prove", "bmc")}
    cover_tasks = {t: v for t, v in tasks.items() if v["mode"] == "cover"}
    if not cover_tasks:
        reasons.append("no cover task: nothing shows any antecedent or the assumptions' sanity is reachable")
    reached: dict[str, int] = {}
    present_cover: set[str] = set()
    for v in cover_tasks.values():
        for c in v["checks"]:
            if c["flavor"] == "cover":
                present_cover.add(c["id"])
        for k, cv in v["covers"].items():
            if cv["reached"]:
                reached[k] = cv["step"]
    n_assume = sum(1 for v in proof_tasks.values() for c in v["checks"] if c["flavor"] == "assume")
    res["assumptions"] = len({(c["id"]) for v in tasks.values() for c in v["checks"] if c["flavor"] == "assume"})
    sanity = [str(s) for s in (side.get("sanity") or [])]
    res["sanity"] = {s: reached.get(s) for s in sanity}
    if not sanity:
        reasons.append("no assumption-sanity cover listed (`sanity:` in the sidecar)")
    for s in sanity:
        if s not in present_cover:
            reasons.append(f"sanity cover {s} is not in any cover task")
        elif s not in reached:
            reasons.append(f"sanity cover {s} is unreachable: the assumptions leave the design unable to reach its main state")
    depth_side = side.get("depth") or {}
    ids: dict[str, dict[str, Any]] = {}
    for t, v in proof_tasks.items():
        for c in v["checks"]:
            if c["flavor"] != "assert":
                continue
            a = ids.setdefault(c["id"], {"id": c["id"], "label": c["label"], "src": c["src"], "tautology": c["tautology"], "tasks": {}})
            a["tasks"][t] = v
    for a in sorted(ids.values(), key=lambda x: x["src"]):
        cov = antecedent_label(a["label"], side) if a["label"] else None
        st, why = None, ""
        failed = [t for t, v in a["tasks"].items() if a["id"] in (v.get("failed_asserts") or [])]
        if failed:
            st, why = "failed", "fails in " + ", ".join(failed)
        elif a["tautology"]:
            st, why = "vacuous", "contains a constant-true term: it can never fail"
        elif cov is None:
            st, why = "vacuous", "unlabelled assertion: no antecedent cover can be paired"
        elif cov not in present_cover:
            st, why = "vacuous", f"no antecedent cover {cov}: non-vacuity not shown"
        elif cov not in reached:
            st, why = "unreachable-cover", f"antecedent cover {cov} is not reached in any cover task"
        else:
            passed = {t: v for t, v in a["tasks"].items() if v["status"] == "PASS"}
            prove = [t for t, v in passed.items() if v["mode"] == "prove"]
            if prove:
                st, why = "proved", f"k-induction in {', '.join(prove)}; antecedent {cov} reached at step {reached[cov]}"
            elif passed:
                t = max(passed, key=lambda x: passed[x]["depth"] or 0)
                n = passed[t]["depth"]
                j = depth_side.get(t) or {}
                justified = bool(str(j.get("why", "")).strip()) and isinstance(j.get("enough"), bool)
                if n is not None and reached[cov] >= n:
                    # a bmc of depth n checks steps 0..n-1: an antecedent that first holds at step >= n never lets the assertion fire in the bound
                    st = "unreachable-cover"
                    why = f"antecedent cover {cov} is first reached at step {reached[cov]} but {t} stops at depth {n}: within the bound the assertion never fires"
                else:
                    st = "bounded"
                    why = f"bmc to depth {n} ({t}); antecedent {cov} reached at step {reached[cov]}; " + (
                        f"justified ({'enough' if j['enough'] else 'NOT enough'}): {str(j['why']).strip()[:160]}" if justified else "no written depth justification")
                    a["bound"], a["justified"], a["enough"] = n, justified, j.get("enough") if justified else None
            else:
                st, why = "not-run", "no passing proof task contains it"
        a.update(status=st, detail=why, antecedent=cov)
        a.pop("tasks")
        res["assertions"].append(a)
    bm = [a for a in res["assertions"] if a["status"] == "bounded"]
    for t, v in proof_tasks.items():
        if v["mode"] == "bmc" and not (depth_side.get(t) or {}).get("why"):
            reasons.append(f"bmc task {t} (depth {v['depth']}) has no written depth justification")
    summ = {k: sum(1 for a in res["assertions"] if a["status"] == k) for k in ("proved", "bounded", "vacuous", "unreachable-cover", "failed", "not-run")}
    summ["bounded_unjustified"] = sum(1 for a in bm if not a.get("justified"))
    res["summary"] = {**summ, "assertions": len(res["assertions"])}
    for k in ("vacuous", "unreachable-cover", "failed", "not-run"):
        if summ[k]:
            reasons.append(f"{summ[k]} assertion(s) {k}: " + ", ".join(a["id"] for a in res["assertions"] if a["status"] == k)[:200])
    if summ["bounded_unjustified"]:
        reasons.append(f"{summ['bounded_unjustified']} bounded assertion(s) without a written depth justification")
    if not res["assertions"]:
        reasons.append("no assertions found in any proof task")
    if reasons:
        res["verdict"] = "fail"
    else:
        res["verdict"] = "bounded" if bm else "pass"
    res["n_assume"] = n_assume
    return res


def judge_job(sby: Path) -> dict[str, Any]:
    """Judge the committed record of a .sby (a missing record is a failed verdict)."""
    rp = record_path(sby)
    if not rp.exists():
        return {"sby": rel(sby), "verdict": "fail", "assertions": [], "summary": {}, "reasons": [f"no record {rel(rp)}: run `python -m flow.formal_rigour run {rel(sby)}`"]}
    return judge(json.loads(rp.read_text()), sby)


# ---- trace_v1 hook -------------------------------------------------------------------------------------------------------
def apply_to_item(item: dict, res: dict) -> None:
    """For a trace_v1 formal item with ``rigour: [path/to/job.sby, ...]``: a pass becomes ``fail`` unless every assertion of every
    job is proved with its antecedent reached; a justified bounded result becomes ``bounded``. Items without the field are untouched."""
    rg = item.get("rigour")
    if not rg or res.get("status") not in ("pass", "bounded"):
        return
    jobs = [rg] if isinstance(rg, str) else list(rg)
    verdicts = [judge_job(ROOT / j) for j in jobs]
    res["rigour"] = [{"sby": v["sby"], "verdict": v["verdict"], "summary": v.get("summary", {}), "reasons": v["reasons"][:4]} for v in verdicts]
    if any(v["verdict"] == "fail" for v in verdicts):
        why = "; ".join(f"{v['sby']}: {v['reasons'][0]}" for v in verdicts if v["verdict"] == "fail")
        res["status"] = "fail"
        res["detail"] = f"formal rigour: {why[:300]} (was: {res.get('detail', '')[:80]})"
    elif any(v["verdict"] == "bounded" for v in verdicts):
        res["status"] = "bounded"
        res["detail"] = (res.get("detail", "") + "; formal rigour: some assertions bounded with a written depth justification").lstrip("; ")
    else:
        res["detail"] = (res.get("detail", "") + f"; formal rigour: {sum(v['summary']['proved'] for v in verdicts)} assertion(s) proved, antecedents reached").lstrip("; ")


# ---- tracked jobs and CLI --------------------------------------------------------------------------------------------------
def tracked_sby() -> list[Path]:
    r = subprocess.run(["git", "-C", str(ROOT), "ls-files", "*.sby"], capture_output=True, text=True)
    return [ROOT / p for p in r.stdout.split() if not p.startswith(EXCLUDE)]


def table(v: dict) -> str:
    out = [f"{v['sby']}: {v['verdict']}  {v.get('summary', {})}"]
    for a in v["assertions"]:
        out.append(f"  {a['status']:<17} {a['id']:<44} {a['detail'][:110]}")
    out += [f"  ! {r}" for r in v["reasons"]]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run every task of a .sby and write its record")
    r.add_argument("sby", nargs="+")
    r.add_argument("--tasks", help="comma list (default: all)")
    r.add_argument("--work", help="keep the sby work directories here")
    c = sub.add_parser("check", help="judge the committed record of a .sby")
    c.add_argument("sby", nargs="+")
    c.add_argument("--json", action="store_true")
    sub.add_parser("audit", help="every tracked .sby: sidecar, record and verdict")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        for s in a.sby:
            p = Path(s).resolve()
            rec = run(p, a.tasks.split(",") if a.tasks else None, Path(a.work) / slug(p) if a.work else None)
            rp = record_path(p)
            rp.parent.mkdir(parents=True, exist_ok=True)
            rp.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
            print(table(judge(rec, p)))
        return 0
    if a.cmd == "check":
        bad = 0
        for s in a.sby:
            v = judge_job(Path(s).resolve())
            print(json.dumps(v, indent=1) if a.json else table(v))
            bad += v["verdict"] == "fail"
        return 1 if bad else 0
    bad = 0
    for p in tracked_sby():
        v = judge_job(p)
        s = v.get("summary", {})
        print(f"{v['verdict']:<8} {rel(p):<62} assertions {s.get('assertions', '-')}, proved {s.get('proved', '-')}, bounded {s.get('bounded', '-')}, vacuous {s.get('vacuous', '-')}, unreachable {s.get('unreachable-cover', '-')}")
        bad += v["verdict"] == "fail"
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
