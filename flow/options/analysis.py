"""The read-only analysis of a loaded design (brief 104): what the agent knows before it proposes a way to improve it.

``analyse`` reads files that already exist (a design's ``project.yaml``, ``latency_stages.yaml`` and its recorded clocks, a
build's timing, utilisation-by-hierarchy and CDC reports) and returns one dictionary: the components with their ownership, the
latency budget by stage, the timing picture (WNS, WHS, the worst path and the component it is in), resources per component, the
clock crossings, and a list of **facts**. Every fact has a stable id, a value, and the file and locator it came from; the options
generator may cite only fact ids, so every number it states traces to a file (``schema.check_options``).

Nothing is edited, simulated or built here. When a report is missing, the analysis says so in ``gaps`` and offers to build; it never
starts Vivado. Components that are ``excluded`` in the manifest are not in the analysis at all (their rows, stages and paths are
dropped), as in the agent's other tools (brief 102).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from agent.core import managed
from flow.latency import model as lm

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "fda-analysis/1"
#: files the analysis looks for in a build directory (relative to it)
BUILD_FILES = {"util_hier": "utilization_hier.rpt", "timing_summary": "timing_summary.rpt", "worst_setup": "timing_worst_setup.rpt",
               "cdc": "cdc_summary.rpt", "run": "run.json"}
#: the 62 closure loop's start digest (one JSON with timing, utilisation, power and the worst setup path)
DIGEST_FILES = ("digest.json", "start_digest.json")


def _rel(p: Path, base: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(base.resolve()))
    except ValueError:
        return str(p)


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class Facts:
    """The ids the generator may cite. ``add`` returns the id; a fact is {value, unit, text, file, locator, origin}."""

    def __init__(self, base: Path):
        self.base = base
        self.items: dict[str, dict[str, Any]] = {}
        self.files: dict[str, dict[str, Any]] = {}

    def source(self, path: Path) -> str:
        rel = _rel(path, self.base)
        if rel not in self.files:
            self.files[rel] = {"file": rel, "sha256": _sha(path), "bytes": Path(path).stat().st_size}
        return rel

    def add(self, fid: str, value: Any, unit: str, text: str, path: Path, locator: str, origin: str) -> str:
        self.items[fid] = {"id": fid, "value": value, "unit": unit, "text": text, "file": self.source(path), "locator": locator, "origin": origin}
        return fid


# --- parsers ------------------------------------------------------------------------------------------------------

def parse_util_hier(text: str) -> list[dict[str, Any]]:
    """Rows of ``report_utilization -hierarchical``: path (without the top's name), module, and the counts. Rows in parentheses
    (a module's own logic) are skipped; a parent's counts include its children's."""
    rows: list[dict[str, Any]] = []
    head: list[str] | None = None
    stack: list[tuple[int, str]] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c for c in line.split("|")[1:-1]]
        if head is None:
            if cells and cells[0].strip() == "Instance":
                head = [c.strip() for c in cells]
            continue
        if len(cells) != len(head):
            continue
        raw = cells[0]
        name = raw.strip()
        depth = (len(raw) - len(raw.lstrip(" "))) // 2
        if name.startswith("("):
            continue
        while stack and stack[-1][0] >= depth:
            stack.pop()
        stack.append((depth, name))
        rec = dict(zip(head, [c.strip() for c in cells]))

        def num(k: str) -> int | None:
            v = rec.get(k, "")
            try:
                return int(float(v))
            except ValueError:
                return None
        path = "/".join(n for _, n in stack[1:])
        rows.append({"path": path, "module": rec.get("Module", ""), "lut": num("Total LUTs"), "ff": num("FFs"), "ramb36": num("RAMB36"),
                     "ramb18": num("RAMB18"), "uram": num("URAM"), "dsp": num("DSP Blocks"), "depth": depth})
    return rows


def parse_timing_summary(text: str) -> dict[str, Any] | None:
    m = re.search(r"WNS\(ns\).*?\n\s*-+.*?\n\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\s+(\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\s+(\d+)", text, re.S)
    if not m:
        return None
    return {"wns_ns": float(m[1]), "tns_ns": float(m[2]), "failing_endpoints": int(m[3]), "whs_ns": float(m[5]), "hold_failing_endpoints": int(m[7])}


def parse_clocks(text: str) -> list[dict[str, Any]]:
    """The Clock Summary table of ``report_timing_summary``: name, period and frequency (generated clocks are indented)."""
    rows: list[dict[str, Any]] = []
    on = False
    for line in text.splitlines():
        if line.startswith("Clock") and "Period(ns)" in line:
            on = True
            continue
        if on:
            m = re.match(r"^\s*(\S+)\s+\{[^}]*\}\s+(-?[\d.]+)\s+(-?[\d.]+)", line)
            if m:
                rows.append({"name": m[1], "period_ns": float(m[2]), "freq_mhz": float(m[3])})
            elif line.strip() and not line.startswith("-----"):
                break
            elif not line.strip() and rows:
                break
    return rows


def parse_worst_path(text: str) -> dict[str, Any] | None:
    sl = re.search(r"Slack \((\w+)\)\s*:\s*(-?[\d.]+)ns", text)
    src = re.search(r"Source:\s+(\S+)", text)
    dst = re.search(r"Destination:\s+(\S+)", text)
    if not (sl and src and dst):
        return None
    out: dict[str, Any] = {"slack_ns": float(sl[2]), "met": sl[1] == "MET", "source": src[1], "destination": dst[1]}
    for key, pat in (("data_path_ns", r"Data Path Delay:\s+(-?[\d.]+)ns"), ("logic_levels", r"Logic Levels:\s+(\d+)"),
                     ("requirement_ns", r"Requirement:\s+(-?[\d.]+)ns")):
        m = re.search(pat, text)
        if m:
            out[key] = float(m[1]) if key != "logic_levels" else int(m[1])
    lv = re.search(r"Logic Levels:\s+\d+\s+\(([^)]*)\)", text)
    if lv:
        out["levels_by_type"] = {k: int(v) for k, v in (p.split("=") for p in lv[1].split() if "=" in p)}
    clk = re.search(r"clocked by (\S+)", text)
    if clk:
        out["clock"] = clk[1]
    return out


def parse_cdc_summary(text: str) -> list[dict[str, Any]]:
    rows = []
    for line in text.splitlines():
        if re.match(r"^(Critical|Warning|Info|Error)", line):
            p = re.split(r"\s{2,}", line.strip())
            if len(p) >= 10:
                rows.append({"severity": p[0], "source_clock": p[1], "dest_clock": p[2], "type": p[3], "exceptions": p[4],
                             "endpoints": int(p[5]), "safe": int(p[6]), "unsafe": int(p[7]), "unknown": int(p[8]), "no_async_reg": int(p[9])})
    return rows


# --- components ----------------------------------------------------------------------------------------------------

def _inst(c: managed.Component) -> str:
    return (c.instance or "").strip("/")


def component_of_path(project: managed.Project, hier: str) -> managed.Component | None:
    """The component whose instance is the longest prefix of a hierarchy path (cell names from the reports); the top (instance
    empty) owns what no deeper component claims."""
    h = hier.strip("/")
    best = None
    for c in project.components:
        i = _inst(c)
        if i and (h == i or h.startswith(i + "/")) and (best is None or len(i) > len(_inst(best))):
            best = c
    if best is None:
        best = next((c for c in project.components if not _inst(c) and c.module == project.top), None)
    return best


def stage_component(project: managed.Project, stage: dict[str, Any]) -> managed.Component | None:
    """The component a latency stage's registers live in, from its register patterns (``*u_rx/u_pr/blk_reg[*]``, ``*u_p_go/*``).
    A pattern's directory part is matched to a component instance; a name no component has as an instance is searched for in the
    component's own RTL (a crossing instantiated inside a wrapper belongs to the wrapper)."""
    names: list[str] = []
    for pat in stage.get("registers") or []:
        parts = [p for p in pat.lstrip("*").strip("/").split("/")[:-1] if p and "*" not in p]
        if parts:
            names.append("/".join(parts))
    hits: list[managed.Component] = []
    for n in names:
        for c in project.components:
            i = _inst(c)
            if i and (i == n or i.endswith("/" + n)):
                hits.append(c)
                break
        else:
            leaf = n.split("/")[-1]
            for c in project.components:
                for f in managed.component_files(project, c):
                    if f.suffix in (".sv", ".v", ".vhd") and re.search(rf"(?<![A-Za-z0-9_]){re.escape(leaf)}(?![A-Za-z0-9_])", f.read_text(errors="ignore")):
                        hits.append(c)
                        break
                else:
                    continue
                break
    if not hits:
        return None
    return max(hits, key=lambda c: (hits.count(c), len(_inst(c))))


# --- the analysis ---------------------------------------------------------------------------------------------------

def _first(*paths: Path) -> Path | None:
    return next((p for p in paths if p.is_file()), None)


def analyse(design: Path, *, build_dir: Path | None = None, base: Path | None = None, path: str | None = None) -> dict[str, Any]:
    """The analysis of ``design`` (a design directory, with or without ``project.yaml``). ``build_dir`` is where its reports are
    (default ``<design>/build/base``, else ``<design>/evidence``). ``base`` is what file names in facts are relative to (default the
    repository root). Read-only."""
    design = Path(design).resolve()
    base = Path(base).resolve() if base else ROOT
    facts = Facts(base)
    gaps: list[str] = []
    notes: list[str] = []
    try:
        project = managed.load(design)
    except ValueError as e:
        raise ValueError(f"{design.name}: {e}") from None
    if project is None:
        try:
            project = managed.Project(**{k: v for k, v in _converted(design).items()})
        except (OSError, KeyError, TypeError):
            project = None
        notes.append("no project.yaml: the whole design is one owned component, so only whole-design options are possible")
    if project is None:
        raise ValueError(f"{design}: neither a project.yaml nor a build.yaml to read")
    visible = [c for c in project.components if c.ownership != "excluded"]
    n_hidden = len(project.components) - len(visible)
    bdir = Path(build_dir) if build_dir else (_first_dir(design / "build" / "base", design / "evidence", design / "build"))
    if bdir is None:
        gaps.append("no build reports (build/base or evidence): timing, resources and clock crossings are unknown; the agent can offer to build, it does not build to analyse")
    comps = [{"name": c.name, "ownership": c.ownership, "level": c.level, "module": c.module, "instance": _inst(c) or "(top)",
              "aliases": list(c.aliases), "description": c.description, "files": [str(f.relative_to(design)) for f in managed.component_files(project, c)
                                                                                 if f.suffix in (".sv", ".v", ".vhd")][:12],
              "ports": len((c.interface or {}).get("ports") or []), "contract_declared": bool((c.interface or {}).get("ports")),
              "trust": managed.trust(project, c)[0]} for c in visible]
    out: dict[str, Any] = {"schema": SCHEMA, "design": project.name, "top": project.top, "components": comps, "notes": notes, "gaps": gaps,
                           "hidden_components": n_hidden, "latency": None, "timing": None, "resources": None, "cdc": None, "build": None}

    # build files
    files = {k: (bdir / v) if bdir else None for k, v in BUILD_FILES.items()}
    files = {k: v for k, v in files.items() if v is not None and v.is_file()}
    digest = _first(*[bdir / d for d in DIGEST_FILES]) if bdir else None

    # timing
    timing: dict[str, Any] = {}
    if "timing_summary" in files:
        t = parse_timing_summary(files["timing_summary"].read_text(errors="ignore"))
        if t:
            f = files["timing_summary"]
            timing.update(t)
            facts.add("timing.wns_ns", t["wns_ns"], "ns", "worst setup slack, routed", f, "Design Timing Summary: WNS(ns)", "post_route_report")
            facts.add("timing.whs_ns", t["whs_ns"], "ns", "worst hold slack, routed", f, "Design Timing Summary: WHS(ns)", "post_route_report")
            facts.add("timing.tns_ns", t["tns_ns"], "ns", "total negative setup slack", f, "Design Timing Summary: TNS(ns)", "post_route_report")
            facts.add("timing.failing_endpoints", t["failing_endpoints"], "endpoints", "setup-failing endpoints", f, "Design Timing Summary: TNS Failing Endpoints", "post_route_report")
    if "timing_summary" in files:
        cl = parse_clocks(files["timing_summary"].read_text(errors="ignore"))
        if cl:
            timing["clocks"] = cl
            for c in cl:
                facts.add(f"clock.{re.sub(r'[^A-Za-z0-9_]', '_', c['name'])}.period_ns", c["period_ns"], "ns", f"period of clock {c['name']} ({c['freq_mhz']} MHz)",
                          files["timing_summary"], "Clock Summary", "post_route_report")
    if "worst_setup" in files:
        w = parse_worst_path(files["worst_setup"].read_text(errors="ignore"))
        if w:
            f = files["worst_setup"]
            sc = component_of_path(project, re.sub(r"/[^/]+$", "", w["source"]))
            dc = component_of_path(project, re.sub(r"/[^/]+$", "", w["destination"]))
            w["source_component"] = sc.name if sc and sc.ownership != "excluded" else None
            w["destination_component"] = dc.name if dc and dc.ownership != "excluded" else None
            if w["source_component"] is None or w["destination_component"] is None:      # the path touches an excluded (or unknown) component: no cell names to the model
                w["source"] = w["destination"] = "(hidden: not in a component this view shows)"
            timing["worst_path"] = w
            facts.add("timing.worst_path.slack_ns", w["slack_ns"], "ns", "setup slack of the single worst path", f, "Slack", "post_route_report")
            if "logic_levels" in w:
                facts.add("timing.worst_path.levels", w["logic_levels"], "levels", f"logic levels on the worst path ({w.get('levels_by_type')})", f, "Logic Levels", "post_route_report")
            if "data_path_ns" in w:
                facts.add("timing.worst_path.data_path_ns", w["data_path_ns"], "ns", "data path delay of the worst path", f, "Data Path Delay", "post_route_report")
    if digest is not None:
        d = json.loads(digest.read_text())
        tm = d.get("timing") or (d.get("digest") or {}).get("timing") or {}
        if tm and "wns_ns" in tm and "timing.wns_ns" not in facts.items:
            timing.update({k: tm[k] for k in ("wns_ns", "whs_ns", "tns_ns", "failing_endpoints") if k in tm})
            timing["period_ns"] = tm.get("period_ns")
            if tm.get("period_ns"):
                facts.add("timing.period_ns", tm["period_ns"], "ns", "clock period the timing was checked against", digest, "timing.period_ns", "post_route_report")
            for k, unit in (("wns_ns", "ns"), ("whs_ns", "ns"), ("tns_ns", "ns"), ("failing_endpoints", "endpoints")):
                if k in tm:
                    facts.add(f"timing.{k}", tm[k], unit, f"{k} from the build digest", digest, f"timing.{k}", "post_route_report")
        sp = d.get("setup_path") or (d.get("digest") or {}).get("digest", {}).get("setup_path")
        sp = sp or ((d.get("digest") or {}).get("setup_path"))
        if sp and "worst_path" not in timing:
            sc = component_of_path(project, re.sub(r"/[^/]+$", "", sp.get("source", "")))
            dcc = component_of_path(project, re.sub(r"/[^/]+$", "", sp.get("destination", "")))
            timing["worst_path"] = {**sp, "source_component": sc.name if sc and sc.ownership != "excluded" else None,
                                    "destination_component": (dcc.name if dcc and dcc.ownership != "excluded" else None)}
            if timing["worst_path"]["source_component"] is None or timing["worst_path"]["destination_component"] is None:
                timing["worst_path"]["source"] = timing["worst_path"]["destination"] = "(hidden: not in a component this view shows)"
            facts.add("timing.worst_path.slack_ns", sp["slack_ns"], "ns", "setup slack of the single worst path", digest, "setup_path.slack_ns", "post_route_report")
            facts.add("timing.worst_path.levels", sp["logic_levels"], "levels", f"logic levels on the worst path ({sp.get('levels_by_type')})", digest,
                      "setup_path.logic_levels", "post_route_report")
            facts.add("timing.worst_path.data_path_ns", sp["data_path_ns"], "ns", "data path delay of the worst path", digest, "setup_path.data_path_ns", "post_route_report")
        feat = d.get("setup_features") or (d.get("digest") or {}).get("setup_features")
        if feat:
            timing["worst_path_features"] = feat
        ut = d.get("utilization") or (d.get("digest") or {}).get("utilization")
        if ut and "lut" in ut:
            out["resources"] = {"total": {k: ut[k] for k in ("lut", "ff", "dsp", "bram_tile") if k in ut}, "by_component": [],
                                "note": "totals only: this build record has no per-module report"}
            for k in ("lut", "ff", "dsp", "bram_tile"):
                if k in ut:
                    facts.add(f"res.total.{k}", ut[k], k, f"total {k} of the whole design", digest, f"utilization.{k}", "post_route_report")
            gaps.append("no per-module utilisation report: resources are known for the whole design only")
    if timing:
        out["timing"] = timing
    elif bdir:
        gaps.append("no timing report in the build directory: slack, levels and the worst path are unknown")

    # resources per component
    if "util_hier" in files:
        rows = parse_util_hier(files["util_hier"].read_text(errors="ignore"))
        by = {r["path"]: r for r in rows}
        comp_rows = []
        for c in visible:
            r = by.get(_inst(c)) if _inst(c) else (rows[0] if rows and rows[0]["path"] == "" and c.module == project.top else None)
            if r is None:
                continue
            # exclusive of the components nested under this one (the table's parents include their children)
            sub = [x for x in project.components if x is not c and _inst(x) and (_inst(x).startswith(_inst(c) + "/") if _inst(c) else True)]
            nested = [s for s in sub if not any(o is not s and o is not c and _inst(o).startswith(_inst(c) + "/" if _inst(c) else "") and _inst(s).startswith(_inst(o) + "/") for o in sub)]
            ex = {k: (r[k] or 0) - sum((by.get(_inst(s), {}).get(k) or 0) for s in nested) for k in ("lut", "ff")}
            rec = {"component": c.name, "instance": _inst(c) or "(top)", "lut_total": r["lut"], "ff_total": r["ff"], "lut_own": ex["lut"], "ff_own": ex["ff"],
                   "dsp": r["dsp"], "ramb36": r["ramb36"], "ramb18": r["ramb18"]}
            comp_rows.append(rec)
            f = files["util_hier"]
            facts.add(f"res.{c.name}.lut", ex["lut"], "LUT", f"LUTs in {c.name} itself (its instance total minus nested components)", f, f"row {_inst(c) or 'top'}", "post_route_report")
            facts.add(f"res.{c.name}.ff", ex["ff"], "FF", f"flip-flops in {c.name} itself", f, f"row {_inst(c) or 'top'}", "post_route_report")
        top = rows[0] if rows else None
        if top and n_hidden:                      # whole-design totals without the excluded components' share
            hid = [by.get(_inst(x)) for x in project.components if x.ownership == "excluded" and _inst(x) and by.get(_inst(x))]
            top = {**top, "lut": top["lut"] - sum(h["lut"] or 0 for h in hid), "ff": top["ff"] - sum(h["ff"] or 0 for h in hid)}
        if top:
            facts.add("res.total.lut", top["lut"], "LUT", "total LUTs of the whole design", files["util_hier"], "top row", "post_route_report")
            facts.add("res.total.ff", top["ff"], "FF", "total flip-flops of the whole design", files["util_hier"], "top row", "post_route_report")
        out["resources"] = {"total": {"lut": top["lut"], "ff": top["ff"]} if top else {}, "by_component": comp_rows,
                            "note": "'own' excludes nested components; parents in the report include their children"}
    elif out["resources"] is None and bdir:
        gaps.append("no per-module utilisation report (utilization_hier.rpt): resources per module are unknown; the agent can offer to build")

    # clock crossings
    if "cdc" in files:
        rows = parse_cdc_summary(files["cdc"].read_text(errors="ignore"))
        out["cdc"] = {"rows": rows}
        for r in rows:
            if r["source_clock"] != r["dest_clock"] and r["type"] != "Safely Timed":
                fid = f"cdc.{r['source_clock']}_to_{r['dest_clock']}"
                facts.add(fid + ".endpoints", r["endpoints"], "endpoints", f"CDC endpoints {r['source_clock']} -> {r['dest_clock']} ({r['exceptions']}; unsafe {r['unsafe']})",
                          files["cdc"], f"row {r['source_clock']} {r['dest_clock']}", "post_route_report")
    else:
        gaps.append("no report_cdc summary: clock crossings are known only from the design's stage file")

    # build record
    if "run" in files:
        r = json.loads(files["run"].read_text())
        out["build"] = {k: r.get(k) for k in ("wall_s", "vivado_version", "vivado_peak_rss_mib", "memory_cap")}
        if r.get("wall_s"):
            facts.add("build.wall_s", r["wall_s"], "s", "wall time of the recorded Vivado run (synthesis to bitstream)", files["run"], "wall_s", "post_route_report")
        if r.get("vivado_version"):
            out["build"]["vivado_version"] = r["vivado_version"]

    # latency
    st_file = design / "latency_stages.yaml"
    if st_file.is_file():
        try:
            out["latency"] = _latency(design, project, facts, path)
        except (lm.LatencyError, OSError, KeyError, ValueError) as e:
            gaps.append(f"latency budget unavailable: {e}")
    else:
        gaps.append("no latency_stages.yaml: the design has not declared its latency chain, so latency by stage is unknown")

    # earlier measured changes the design supplies (brief 104A): facts with origin prior_run, usable as a gain's `measurement` basis
    pr_file = design / "prior_runs.yaml"
    if pr_file.is_file():
        try:
            out["prior_runs"], unused = _prior_runs(pr_file, facts, {s["id"] for s in ((out["latency"] or {}).get("stages") or [])})
            if unused:
                notes.append("prior_runs.yaml: " + "; ".join(f"{n} (stage(s) {', '.join(m)} are not in this design's latency chain)" for n, m in unused)
                             + ": measured on another chain, so they are not facts of this analysis")
        except (OSError, KeyError, ValueError, TypeError, yaml.YAMLError) as e:
            gaps.append(f"prior_runs.yaml could not be read: {e}")

    out["facts"] = facts.items
    out["sources"] = sorted(facts.files.values(), key=lambda x: x["file"])
    out["component_hashes"] = {c.name: managed.component_hash(project, c) for c in visible}      # an RTL edit with unchanged reports still makes the analysis stale
    out["hash"] = hashlib.sha256(json.dumps({k: out[k] for k in ("components", "latency", "timing", "resources", "cdc", "facts", "sources", "component_hashes", "prior_runs") if k in out}, sort_keys=True, default=str).encode()).hexdigest()
    return out


def _prior_runs(pr_file: Path, facts: Facts, stage_ids: set[str]) -> tuple[list[dict[str, Any]], list[tuple[str, list[str]]]]:
    """``prior_runs.yaml``: earlier changes to this design that were measured (schema ``fda-prior-runs/1``). Each run lists the latency stages it changed
    and its evidence entries; every entry becomes the fact ``prior.<run>.<id>`` (origin ``prior_run``) and must point at an existing file. A run whose stages
    are not all in the analysis's latency chain is left out (an excluded component's stages are not in it: what is hidden stays hidden; a stage the chain no longer has was
    measured on a different chain). Returns ``(runs used, [(name, missing stages)] left out)``. The evidence entry with id ``gain`` is a run's headline."""
    doc = yaml.safe_load(pr_file.read_text()) or {}
    if doc.get("schema") != "fda-prior-runs/1":
        raise ValueError("schema must be fda-prior-runs/1")
    out = []
    unused: list[tuple[str, list[str]]] = []
    for r in doc.get("runs") or []:
        name = r["name"]
        stages = list(r["stages"])
        if not set(stages) <= stage_ids:
            unused.append((name, sorted(set(stages) - stage_ids)))
            continue
        ids = {}
        for e in r["evidence"]:
            f = facts.base / e["file"]
            if not f.is_file():
                raise OSError(f"{name}: evidence file {e['file']} not found")
            ids[e["id"]] = facts.add(f"prior.{name}.{e['id']}", e["value"], e["unit"], f"{name}: {e['text']}", f, e["locator"], "prior_run")
        if "gain" not in ids:
            raise ValueError(f"{name}: no evidence entry with id gain")
        out.append({"name": name, "metric": r.get("metric", "latency_clocks"), "stages": stages, "gain": facts.items[ids["gain"]]["value"], "fact": ids["gain"],
                    "facts": ids, "summary": r.get("summary", "")})
    return out, unused


def _first_dir(*ds: Path) -> Path | None:
    return next((d for d in ds if d.is_dir() and any(d.iterdir())), None)


def _converted(design: Path) -> dict[str, Any]:
    raw = managed.from_design(design)
    comps = [managed.Component(name=c["name"], ownership=c["ownership"], level=c["level"], paths=list(c["paths"]), module=c.get("module"),
                               build_sources=list(c.get("build_sources") or []), description=c.get("description", "")) for c in raw["components"]]
    return {"name": raw["name"], "top": raw["top"], "components": comps, "design": design}


def _latency(design: Path, project: managed.Project, facts: Facts, path: str | None) -> dict[str, Any]:
    st = lm.load_stages(design)
    path = path or next(iter(st["paths"]))
    st_file = design / "latency_stages.yaml"

    def locate(rel: str) -> Path:
        for b in (design, ROOT):
            if (b / rel).is_file():
                return b / rel
        raise OSError(f"{rel} not found (looked in the design directory and the repository root)")
    core_f = locate(st["trace"]["results_file"])
    core = json.loads(core_f.read_text())
    sl_f = None
    slack = None
    try:
        sl_f = locate(st["slack"]["file"])
        slack = lm.load_slack(sl_f)
    except OSError:
        pass
    lp = lm.latency_path(design, core, slack, path, st)
    bud = lm.latency_budget(design, core, slack, (sl_f.parent if sl_f else None), st, path)
    rows = []
    by_budget = {r["stage"]: r for r in bud["rows"]}
    hidden = 0
    for s in lp["stages"]:
        sd = next(x for x in st["paths"][path]["stages"] if x["id"] == s["id"])
        comp = stage_component(project, sd)
        if comp is not None and comp.ownership == "excluded":
            hidden += 1
            continue
        b = by_budget.get(s["id"], {})
        rec = {"id": s["id"], "name": s["name"], "domain": s["domain"], "kind": s["kind"], "clocks": s["clocks"], "ns": s["ns"],
               "component": comp.name if comp else None, "component_ownership": comp.ownership if comp else None,
               "setup_slack_ns": (s["netlist"] or {}).get("setup_slack_ns"), "why": s["why"], "risk_of_removing": s["remove_risk"],
               "technique": b.get("technique", s["technique"]), "removable_clocks": b.get("removable_clocks", s["removable"])}
        rows.append(rec)
        facts.add(f"stage.{s['id']}.clocks", s["clocks"], "clocks", f"clocks stage {s['id']} adds on the {path} chain (simulation)", core_f,
                  f"stage table row {s['id']} (segment sums reconcile with {st['paths'][path]['measured']['key']})", "simulation")
        if rec["setup_slack_ns"] is not None and sl_f is not None:
            facts.add(f"stage.{s['id']}.slack_ns", rec["setup_slack_ns"], "ns", f"post-route setup slack of stage {s['id']}'s registers", sl_f,
                      f"stages.{s['id']}.setup_slack_ns", "post_route_report")
        if isinstance(rec["removable_clocks"], int):
            facts.add(f"stage.{s['id']}.removable", rec["removable_clocks"], "clocks", f"clocks the stage file says could come out of {s['id']} (an upper bound, not a plan)",
                      st_file, f"stages[{s['id']}].removable", "stage_file")
    facts.add("latency.total_clocks", lp["total_clocks"], "clocks", f"digital clocks of the {path} chain, GT word to GT word (simulation)", core_f, st["paths"][path]["measured"]["key"], "simulation")
    facts.add("latency.period_ns", lp["period_ns"], "ns", "clock period of the chain", st_file, "period_ns", "stage_file")
    out = {"path": path, "title": lp["title"], "period_ns": lp["period_ns"], "total_clocks": lp["total_clocks"], "total_ns": lp["total_ns"],
           "reconciled": lp["reconciled"], "problems": lp["problems"], "stages": rows, "hidden_stages": hidden,
           "removable_upper_bound": bud["total_removable_digital_clocks_upper_bound"], "board": bud.get("board"),
           "note": "stage clocks are in-phase simulation with a zero-latency GT stand-in; the board adds GT and optics that simulation cannot see"}
    if bud.get("board"):
        b = bud["board"]
        facts.add("latency.board_gt_optics_clocks", b["gt_optics_clocks"], "clocks", "GT and optics share of the wire-to-wire latency, from the recorded board run", sl_f or st_file, "board", "board")
    return out
