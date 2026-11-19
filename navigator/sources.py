"""The read-only readers behind every page: each returns plain data and names the file (and date) every number came from.

Nothing here writes, starts a process or opens a socket. The dates are the committer date of the file's last commit (``git log``), else
its modification time; a field recorded inside the file (``created``, ``started``) is used when there is one and is labelled as such.
"""

from __future__ import annotations

import functools
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

from agent.core import managed as M

JSON_LIMIT = 8_000_000                                   # a file larger than this is listed, not loaded
HEX64 = re.compile(r"^[0-9a-f]{64}$")


# --- provenance of a number: file and date ----------------------------------------------------------------------------------------

@functools.lru_cache(maxsize=4096)
def _git_date(root: str, rel: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", root, "log", "-1", "--format=%cs", "--", rel], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() or None


def file_date(root: Path, p: Path) -> str | None:
    """Committer date of the file's last commit, else the modification date (the file is local, not yet committed)."""
    try:
        rel = p.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        rel = None
    d = _git_date(str(root), rel) if rel else None
    if d:
        return d
    try:
        return time.strftime("%Y-%m-%d", time.localtime(p.stat().st_mtime))
    except OSError:
        return None


def src(root: Path, p: Path, key: str | None = None, created: str | None = None) -> dict[str, Any]:
    """{"file": repo-relative path, "date": ..., "date_from": "recorded"|"git"|"mtime"} and the key inside the file, when given."""
    try:
        rel = p.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        rel = p.name
    d = {"file": rel, "date": created[:10] if created else file_date(root, p), "date_from": "recorded" if created else "file"}
    if key:
        d["key"] = key
    return d


def load_json(p: Path) -> Any | None:
    try:
        if p.stat().st_size > JSON_LIMIT:
            return None
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def sha256_file(p: Path) -> str | None:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None


# --- managed projects --------------------------------------------------------------------------------------------------------------

def design_dirs(root: Path) -> list[Path]:
    return sorted(p.parent for p in (Path(root) / "designs").glob("*/project.yaml"))


def load_project(root: Path, name: str) -> M.Project | None:
    d = Path(root) / "designs" / name
    if "/" in name or ".." in name or not d.is_dir():
        return None
    return M.load(d)


def project_list(root: Path) -> list[dict[str, Any]]:
    out = []
    for d in design_dirs(root):
        try:
            p = M.load(d)
        except ValueError as e:
            out.append({"name": d.name, "error": str(e)})
            continue
        if p is not None:
            out.append({"name": d.name, "top": p.top, "components": len(p.components),
                        "ownership": {o: sum(c.ownership == o for c in p.components) for o in ("owned", "frozen", "excluded")}})
    return out


def _evidence_files(root: Path, p: M.Project, c: M.Component) -> list[dict[str, Any]]:
    cand: list[tuple[str, Path]] = []
    ev = M.evidence_path(p, c)
    cand.append(("own-tests and build evidence (written by the flow)", ev))
    if c.netlist.get("file"):
        cand.append(("netlist", p.design / c.netlist["file"]))
    if c.netlist.get("sim_file"):
        cand.append(("functional netlist for simulation", p.design / c.netlist["sim_file"]))
    for r in c.reference_rtl:
        cand.append(("reference RTL for the equivalence proof", p.design / r))
    for t in (c.provenance.get("tests") or []):
        cand.append(("the block's own tests", p.design / t if isinstance(t, str) else p.design))
    out = []
    for what, f in cand:
        try:
            shown = f.resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            shown = f.name
        out.append({"what": what, "file": shown, "exists": f.exists(), "date": file_date(root, f) if f.exists() else None})
    return out


def component_view(root: Path, p: M.Project, c: M.Component) -> dict[str, Any]:
    label, why = M.trust(p, c)
    iface = c.interface or {}
    return {"name": c.name, "module": c.module, "instance": c.instance, "ownership": c.ownership, "level": c.level, "trust": label, "why_not_higher": why,
            "description": c.description, "aliases": c.aliases,
            "interface": {"ports": iface.get("ports") or [], "clocks": iface.get("clocks") or [], "resets": iface.get("resets") or [],
                          "timing_budgets": iface.get("timing_budgets") or []},
            "provenance": {k: c.provenance.get(k) for k in ("origin", "version", "licence", "sha256") if c.provenance.get(k)},
            "paths": c.paths, "build_sources": c.build_sources, "placement": c.placement or None, "evidence": _evidence_files(root, p, c),
            "approved_contract_change": c.name in p.approved_contract_changes,
            "selectable": c.ownership == "owned",
            "not_selectable_why": None if c.ownership == "owned" else (
                f"{c.ownership}: it cannot be edited, so it cannot be in a scope" if c.ownership == "frozen"
                else "excluded: the agent does not see it, so a scope cannot name it")}


def project_tree(root: Path, name: str) -> dict[str, Any] | None:
    p = load_project(root, name)
    if p is None:
        return None
    comps = {c.name: component_view(root, p, c) for c in p.components}
    # the hierarchy: a component sits under the component whose instance path is the longest proper prefix of its own; the component
    # of the top module (no instance) is the root, a synthetic root when there is none
    root_c = next((c for c in p.components if c.module == p.top and not c.instance), None)
    parent: dict[str, str | None] = {}
    for c in p.components:
        if c is root_c:
            parent[c.name] = None
            continue
        inst = (c.instance or "").strip("/")
        best = None
        for o in p.components:
            oi = (o.instance or "").strip("/")
            if o is not c and oi and inst.startswith(oi + "/") and (best is None or len(oi) > len((best.instance or "").strip("/"))):
                best = o
        parent[c.name] = best.name if best else (root_c.name if root_c else None)
    children: dict[str | None, list[str]] = {}
    for c in p.components:
        children.setdefault(parent[c.name], []).append(c.name)

    def node(n: str) -> dict[str, Any]:
        return {"name": n, "children": [node(k) for k in children.get(n, [])]}
    tops = [node(n) for n in children.get(None, [])]
    return {"project": {"name": p.name, "top": p.top, "design": name, "unclaimed": p.unclaimed, "approved_contract_changes": p.approved_contract_changes},
            "tree": tops, "components": comps, "source": src(root, p.design / M.MANIFEST),
            "legend": {"ownership": {"owned": "the agent may edit it, when the request's scope includes it",
                                     "frozen": "read only: the agent may read it and not change it",
                                     "excluded": "hidden from the agent's tools; still built and signed off with the whole design"},
                       "level": {"rtl": "source RTL", "netlist": "a netlist made elsewhere (EDIF or checkpoint)", "placed_routed": "a placed and routed checkpoint",
                                 "vendor_ip": "vendor IP", "encrypted_ip": "encrypted IP"},
                       "trust": {"none": "no provenance or contract on record", "documented": "origin, version, licence, hash and a contract on record",
                                 "verified": "documented, and its own tests passed on the current content", "built": "verified, and a build had every gate clean on the current content"}}}


def scope_view(root: Path, name: str, components: list[str], request: str = "") -> dict[str, Any] | None:
    """What the scope picker shows: the resolution the agent itself would make (``managed.resolve_request``) and the command that corresponds."""
    p = load_project(root, name)
    if p is None:
        return None
    res = M.resolve_request(p, request, components or None)
    cmd = ["python", "-m", "agent", "resume", f"designs/{name}", request or "<change request>"]
    if components:
        cmd += ["--scope", ",".join(components)]
    out: dict[str, Any] = {"project": name, "ask": res.question, "notes": res.notes, "command": cmd, "runs_anything": False}
    if res.scope is not None:
        out.update(components=list(res.scope.components), source=res.scope.source, will_touch=list(res.scope.components),
                   read_only=[c.name for c in p.components if c.ownership == "frozen"],
                   not_in_scope_owned=[c.name for c in p.owned() if c.name not in res.scope.components])
    return out


# --- latency, timing, resources -----------------------------------------------------------------------------------------------------

def latency_designs(root: Path) -> list[str]:
    return sorted(p.parent.name for p in (Path(root) / "designs").glob("*/latency_stages.yaml"))


def latency_view(root: Path, design: str) -> dict[str, Any] | None:
    from flow.latency import model as L
    d = Path(root) / "designs" / design
    if "/" in design or ".." in design or not (d / "latency_stages.yaml").is_file():
        return None
    st = L.load_stages(d)
    core_rel = st["trace"]["results_file"]
    core = load_json(Path(root) / core_rel)
    if core is None:
        return {"design": design, "error": f"{core_rel} is missing: the simulated chain has not been recorded"}
    slack_rel = (st.get("slack") or {}).get("file")
    slack = L.load_slack(Path(root) / slack_rel) if slack_rel else None
    try:
        lp = L.latency_path(d, core, slack, st=st)
    except L.LatencyError as e:
        return {"design": design, "error": str(e)}
    for row in lp["stages"]:
        row.pop("registers", None)
    lp["sources"] = {"stages": src(root, d / "latency_stages.yaml"), "simulation": src(root, Path(root) / core_rel),
                     "slack": src(root, Path(root) / slack_rel) if slack is not None else None,
                     "slack_missing_note": None if slack is not None else f"{slack_rel} is not recorded: stages show no slack (unknown, not fine)"}
    board = None
    try:
        board = L.board_numbers(st, Path(root) / "results")
    except (L.LatencyError, KeyError, ValueError, OSError):
        board = None
    lp["board"] = board
    lp["board_note"] = ("board numbers are measured on the KR260 (stage 3 of brief 96) and are never added to the simulated chain" if board
                        else "no board measurement is recorded for this design's chain")
    return lp


def builds(root: Path) -> list[dict[str, Any]]:
    """Every post-route build digest in results/*/builds/*/digest.json: timing, resources, power, gates, and the run's version and wall time."""
    out = []
    for dg in sorted((Path(root) / "results").glob("*/builds/*/digest.json")):
        d = load_json(dg)
        if not isinstance(d, dict) or "timing" not in d:
            continue
        run = load_json(dg.parent / "run.json") or {}
        t, u, pw, g = d.get("timing") or {}, d.get("utilization") or {}, d.get("power") or {}, d.get("gates") or {}
        res = {k: u.get(k) for k in ("lut", "ff", "bram_tile", "dsp") if k in u}
        res["available"] = {k: u.get(k + "_available") for k in ("lut", "ff", "bram_tile", "dsp") if (k + "_available") in u}
        out.append({"id": f"{dg.parent.parent.parent.name}/{dg.parent.name}", "set": dg.parent.parent.parent.name, "variant": dg.parent.name,
                    "wns_ns": t.get("wns_ns"), "whs_ns": t.get("whs_ns"), "tns_ns": t.get("tns_ns"), "timing_met": t.get("timing_met"),
                    "failing_endpoints": t.get("failing_endpoints"), "period_ns": t.get("period_ns"), "resources": res,
                    "power_w": pw.get("total_w"), "junction_c": pw.get("junction_c"), "power_confidence": pw.get("confidence"),
                    "gates_total": len(g), "gates_failing": sorted(k for k, v in g.items() if v is not True),
                    "vivado_version": run.get("vivado_version"), "wall_s": run.get("wall_s"), "build_id": run.get("build_id"),
                    "git_commit": (run.get("git_commit") or "")[:8] or None, "design": run.get("design"),
                    "source": src(root, dg), "run_source": src(root, dg.parent / "run.json") if run else None})
    return out


def board_records(root: Path) -> list[dict[str, Any]]:
    """Board sessions: every results/**/hw/<session>/<variant>/stage3.json (restart statistics, E and L), with the session's conditions."""
    out = []
    for f in sorted((Path(root) / "results").glob("*/hw/*/*/stage3.json")):
        d = load_json(f)
        if not isinstance(d, dict) or "restarts" not in d:
            continue
        r = d["restarts"] or {}
        sess = load_json(f.parent / "session.json") or {}
        out.append({"id": f.relative_to(Path(root) / "results").parent.as_posix(), "variant": f.parent.name, "session": f.parent.parent.name,
                    "started": d.get("started"), "link_up": d.get("link_up"), "safety_ok": (d.get("safety") or {}).get("ok"),
                    "restarts": r.get("restarts"), "failed_to_lock": r.get("failed_to_lock"),
                    "lock_clocks": r.get("lock_clocks"), "E_min": r.get("E_min_per_link"), "E_max": r.get("E_max_per_link"),
                    "L_min": r.get("L_min_per_link"), "L_max": r.get("L_max_per_link"),
                    "D_clocks": d.get("D_clocks_from_medians_of_minima"), "fibre_one_way_ns": d.get("fibre_one_way_ns"),
                    "conditions_start": sess.get("conditions_start"), "conditions_end": sess.get("conditions_end"), "roc_ok": sess.get("roc_ok"),
                    "source": src(root, f, created=d.get("started"))})
    return out


def ppm_records(root: Path) -> dict[str, Any]:
    """The frequency-offset sweeps: the board's (ppm_session.json) and the simulated partner's (ppm_sim_*.json)."""
    boards, sims = [], []
    for f in sorted((Path(root) / "results").glob("*/hw/*/*/ppm_session.json")):
        d = load_json(f)
        if not isinstance(d, dict):
            continue
        pts = []
        for p in d.get("points") or []:
            dw = p.get("dwell") or {}
            tx, rx = dw.get("tx") or {}, dw.get("rx") or {}
            pts.append({"target_ppm": p.get("target_ppm"), "reachable": p.get("reachable"), "ppm_calibrated": p.get("ppm_calibrated"),
                        "ppm_dwell": dw.get("ppm_dwell"), "orders_expected": dw.get("orders_expected"), "orders_sent": tx.get("n_order"),
                        "orders_fired": rx.get("fired"), "frames_bad": rx.get("bad"), "l_min": tx.get("l_min"), "l_max": tx.get("l_max"),
                        "verdict": p.get("verdict")})
        boards.append({"id": f.relative_to(Path(root) / "results").parent.as_posix(), "dwell_s": d.get("dwell_s"), "points": pts,
                       "conditions_start": d.get("conditions_start"), "conditions_end": d.get("conditions_end"), "source": src(root, f, created=d.get("started"))})
    for f in sorted((Path(root) / "results").glob("*/ppm_sim_*.json")):
        d = load_json(f)
        if not isinstance(d, dict):
            continue
        pts = []
        for k, v in d.items():
            if not isinstance(v, dict) or "ppm" not in v:
                continue
            rx = v.get("rx") or {}
            pts.append({"name": k, "ppm": v.get("ppm"), "frames_sent": v.get("frames_sent_by_partner"), "frames": rx.get("frames"), "good": rx.get("good"),
                        "bad": rx.get("bad"), "inserts": rx.get("rm_ins"), "deletes": rx.get("rm_del"), "overflow": rx.get("rm_ovf")})
        if pts:
            sims.append({"id": f.name, "points": sorted(pts, key=lambda x: x["ppm"] if x["ppm"] is not None else 0), "source": src(root, f)})
    return {"board": boards, "simulated": sims}


def sim_latency_records(root: Path) -> list[dict[str, Any]]:
    out = []
    for f in sorted((Path(root) / "results").glob("*/rm_latency_sim.json")):
        d = load_json(f)
        if isinstance(d, dict):
            out.append({"id": f.parent.name, "what": d.get("what"), "phase_ps_is": d.get("phase_ps_is"),
                        "series": {k: d[k] for k in d if isinstance(d[k], list) and d[k] and isinstance(d[k][0], dict) and "phase_ps" in d[k][0]},
                        "source": src(root, f)})
    return out


# --- runs ----------------------------------------------------------------------------------------------------------------------------

SUMMARY_FIELDS = ("run_id", "design", "model", "harness", "harness_arm", "profile", "interview", "review", "loops", "tokens", "cost_usd", "turns", "wall_s", "stop",
                  "plan_cost_estimate_usd", "claude_code_version", "oracle_model", "model_table_hash", "stages_visited", "bringup", "gates_last")
CALL_FIELDS = ("seq", "purpose", "stage", "endpoint", "kind", "model", "entry_hash", "table_hash", "prompt_tokens", "completion_tokens", "cost_usd", "seconds")
CC_FIELDS = ("tag", "role", "stage", "model_requested", "models_served", "effort", "turns", "tool_calls", "wall_s", "timed_out", "subtype", "is_error",
             "tokens", "cost_usd", "plan_cost_estimate_usd")
USAGE_FIELDS = ("stage", "visit", "role", "harness", "model", "effort", "turns", "ended", "tokens", "wall_s", "cost_usd", "plan_cost_estimate_usd")
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")


def _pick(d: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {k: d[k] for k in fields if isinstance(d, dict) and k in d}


def _jsonl(p: Path, limit: int = 2000) -> list[Any]:
    rows: list[Any] = []
    try:
        with p.open() as f:
            for line in f:
                if len(rows) >= limit:
                    break
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return rows


def _fp(d: Any) -> dict[str, Any] | None:
    """A prompt fingerprint is {"sha256": 64 hex, "chars": int} and nothing else: anything else (an older record that kept text) is dropped."""
    if isinstance(d, dict) and isinstance(d.get("sha256"), str) and HEX64.match(d["sha256"]) and isinstance(d.get("chars"), int):
        return {"sha256": d["sha256"], "chars": d["chars"]}
    return None


def run_list(runs_dir: Path, root: Path) -> list[dict[str, Any]]:
    out = []
    for d in sorted(Path(runs_dir).glob("*/summary.json"), reverse=True) if Path(runs_dir).is_dir() else []:
        s = load_json(d)
        if not isinstance(s, dict):
            continue
        sc = s.get("scope") or {}
        row = _pick(s, ("run_id", "design", "model", "harness", "stop", "cost_usd", "plan_cost_estimate_usd", "wall_s", "loops"))
        row.update(id=d.parent.name, scope=sc.get("components"), started=d.parent.name[:15], source={"file": f"runs/{d.parent.name}/summary.json", "date": file_date(root, d)})
        out.append(row)
    return out


def run_detail(runs_dir: Path, run_id: str, root: Path) -> dict[str, Any] | None:
    if not RUN_ID.match(run_id):
        return None
    d = Path(runs_dir) / run_id
    s = load_json(d / "summary.json")
    if not isinstance(s, dict):
        return None
    sc = s.get("scope") or {}
    prompts = []
    for pf in sorted((d / "claude_code").glob("*.prompt.json")) if (d / "claude_code").is_dir() else []:
        j = load_json(pf)
        if isinstance(j, dict):
            prompts.append({"call": pf.name[:-len(".prompt.json")], "user_fp": _fp(j.get("user_message")), "system_fp": _fp(j.get("system_prompt")),
                            "prompt_manifest_sha256": ((j.get("prompts_pin") or {}).get("manifest_sha256") if isinstance(j.get("prompts_pin"), dict) else None),
                            "enforced": ((j.get("prompts_pin") or {}).get("enforced") if isinstance(j.get("prompts_pin"), dict) else None)})
    return {"id": run_id, "summary": _pick(s, SUMMARY_FIELDS),
            "scope": {k: sc.get(k) for k in ("components", "source", "time", "plan") if k in sc} or None,
            "per_stage": s.get("per_stage"), "per_role": s.get("per_role"),
            "calls": [_pick(r, CALL_FIELDS) for r in _jsonl(d / "model_calls.jsonl")],
            "claude_code_calls": [_pick(r, CC_FIELDS) for r in _jsonl(d / "claude_code_calls.jsonl")],
            "usage": [_pick(r, USAGE_FIELDS) for r in _jsonl(d / "role_usage.jsonl")],
            "prompts": prompts,
            "prompts_note": "prompt names and hashes only; the rendered prompt text is private and is never read by the navigator",
            "source": {"file": f"runs/{run_id}/summary.json", "date": file_date(root, d / "summary.json")}}


# --- captures -------------------------------------------------------------------------------------------------------------------------

def capture_files(root: Path, extra: list[Path] | None = None) -> list[Path]:
    """Eye captures (schema fda-capture-eye/1) under results/ and any extra directories: found by the first bytes of each JSON file."""
    out = []
    for base in [Path(root) / "results", *(extra or [])]:
        for f in sorted(base.rglob("*.json")) if base.is_dir() else []:
            try:
                with f.open("rb") as fh:
                    head = fh.read(400)
            except OSError:
                continue
            if b"fda-capture-eye/1" in head:
                out.append(f)
    return out


# --- the record viewer -----------------------------------------------------------------------------------------------------------------

RECORD_SUFFIX = {".json", ".yaml", ".yml", ".md", ".txt", ".rpt", ".csv"}
RECORD_LIMIT = 400_000
_DESIGN_FILES = re.compile(r"^designs/[A-Za-z0-9_.-]+/(project|latency_stages)\.yaml$")


def read_record(root: Path, rel: str) -> dict[str, Any] | None:
    """A committed record, shown as plain text: only a file under results/ or a design's project.yaml or latency_stages.yaml, of a text type, inside the
    repository once symlinks are resolved. Anything else, however it is spelled, is None."""
    if not rel or "\x00" in rel or rel.startswith("/") or ".." in Path(rel).parts:
        return None
    if not (rel.startswith("results/") or _DESIGN_FILES.match(rel)) or Path(rel).suffix not in RECORD_SUFFIX:
        return None
    p = (Path(root) / rel).resolve()
    try:
        p.relative_to(Path(root).resolve())
    except ValueError:
        return None
    if not p.is_file() or p.stat().st_size > RECORD_LIMIT:
        return None
    try:
        body = p.read_text(errors="replace")
    except OSError:
        return None
    return {"file": rel, "date": file_date(root, p), "bytes": p.stat().st_size, "lines": body.splitlines()[:6000]}
