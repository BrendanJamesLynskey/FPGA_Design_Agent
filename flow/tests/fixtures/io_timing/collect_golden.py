#!/usr/bin/env python3
"""Copy the reports flow/io_check.py and the tests read from a run_all.sh output directory into golden/<fixture>/.
    collect_golden.py <run_all.sh out dir>
Per fixture: io_paths.txt, check_timing.rpt, timing_summary.rpt, timing_worst_setup.rpt, timing_worst_hold.rpt,
timing_inputs.rpt / timing_outputs.rpt, clocks.rpt, and vivado.log = that fixture's XDC messages from the group log (the lines
after its "VARIANT <name>" marker, CRITICAL WARNING / ERROR / WARNING lines that name an XDC file)."""
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEEP = ("io_paths.txt", "check_timing.rpt", "timing_summary.rpt", "timing_worst_setup.rpt", "timing_worst_hold.rpt",
        "timing_inputs.rpt", "timing_outputs.rpt", "timing_inputs_edges.rpt", "clocks.rpt")


def main(out: Path) -> None:
    for log in sorted(out.glob("*.log")):
        group = log.stem
        cur, msgs = None, {}
        for line in log.read_text(errors="replace").splitlines():
            m = re.match(r"^VARIANT (\S+)$", line)
            if m:
                cur = m.group(1)
                continue
            if cur and re.match(r"^(CRITICAL WARNING|ERROR|WARNING): .*\.xdc:\d+\]", line):
                msgs.setdefault(cur, []).append(re.sub(r"\[/\S*/(xdc/[^/\]]+\.xdc:\d+)\]", r"[\1]", line))
        for d in sorted((out / group).glob("io_*")):
            if not d.is_dir():
                continue
            g = HERE / "golden" / d.name
            g.mkdir(parents=True, exist_ok=True)
            for k in KEEP:
                if (d / k).exists():
                    shutil.copyfile(d / k, g / k)
            (g / "vivado.log").write_text("\n".join(dict.fromkeys(msgs.get(d.name, []))) + "\n")
            print("golden", d.name)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
