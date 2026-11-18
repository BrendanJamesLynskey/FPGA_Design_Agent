#!/usr/bin/env python3
"""Make a buildable latency variant of the b96 design (brief 97): <design>/lat_<name>/ holds only the RTL files that differ from the base
(`rtl/`), a build.yaml that points each source at the variant's copy where there is one and at the base otherwise, the base's
architecture.yaml, and variant.json (parent, the files changed, the sha of the whole source set, where the change came from).

    python3 designs/b96_kr260_10g/scripts/make_variant.py <name> <rtl dir with the changed design> [--origin "agent A1 run 2, visit 1"]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import yaml

D = Path(__file__).resolve().parents[1]
ROOT = D.parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("rtl", type=Path)
    ap.add_argument("--origin", default="")
    a = ap.parse_args()
    out = D / f"lat_{a.name}"
    out.mkdir(exist_ok=True)
    rtl_out = out / "rtl"
    shutil.rmtree(rtl_out, ignore_errors=True)
    rtl_out.mkdir()
    changed = []
    for f in sorted(a.rtl.glob("*.sv")):
        base = D / "rtl" / f.name
        if not base.is_file() or base.read_bytes() != f.read_bytes():
            shutil.copy(f, rtl_out / f.name)
            changed.append(f.name)
    bld = yaml.safe_load((D / "build.yaml").read_text())
    bld["sources"] = [f"designs/b96_kr260_10g/lat_{a.name}/rtl/{Path(s).name}" if Path(s).name in changed and "/b96_kr260_10g/rtl/" in s else s
                      for s in bld["sources"]]
    head = f"# Latency variant {a.name} of designs/b96_kr260_10g (brief 97): the base's sources, with {', '.join(changed) or 'no file'} replaced by the copy in rtl/.\n"
    (out / "build.yaml").write_text(head + yaml.safe_dump(bld, sort_keys=False))
    shutil.copy(D / "selftest" / "architecture.yaml", out / "architecture.yaml")
    h = hashlib.sha256()
    for s in bld["sources"]:
        h.update((ROOT / s).read_bytes())
    (out / "variant.json").write_text(json.dumps({"name": a.name, "parent": "designs/b96_kr260_10g", "files_changed": changed,
                                                   "sources_sha256": h.hexdigest(), "origin": a.origin}, indent=1) + "\n")
    print(f"{out}: changed {changed}")


if __name__ == "__main__":
    main()
