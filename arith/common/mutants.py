"""Seeded-mutant check for the arithmetic library's benches (brief 139b).

A mutant is one text replacement in one RTL file of a function (`verif/mutants.yaml`); it must occur exactly once. The mutated copy of the
function's RTL is simulated under a configuration (variant and parameters) with the function's own stream; the mutant is *killed* when
the bench reports a mismatch, a latency error, a spurious or X valid, or never finishes. A mutant that does not compile is an error, not a kill.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Callable

import yaml

from arith.common import sim


def load(fn_dir: Path, key: str = "mutants") -> list[dict]:
    return yaml.safe_load((fn_dir / "verif" / "mutants.yaml").read_text()).get(key) or []


def apply(src: str, find: str, replace: str, mid: str) -> str:
    n = src.count(find)
    if n != 1:
        raise AssertionError(f"mutant {mid}: pattern occurs {n} times, must occur once: {find!r}")
    return src.replace(find, replace)


def run_all(fn_dir: Path, tb_top: str, make: Callable[[dict], dict], gap_pct: int = 25) -> dict:
    """make(cfg) -> {params, vin, vexp, in_w, out_w, lat}. Returns {total, killed, survivors, rows, equivalent: {id: still_equivalent}}.
    The `equivalent` list of mutants.yaml holds mutants shown to change structure but not behaviour; they are run to confirm they still
    survive (an equivalent mutant that starts failing is a stale claim) and are not counted in total."""
    rtl = fn_dir / "rtl"
    tb = fn_dir / "tb" / f"{tb_top}.sv"
    rows, survivors = [], []
    eq: dict[str, bool] = {}
    for m in load(fn_dir) + [dict(e, equivalent=True) for e in load(fn_dir, "equivalent")]:
        tmp = Path(tempfile.mkdtemp(prefix="arith_mut_"))
        try:
            for f in rtl.glob("*.sv"):
                shutil.copy(f, tmp / f.name)
            p = tmp / m["file"]
            p.write_text(apply(p.read_text(), m["find"], m["replace"], m["id"]))
            c = make(m["config"])
            res = sim.run_stream(tb_top, sorted(tmp.glob("*.sv")), c["params"], c["vin"], c["vexp"], c["in_w"], c["out_w"], c["lat"],
                                 gap_pct=gap_pct, extra_tb=[tb])
            if res.get("compile_error"):
                raise AssertionError(f"mutant {m['id']} does not compile (an invalid mutant is not a kill): {res.get('log')}")
            killed = not sim.ok(res)
            if m.get("equivalent"):
                eq[m["id"]] = not killed
                continue
            rows.append({"id": m["id"], "file": m["file"], "what": m["what"], "killed": killed,
                         "mismatches": res.get("mismatches"), "lat_errors": res.get("lat_errors"), "compile_error": bool(res.get("compile_error"))})
            if not killed:
                survivors.append(m["id"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return {"total": len(rows), "killed": len(rows) - len(survivors), "survivors": survivors, "rows": rows, "equivalent": eq}
