"""``python3 -m flow.checks``: the check suite's command line (see the package docstring)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from flow import checks as C


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m flow.checks", description="Run design checks; print the digest.")
    ap.add_argument("design")
    ap.add_argument("--names", default="all", help="all, or a comma-separated list: " + ", ".join(sorted(C.CHECKS)))
    ap.add_argument("--scope", default="auto", choices=("auto", *C.SCOPES))
    ap.add_argument("--level", default="summary", choices=tuple(C.LEVELS))
    ap.add_argument("--variant", default="base", choices=("base", "ila"))
    ap.add_argument("--vivado", default="never", choices=("auto", "never"),
                    help="auto: run ONE Vivado session for reports the build did not write (take a heavy slot first)")
    ap.add_argument("--json", help="also copy the full result here")
    ap.add_argument("--list", action="store_true", help="list the registry and exit")
    a = ap.parse_args(argv)
    if a.list:
        for n, c in C.CHECKS.items():
            print(f"{n:16} {c.kind:8} {'/'.join(c.scopes):16} {'AMD' if c.amd else 'ours/AMD+ours':14} {c.summary}")
        return 0
    rep = C.run(Path(a.design), a.names, a.scope, a.level, a.variant,
                vivado=C.cli_vivado if a.vivado == "auto" else None)
    print(rep["digest"])
    if a.json:
        Path(a.json).write_text(json.dumps({k: v for k, v in rep.items() if k != "digest"}, indent=1, default=str) + "\n")
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
