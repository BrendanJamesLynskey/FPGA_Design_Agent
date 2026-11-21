"""Brief 82P7: count the Vivado jobs running on this PC, by executable.

A job is a process whose argv[0] ends with ``unwrapped/lnx64.o/vivado``. A shell that only names that path later in its command line
(a ``pgrep`` loop waiting for Vivado to finish, a ``bash -c`` wrapper) is not a job, and neither are Vivado's own ``task_worker.tcl``
helpers (synthesis children of a job already counted). ``pgrep -af`` matched the command line, so 82P6's synthesis gate saw a 40-hour
shell as a Vivado job and logged "limit FDA_VIVADO_MAX=1 reached" for most of two runs. ``flow/run_vivado.sh`` makes the same test
with ``awk '$2 ~ ...'`` on ``ps -eo pid=,args=``; this is the Python side (``flow/hw.py``).

    python3 flow/vivado_count.py        # prints the PIDs, one per line
"""
from __future__ import annotations

import re
import subprocess

VIVADO_EXE = re.compile(r"unwrapped/lnx64\.o/vivado$")


def running_pids(ps_text: str) -> list[str]:
    """PIDs of real Vivado jobs in ``ps -eo pid=,args=`` output."""
    out = []
    for line in ps_text.splitlines():
        parts = line.split(None, 2)
        if len(parts) >= 2 and VIVADO_EXE.search(parts[1]) and "task_worker.tcl" not in line:
            out.append(parts[0])
    return out


def running_now() -> list[str]:
    return running_pids(subprocess.run(["ps", "-ww", "-eo", "pid=,args="], capture_output=True, text=True).stdout)


if __name__ == "__main__":
    print("\n".join(running_now()))
