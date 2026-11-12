#!/usr/bin/env python3
"""Stage and summarise a SystemVerilog reference and its VHDL translation for the same Vivado gates (brief 55).

    python3 tools/vhdl_pair_build.py stage <task_dir> <vhdl rtl dir>     -> prints the two design directories
    python3 tools/vhdl_pair_build.py summary <task_dir> <out dir>        -> <out>/<id>__sv.json and <id>__vhdl.json

``stage`` uses benchmark/tools/ref_build.py's staging for the reference (build/bench/<id>: ref/rtl, the XDC generated from
the task's spec, a generated architecture.yaml) and makes build/bench/<id>__vhdl beside it with the same XDC and the
VHDL files (sources rtl/*.vhd, the `.hdl` marker, the architecture's blocks named after the VHDL entities). Build both with
flow/run_vivado.sh <dir> base under a heavy slot (the caller's job), then ``summary`` writes ref_build's summary of each
(gates, timing, utilisation, power, run cost) plus the design-standards result.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark.tools import ref_build  # noqa: E402
from flow import vhdl  # noqa: E402


def stage(task: Path, vrtl: Path) -> tuple[Path, Path]:
    task = task.resolve()
    sv = ref_build.stage(task)
    vd = sv.with_name(sv.name + "__vhdl")
    shutil.rmtree(vd, ignore_errors=True)
    (vd / "rtl").mkdir(parents=True)
    for f in sorted(vrtl.iterdir()):
        if vhdl.is_vhdl(f):
            shutil.copy2(f, vd / "rtl" / f.name)
    shutil.copy2(sv / "design.xdc", vd / "design.xdc")
    arch = yaml.safe_load((sv / "architecture.yaml").read_text())
    ents = sorted({e for f in (vd / "rtl").iterdir() for e in re.findall(r"^\s*entity\s+(\w+)\s+is", f.read_text(), re.M | re.I)})
    arch["blocks"] = [{"name": e, "function": "VHDL translation of the reference"} for e in ents] + \
        [b for b in arch["blocks"] if b["name"] == "fpga_shell"]
    (vd / "architecture.yaml").write_text(yaml.safe_dump(arch, sort_keys=False))
    cfg = yaml.safe_load((sv / "build.yaml").read_text())
    cfg["sources"] = ["shell/rtl/*.sv", f"{vd.relative_to(ROOT)}/rtl/*.vhd"]
    cfg["constraints"] = [f"{vd.relative_to(ROOT)}/design.xdc"]
    (vd / "build.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    (vd / vhdl.HDL_MARKER).write_text("vhdl\n")
    return sv, vd


def summary(task: Path, out: Path) -> list[Path]:
    task = task.resolve()
    sv = ROOT / "build" / "bench" / task.name
    written = []
    for lang, d in (("sv", sv), ("vhdl", sv.with_name(sv.name + "__vhdl"))):
        if not (d / "build" / "base" / "gates.json").is_file():
            continue
        sj = d / "build" / "base" / "standards.json"
        subprocess.run([sys.executable, str(ROOT / "flow" / "standards_check.py"), str(d), "--stage", "all", "--json", str(sj)],
                       cwd=ROOT, capture_output=True)
        st = json.loads(sj.read_text()) if sj.is_file() else None
        s = ref_build.summary(task, d, st)
        s["language"] = lang
        if st:
            s["standards_failing"] = [r["id"] for r in st["rules"] if r["status"] in ("fail", "not_run")]
        out.mkdir(parents=True, exist_ok=True)
        p = out / f"{task.name}__{lang}.json"
        p.write_text(json.dumps(s, indent=2) + "\n")
        written.append(p)
    return written


def main(argv: list[str] | None = None) -> int:
    a = sys.argv[1:] if argv is None else argv
    if len(a) == 3 and a[0] == "stage":
        sv, vd = stage(Path(a[1]), Path(a[2]))
        print(sv.relative_to(ROOT))
        print(vd.relative_to(ROOT))
        return 0
    if len(a) == 3 and a[0] == "summary":
        for p in summary(Path(a[1]), Path(a[2])):
            print(p)
        return 0
    sys.exit(__doc__)


if __name__ == "__main__":
    raise SystemExit(main())
