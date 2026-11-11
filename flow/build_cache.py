#!/usr/bin/env python3
"""Decide whether a Vivado build can reuse an earlier build of the same inputs (brief 33). Called by flow/run_vivado.sh.

    python3 flow/build_cache.py <out> --prev <out>.prev --base <design>/build/base --variant base|ila
                                --vivado <path> --threads N

``<out>`` holds the new build's ``inputs.tcl`` and ``prepare.json`` (flow/prepare.py); ``--prev`` the earlier build
of the same variant, moved aside by the runner. The **flow key** is the SHA-256 of everything that decides the result:
the inputs.tcl lines (top, part, source and XDC lists, generics, ILA switch, power environment, timing margin; not
the output directory or the stop stage), the probes, the content hash of every source, XDC and data file, every
flow/*.tcl script, the thread count, the Vivado binary and the FDA_XPROBE / FDA_RESULT_HASH / FDA_INCREMENTAL
switches. The **synth key** covers only what synthesis reads, so the ILA variant can start from the base build's
post_synth.dcp.

Prints one JSON line, the decision:

- ``hit``: the earlier build has the same flow key and already reached the requested stage. Vivado is not run; the
  runner puts the earlier build back and re-runs the gates on it.
- ``resume_synth`` / ``resume_route``: same key (or, for ILA, the same synth key as the base build) and an earlier
  stage reached: inputs.tcl gets ``resume_from`` and ``resume_dir`` and flow/build.tcl opens that checkpoint.
- ``fresh``: the whole flow from the RTL. With FDA_INCREMENTAL=1 and an earlier routed checkpoint, inputs.tcl gets
  ``incremental_ref``.

FDA_BUILD_CACHE=0 forces ``fresh`` (no reuse at all). Stage ranks: synth 1, place 2, route 3, bitstream 4; a stage
counts as reached when flow/build.tcl logged its last step in stages.txt (synth_reports, place_reports, reports,
bitstream), which it does only after the checkpoint and reports of that stage are written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RANK = {"synth": 1, "place": 2, "route": 3, "bitstream": 4}
# the last stages.txt entry of each stage (flow/build.tcl), and the entries a resumed build logs instead
REACHED = {"synth_reports": 1, "resumed_synth": 1, "place_reports": 2, "reports": 3, "resumed_route": 3,
           "bitstream": 4}
SYNTH_LINES = ("set top ", "set part ", "set sources ", "set constraints ", "set generics ")
SKIP_LINES = ("set out ", "set stop_after ", "set resume_from ", "set resume_dir ", "set incremental_ref ")
SWITCHES = ("FDA_XPROBE", "FDA_RESULT_HASH", "FDA_INCREMENTAL")


def _lines(d: Path) -> list[str]:
    return (d / "inputs.tcl").read_text().splitlines()


def _common(d: Path, vivado: str, threads: str) -> list[str]:
    prep = json.loads((d / "prepare.json").read_text())
    tcl = sorted((ROOT / "flow").glob("*.tcl"))
    return [f"sources_sha256={prep['sources_sha256']}", f"vivado={vivado}", f"threads={threads}",
            *(f"{t.name}={hashlib.sha256(t.read_bytes()).hexdigest()}" for t in tcl)]


def synth_key(d: Path, vivado: str, threads: str) -> str:
    parts = [l for l in _lines(d) if l.startswith(SYNTH_LINES)] + _common(d, vivado, threads)
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def flow_key(d: Path, vivado: str, threads: str, env: dict[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    parts = [l for l in _lines(d) if not l.startswith(SKIP_LINES) and not l.startswith("#")]
    probes = d / "probes.tcl"
    if probes.is_file():
        parts += [l for l in probes.read_text().splitlines() if not l.startswith("#")]
    parts += _common(d, vivado, threads)
    parts += [f"{k}={env.get(k, '0') or '0'}" for k in SWITCHES]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def reached(d: Path) -> int:
    """The highest stage rank the build in ``d`` completed (0: none, or no such build)."""
    f = d / "stages.txt"
    if not f.is_file():
        return 0
    names = [l.split()[0] for l in f.read_text().splitlines() if l.strip()]
    return max((REACHED.get(n, 0) for n in names), default=0)


def _key_file(d: Path, name: str) -> str:
    f = d / name
    return f.read_text().strip() if f.is_file() else ""


def decide(out: Path, prev: Path | None, base: Path | None, variant: str, stop: str, vivado: str, threads: str,
           env: dict[str, str] | None = None) -> dict:
    env = os.environ if env is None else env
    fk, sk = flow_key(out, vivado, threads, env), synth_key(out, vivado, threads)
    want = 4 if variant == "ila" else RANK[stop]
    res: dict = {"action": "fresh", "flow_key": fk, "synth_key": sk, "requested": want}
    if env.get("FDA_BUILD_CACHE", "1") == "0":
        res["why"] = "FDA_BUILD_CACHE=0"
        return res
    if prev is not None and prev.is_dir() and _key_file(prev, "flow_key.txt") == fk:
        got = reached(prev)
        res["prev_reached"] = got
        if got >= want:
            return {**res, "action": "hit", "resume_dir": str(prev)}
        if got >= 3 and (prev / "post_route.dcp").is_file():
            return {**res, "action": "resume_route", "resume_dir": str(prev)}
        if got >= 1 and (prev / "post_synth.dcp").is_file():
            return {**res, "action": "resume_synth", "resume_dir": str(prev)}
    if variant == "ila" and base is not None and base.is_dir() and _key_file(base, "synth_key.txt") == sk \
            and reached(base) >= 1 and (base / "post_synth.dcp").is_file():
        return {**res, "action": "resume_synth", "resume_dir": str(base), "why": "the base build has the same synth key"}
    if env.get("FDA_INCREMENTAL", "0") == "1" and prev is not None and (prev / "post_route.dcp").is_file():
        res["incremental_ref"] = str(prev / "post_route.dcp")
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--prev", type=Path)
    ap.add_argument("--base", type=Path)
    ap.add_argument("--variant", choices=["base", "ila"], default="base")
    ap.add_argument("--vivado", required=True)
    ap.add_argument("--threads", required=True)
    a = ap.parse_args(argv)
    stop = os.environ.get("FDA_STOP_AFTER", "bitstream") or "bitstream"
    d = decide(a.out, a.prev, a.base, a.variant, stop, a.vivado, a.threads)
    (a.out / "flow_key.txt").write_text(d["flow_key"] + "\n")
    (a.out / "synth_key.txt").write_text(d["synth_key"] + "\n")
    extra = []
    if d["action"] in ("resume_synth", "resume_route"):
        extra = [f"set resume_from {d['action'].split('_')[1]}", f"set resume_dir {{{d['resume_dir']}}}"]
    elif d.get("incremental_ref"):
        extra = [f"set incremental_ref {{{d['incremental_ref']}}}"]
    if extra and d["action"] != "hit":
        with (a.out / "inputs.tcl").open("a") as f:
            f.write("\n".join(extra) + "\n")
    print(json.dumps(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
