"""Run an example and write its result (brief 195): pre-flight, the pinned ``agent run`` command, the hidden bench, the result record.

``run_example`` is what ``python -m agent example run <name>`` and the navigator's Examples page both call. The navigator holds its own heavy slot, so it
passes ``slot=False``; on the command line the slot is taken here when the owner's ``take_heavy_slot.sh`` exists (a machine without it runs without one).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from agent.repro import compare as C
from agent.repro import extract as X
from agent.repro import registry as R

ROOT = R.ROOT
RUNS = ROOT / "runs"
HANDOFF = Path(os.environ.get("FDA_HANDOFF") or next((p / "_handoff" for p in ROOT.parents if (p / "_handoff").is_dir()), ROOT / "_handoff"))
RESULT_FILE = "example_result.json"


def references(name: str, results: Path | None = None) -> list[dict[str, Any]]:
    d = (results or R.RESULTS) / name
    out = []
    for p in sorted(d.glob("ref_*.json")) if d.is_dir() else []:
        try:
            out.append(json.loads(p.read_text()))
        except ValueError:
            continue
    return out


def setup_of(pins: dict[str, Any], pre: dict[str, Any]) -> dict[str, Any]:
    cli = next((c for c in pre["checks"] if c["name"] == "claude_cli"), {})
    kb = next((c for c in pre["checks"] if c["name"] == "knowledge_bank"), {})
    viv = next((c for c in pre["checks"] if c["name"] == "vivado"), {})
    from agent.core import prompts
    pin = prompts.read_pin()
    keep = ("harness", "cc_model", "cc_effort", "oracle", "oracle_cc_model", "interview", "review", "verif_level", "harness_arm", "docs", "profile", "board", "hdl", "stop_after", "seeds")
    return {**{k: pins[k] for k in keep}, "claude_cli_version": (cli.get("installed") or pins["claude_cli_version"]).split(" ")[0], "claude_cli_sha256": cli.get("sha256"),
            "vivado_version": pins["vivado_version"] if viv.get("ok") else None, "kb_commit": kb.get("installed"), "prompts_manifest_sha256": pin.get("manifest_sha256"),
            "agent_commit": R.repo_commit(), "unpinned_waived": pre.get("unpinned_waived") or []}


def score(e: dict[str, Any], run_dir: Path, python: str) -> dict[str, Any] | None:
    """The task's own hidden bench on the run's RTL (seed 1, Icarus). Returns the bench's per-test verdicts, never a model's opinion."""
    design = X.design_dir(run_dir)
    if design is None or not X.rtl_files(design):
        return {"pass": False, "tests": {}, "tests_passed": 0, "tests_total": 0, "error": "the run wrote no RTL"}
    out = run_dir / "example_score.json"
    p = subprocess.run([python, str(ROOT / e["scorer"]), str(R.task_dir(e)), "--rtl", str(design / "rtl"), "--tag", run_dir.name, "--json", str(out)],
                       cwd=ROOT, capture_output=True, text=True, timeout=3600)
    try:
        r = json.loads(out.read_text())
    except (OSError, ValueError):
        return {"pass": False, "tests": {}, "tests_passed": 0, "tests_total": 0, "error": f"the bench did not run (exit {p.returncode})"}
    tests = r.get("tests") or {}
    return {"pass": bool(r.get("pass")), "tests": tests, "tests_passed": sum(1 for v in tests.values() if v), "tests_total": len(tests), **({"error": str(r["error"])[:200]} if r.get("error") else {})}


def take_slot(prefix: str, text_job: str, hours: float = 4.0) -> tuple[Path | None, str | None]:
    script = HANDOFF / "take_heavy_slot.sh"
    if not script.is_file():
        return None, None
    end = time.strftime("%H:%M", time.localtime(time.time() + hours * 3600))
    text = f"{prefix}: {text_job} (Vivado impl, peak 4G), {time.strftime('%H:%M')}, expected end {end}"
    while True:
        p = subprocess.run([str(script), text], capture_output=True, text=True)
        if p.returncode == 0:
            return Path(p.stdout.strip().splitlines()[-1]), text
        print("waiting for a heavy slot ...", file=sys.stderr)
        time.sleep(60)


def release_slot(lock: Path | None, text: str | None) -> None:
    """Only a lock whose text is ours (owner-checked release)."""
    if lock is not None and text is not None:
        try:
            if lock.read_text().strip() == text.strip():
                lock.unlink()
        except OSError:
            pass


def find_run(name: str, since: float) -> Path | None:
    cands = []
    for p in RUNS.glob("*/config.json"):
        try:
            if p.stat().st_mtime >= since - 2 and json.loads(p.read_text()).get("name") == name:
                cands.append(p.parent)
        except (OSError, ValueError):
            continue
    return sorted(cands)[-1] if cands else None


def run_example(name: str, *, max_usd: float | None = None, slot: bool = True, allow_unpinned: bool = False, dry_run: bool = False, python: str | None = None,
                prefix: str | None = None, results: Path | None = None) -> dict[str, Any]:
    reg = R.load()
    e = R.get(name, reg)
    pins = reg["pins"]
    pre = R.check(pins, allow_unpinned)
    py = python or sys.executable
    cmd = R.argv(e, pins, py, max_usd)
    info: dict[str, Any] = {"example": name, "command": cmd[1:], "preflight": pre, "refused": None}
    if not pre["ok"]:
        info["refused"] = "pre-flight: " + "; ".join(f"{c['name']}: {c['detail']}" for c in pre["checks"] if not c["ok"] and c["name"] not in pre["unpinned_waived"])
        return info
    if dry_run:
        return info
    lock, text = (take_slot(prefix or os.environ.get("FDA_SLOT_PREFIX", "example"), f"agent run {name}") if slot else (None, None))
    started = time.time()
    try:
        env = {**os.environ, **pre["env"]}
        rc = subprocess.run(cmd, cwd=ROOT, env=env).returncode
    finally:
        release_slot(lock, text)
    wall = time.time() - started
    run_dir = find_run(f"ex_{name}", started)
    info.update(exit_code=rc, run_dir=str(run_dir) if run_dir else None, wall_s=round(wall, 1))
    if run_dir is None:
        info["refused"] = "the run left no run directory"
        return info
    sc = score(e, run_dir, py)
    rec = X.extract(run_dir, name, sc, setup_of(pins, pre), wall_s=round(wall, 1))
    (run_dir / RESULT_FILE).write_text(json.dumps(rec, indent=1) + "\n")
    info["result"] = rec
    info["comparison"] = C.compare(rec, references(name, results))
    return info
