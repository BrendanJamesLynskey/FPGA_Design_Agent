"""One finished run directory into one result record (``fda-example-result/1``). Reads files only; starts no model and no tool.

Every figure comes from a file the run wrote: ``summary.json`` and ``role_usage.jsonl`` (tokens, turns, plan-estimated cost, wall), ``<design>/build/<variant>/gates.json``
and ``run.json`` (resources, slack, build stamp, Vivado version), ``manifest.json`` (build ID) and the scorer's result (the hidden bench). **Nothing is typed in by hand
and no model produces a score.** The record holds no prompt text, no source text and no path outside the run (the leak gate, agent/tests/test_99_prompts.py, runs over
the committed records).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from agent.repro.compare import SCHEMA

RTL_EXT = (".sv", ".v", ".vhd", ".vhdl")


def _json(p: Path) -> Any:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def design_dir(run_dir: Path, name: str | None = None) -> Path | None:
    cfg = _json(run_dir / "config.json") or {}
    n = name or cfg.get("name")
    if n and (run_dir / n).is_dir():
        return run_dir / n
    subs = [p for p in run_dir.iterdir() if p.is_dir() and (p / "spec.md").is_file()] if run_dir.is_dir() else []
    return subs[0] if len(subs) == 1 else None


def rtl_files(design: Path | None) -> list[Path]:
    if design is None or not (design / "rtl").is_dir():
        return []
    return sorted(p for p in (design / "rtl").rglob("*") if p.is_file() and p.suffix in RTL_EXT and not p.is_symlink())


def rtl_hash(files: list[Path], base: Path | None = None) -> str | None:
    """SHA-256 over the sorted (relative name, bytes) pairs, line endings normalised. The same files give the same hash on any machine."""
    if not files:
        return None
    h = hashlib.sha256()
    for p in files:
        rel = p.relative_to(base).as_posix() if base else p.name
        h.update(rel.encode() + b"\0" + p.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def build_of(design: Path | None) -> dict[str, Any]:
    """Resources, slack and identity of the last post-route build of the base variant (``build/base``), else the first variant that has gates.json."""
    out: dict[str, Any] = {}
    if design is None:
        return out
    bdirs = [design / "build" / "base"] + sorted(p for p in (design / "build").glob("*") if p.is_dir() and p.name != "base")
    for b in bdirs:
        g = _json(b / "gates.json")
        if not isinstance(g, dict):
            continue
        t, u = g.get("timing") or {}, g.get("utilization") or {}
        run = _json(b / "run.json") or {}
        man = _json(b / "manifest.json") or {}
        out = {"variant": b.name, "build_pass": g.get("pass"), "first_failed_stage": g.get("first_failed_stage"), "lut": u.get("lut"), "ff": u.get("ff"), "dsp": u.get("dsp"),
               "bram36": u.get("bram_tile"), "wns_ns": t.get("wns_ns"), "whs_ns": t.get("whs_ns"), "timing_met": t.get("timing_met"),
               "build_stamp": g.get("build_stamp") or run.get("build_stamp"), "sources_sha256": g.get("sources_sha256") or run.get("sources_sha256"),
               "build_id": man.get("build_id") or run.get("build_id"), "vivado_version": run.get("vivado_version"), "vivado_wall_s": run.get("wall_s")}
        out["gates_passed"] = sum(1 for v in (g.get("gates") or {}).values() if v is True)
        out["gates_total"] = len(g.get("gates") or {})
        break
    return out


def usage_of(run_dir: Path) -> dict[str, Any]:
    tok, cost, n, wall = 0, 0.0, 0, 0.0
    served: set[str] = set()
    try:
        for line in (run_dir / "role_usage.jsonl").read_text().splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            n += 1
            tok += d.get("tokens") or 0
            cost += d.get("plan_cost_estimate_usd") or 0.0
            wall += d.get("wall_s") or 0.0
    except OSError:
        pass
    try:
        for line in (run_dir / "claude_code_calls.jsonl").read_text().splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            served.update(d.get("models_served") or [])
            cost_extra = d.get("plan_cost_estimate_usd")
            if "plan_cost_estimate_usd" not in d and isinstance(cost_extra, (int, float)):
                cost += cost_extra
    except OSError:
        pass
    return {"tokens": tok or None, "plan_cost_estimate_usd": round(cost, 4) if n else None, "agent_call_wall_s": round(wall, 1) if n else None, "models_served": sorted(served)}


def extract(run_dir: Path, example: str, score: dict[str, Any] | None, setup: dict[str, Any], wall_s: float | None = None) -> dict[str, Any]:
    """``score`` is the scorer's own result (``{"pass": bool, "tests_passed": n, "tests_total": n, "tests": {name: bool}}``) or None when it did not run."""
    run_dir = Path(run_dir)
    summ = _json(run_dir / "summary.json") or {}
    design = design_dir(run_dir)
    files = rtl_files(design)
    b = build_of(design)
    u = usage_of(run_dir)
    visits = summ.get("stages_visited") or []
    stages = sorted(set(visits))
    repair = max(len(visits) - len(stages), 0)
    gates_ok = bool(b.get("build_pass")) if b else False
    stop = summ.get("stop") or summ.get("stop_reason") or summ.get("outcome")
    rec: dict[str, Any] = {
        "schema": SCHEMA, "example": example, "run_id": run_dir.name, "date": summ.get("date"), "setup": {**setup, "models_served": u["models_served"]},
        "outcome": {"hidden_pass": (score or {}).get("pass"), "tests_passed": (score or {}).get("tests_passed"), "tests_total": (score or {}).get("tests_total"),
                    "internal_pass": gates_ok and bool(stages) and max(stages) >= int(setup.get("stop_after") or 0) if b else False, "build_gates": f"{b.get('gates_passed')}/{b.get('gates_total')}" if b else None,
                    "last_stage": max(stages) if stages else None, "stop": stop if isinstance(stop, (str, int, float)) else (json.dumps(stop)[:200] if stop else None)},
        "tool_results": {"rtl_sha256": rtl_hash(files, design / "rtl" if design else None), "rtl_files": [p.name for p in files], **{k: b.get(k) for k in
                         ("lut", "ff", "dsp", "bram36", "wns_ns", "whs_ns", "timing_met", "build_stamp", "sources_sha256", "build_id", "vivado_version", "build_pass")},
                         "bench_tests": (score or {}).get("tests")},
        "varies": {"rtl_lines": sum(len(p.read_text(errors="replace").splitlines()) for p in files) if files else None, "repair_visits": repair, "loops": summ.get("loops"),
                   "agent_turns": summ.get("turns"), "tokens": u["tokens"] or summ.get("tokens"), "cost_usd": u["plan_cost_estimate_usd"], "cost_basis": "the plan's estimate (Claude Code reports no bill on a subscription)",
                   "wall_s": wall_s if wall_s is not None else summ.get("wall_s"), "agent_call_wall_s": u["agent_call_wall_s"], "vivado_wall_s": b.get("vivado_wall_s"),
                   "questions_asked": (summ.get("questions") or {}).get("asked") if isinstance(summ.get("questions"), dict) else None},
    }
    return rec


def check_no_text(rec: dict[str, Any]) -> list[str]:
    """Why a record may not be committed: it carries a long free-text field or an absolute path. Records hold numbers, names and hashes only."""
    bad: list[str] = []

    def walk(v: Any, path: str) -> None:
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, f"{path}.{k}")
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, f"{path}[{i}]")
        elif isinstance(v, str):
            if len(v) > 240:
                bad.append(f"{path}: {len(v)} characters of text")
            if re.search(r"(?<![\w.])/(?:home|tmp|Users|opt)/", v):
                bad.append(f"{path}: an absolute path")
    walk(rec, "$")
    return bad
