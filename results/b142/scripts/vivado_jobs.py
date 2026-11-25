#!/usr/bin/env python3
"""Write the Tcl job list for vivado_ooc.tcl.

    python3 vivado_jobs.py synth --part xck26-sfvc784-2LV-c --out WORK/jobs_k26.tcl [--names ...]
    python3 vivado_jobs.py edif  --part ... --edif-dir DIR --family xcup --variant flat --stage impl --names ...
Work directories are WORK/<arm>/<name>; the clock is 2.0 ns on UltraScale+ and 3.5 ns on 7 series (a stress target: paths report their
slack, and only the logic level and utilisation of the synthesis-stage jobs are used from it).
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from manifest import BENCH  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("kind", choices=["synth", "edif"])
ap.add_argument("--part", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--work", required=True)
ap.add_argument("--arm", default=None)
ap.add_argument("--names", nargs="*")
ap.add_argument("--stage", default="synth")
ap.add_argument("--clock", type=float)
ap.add_argument("--edif-dir")
ap.add_argument("--family")
ap.add_argument("--variant")
ap.add_argument("--jpart", action="store_true", help="write the part into every job (a ninth field) so job files with different parts can be concatenated")
ap.add_argument("--append", action="store_true", help="append the jobs to --out (which must already exist) instead of writing it")
a = ap.parse_args()
clock = a.clock or (2.0 if a.part.startswith("xck26") else 3.5)
arm = a.arm or ("viv_default" if a.kind == "synth" else f"ys_{a.variant}")
jobs = []
for n in a.names or list(BENCH):
    b = BENCH[n]
    wd = f"{a.work}/{arm}/{n}"
    if a.kind == "synth":
        gen = " ".join("{%s=%s}" % kv for kv in b["generics"].items())
        jobs.append(f"{{{n} {b['top']} {wd} {clock} rtl {a.stage} {{{' '.join(map(str, b['sources']))}}} {{{gen}}}" + (f" {a.part}" if a.jpart else "") + "}")
    else:
        e = f"{a.edif_dir}/{a.family}/{a.variant}/{n}.edif"
        jobs.append(f"{{{n} {b['top']} {wd} {clock} edif {a.stage} {{{e}}} {{}}}}")
if a.append:
    t = Path(a.out).read_text().rstrip()
    assert t.endswith("}")
    Path(a.out).write_text(t[:-1] + "\n".join(jobs) + "\n}\n")
else:
    Path(a.out).write_text(f"set ooc(part) {a.part}\nset ooc(jobs) {{\n" + "\n".join(jobs) + "\n}\n")
print(f"{len(jobs)} jobs -> {a.out}")
