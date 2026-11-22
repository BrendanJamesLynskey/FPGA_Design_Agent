"""Checks of the prepared out-of-context build descriptions (brief 139b): no Vivado. Used by each function's test_<function>_build_rtl.py."""
from __future__ import annotations

import glob
import re
from pathlib import Path

import yaml

from arith.common import sim
from arith.tools import gen_build

PARTS = {"a7": "xc7a100tcsg324-1", "k26": "xck26-sfvc784-2LV-c"}


def check_descriptions(fn: str) -> list[str]:
    """Problems with arith/<fn>/build: out of date against the generator, a missing source or constraint, a top that does not exist, a generic the
    top does not have, a variant or point without expected primitives, a wrong part."""
    root = gen_build.ROOT
    spec = yaml.safe_load((gen_build.ARITH / fn / "spec.yaml").read_text())
    probs = []
    for p, t in gen_build.outputs().items():
        if fn in p.parts and (not p.exists() or p.read_text() != t):
            probs.append(f"out of date: {p.relative_to(root)}")
    for var in spec["variants"]:
        for fab, part in PARTS.items():
            bp = gen_build.ARITH / fn / "build" / var["id"] / fab / "build.yaml"
            if not bp.exists():
                probs.append(f"missing {bp.relative_to(root)}")
                continue
            b = yaml.safe_load(bp.read_text())
            if b["part"] != part or b["mode"] != "out_of_context" or not b["clock_ns"]:
                probs.append(f"{bp}: part, mode or clock wrong")
            srcs = [f for s in b["sources"] for f in glob.glob(str(root / s))]
            if not srcs:
                probs.append(f"{bp}: no source matches")
            for c in b["constraints"]:
                if not (root / c).exists():
                    probs.append(f"{bp}: constraint {c} missing")
            text = "\n".join(Path(f).read_text() for f in srcs)
            m = re.search(rf"module\s+{b['top']}\s*#\((.*?)\)\s*\(", text, re.S)
            if not m:
                probs.append(f"{bp}: top {b['top']} not found in the sources")
                continue
            tops = set(re.findall(r"parameter\s+(?:int|bit)\s+(\w+)", m.group(1)))
            if not b["points"]:
                probs.append(f"{bp}: no points")
            for pt in b["points"]:
                if not set(pt["generics"]) <= tops:
                    probs.append(f"{bp}: generics {set(pt['generics']) - tops} are not parameters of {b['top']}")
                if pt["generics"].get("VARIANT") != var["selector"]["VARIANT"]:
                    probs.append(f"{bp}: a point's VARIANT differs from the selector's")
                ex = pt["expected_primitives"]
                if not {"carry4", "dsp48", "bram"} <= set(ex):
                    probs.append(f"{bp}: expected_primitives lacks carry4, dsp48 or bram")
            for k in ("variant", "function", "status"):
                if k not in b:
                    probs.append(f"{bp}: no {k}")
    return probs


def lint_wrappers(fn: str, top: str, params_list: list[dict]) -> list[str]:
    root = gen_build.ARITH / fn / "rtl"
    files = sorted(root.glob("*.sv"))
    bad = []
    for params in params_list:
        ok, log = sim.lint(f"{fn}_ooc", files, params)
        if not ok:
            bad.append((params, log[:300]))
    return bad
