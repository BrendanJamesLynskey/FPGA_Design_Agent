"""Keep a finished example run as a reference run (brief 195): ``python -m agent example record <name> <run_dir>``.

Copies the run's ``example_result.json`` to ``results/195_repro_examples/<name>/ref_<n>.json`` and the run's RTL to ``ref_<n>_rtl/`` (what ``example tools`` re-scores).
Refuses a record that holds long text or an absolute path, a run that did not use the pinned setup, and a held-out example name. Before pushing a record, run the leak
gate: ``FDA_PROMPTS_DIR=<pinned prompts> FDA_PROMPTS_UNPINNED=1 python -m pytest -q agent/tests/test_99_prompts.py``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from agent.repro import extract as X
from agent.repro import registry as R


def record(name: str, run_dir: Path, results: Path | None = None, allow_unpinned: bool = False) -> Path:
    reg = R.load()
    R.get(name, reg)
    run_dir = Path(run_dir)
    f = run_dir / "example_result.json"
    rec: dict[str, Any] = json.loads(f.read_text())
    if rec.get("example") != name:
        raise R.ExampleError(f"that run is a run of {rec.get('example')!r}, not {name!r}")
    pins, setup = reg["pins"], rec.get("setup") or {}
    wrong = [k for k in ("cc_model", "oracle_cc_model", "verif_level", "harness_arm", "stop_after", "claude_cli_version", "vivado_version") if str(setup.get(k)) != str(pins.get(k))]
    if wrong and not allow_unpinned:
        raise R.ExampleError("not the pinned setup, so not a reference: " + ", ".join(wrong))
    if setup.get("unpinned_waived") and not allow_unpinned:
        raise R.ExampleError("a run with a waived pin is not a reference: " + ", ".join(setup["unpinned_waived"]))
    bad = X.check_no_text(rec)
    if bad:
        raise R.ExampleError("the record holds text or a path: " + "; ".join(bad[:3]))
    d = (results or R.RESULTS) / name
    d.mkdir(parents=True, exist_ok=True)
    n = 1 + max([int(p.stem.split("_")[1]) for p in d.glob("ref_*.json") if p.stem.split("_")[1].isdigit() and p.stem.count("_") == 1] or [0])
    design = X.design_dir(run_dir)
    rec["run_id"] = run_dir.name
    rec["reference"] = n
    out = d / f"ref_{n}.json"
    out.write_text(json.dumps(rec, indent=1) + "\n")
    if design is not None and (design / "rtl").is_dir():
        dest = d / f"ref_{n}_rtl"
        shutil.copytree(design / "rtl", dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        by = design / "build.yaml"
        if by.is_file() and (design / "design.xdc").is_file():          # what `example tools --vivado` needs to rebuild this RTL: the top, the part, the generics and the constraints
            import yaml
            cfg = yaml.safe_load(by.read_text()) or {}
            (d / f"ref_{n}_design.json").write_text(json.dumps({"top": cfg.get("top"), "part": cfg.get("part"), "generics": cfg.get("generics") or {}, "sources": cfg.get("sources"), "constraints": cfg.get("constraints")}, indent=1) + "\n")
            shutil.copyfile(design / "design.xdc", d / f"ref_{n}_design.xdc")
    return out
