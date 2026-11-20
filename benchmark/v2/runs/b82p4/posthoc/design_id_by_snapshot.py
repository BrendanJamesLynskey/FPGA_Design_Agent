#!/usr/bin/env python3
"""Post-hoc (not part of the pre-registered numbers): the shell DESIGN_ID binding in every stage snapshot of every b82p4 run, read
from each run directory's snap.git, to say whether the derived-constants gate ever had a wrong binding to block.

    python3 design_id_by_snapshot.py <runs dir of the frozen worktree> > design_id_by_snapshot.json
"""
import json
import re
import subprocess
import sys
from pathlib import Path

runs = Path(sys.argv[1])
out = {}
for rd in sorted(p for p in runs.iterdir() if (p / "snap.git").is_dir()):
    g = ["git", f"--git-dir={rd / 'snap.git'}"]
    commits = subprocess.run(g + ["rev-list", "--all"], capture_output=True, text=True).stdout.split()
    seen: dict[str, int] = {}
    for c in commits:
        t = subprocess.run(g + ["grep", "-h", "-o", r"DESIGN_ID *( *[^)]*)", c, "--", "*.sv"], capture_output=True, text=True).stdout
        for m in set(re.findall(r"DESIGN_ID *\( *([^)]*)\)", t)):
            seen[m.strip()] = seen.get(m.strip(), 0) + 1
    out[rd.name] = {"snapshots": len(commits), "bindings_found_in_snapshots": seen}
print(json.dumps(out, indent=1))
