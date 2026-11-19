"""``python -m navigator``: start the navigator on 127.0.0.1 and print the address with this session's token.

    python -m navigator [--port 8765] [--runs DIR] [--captures DIR ...] [--handoff DIR]

It needs the access key like every entry point (``FDA_ACCESS_KEY`` or ``.env``). It never opens a browser by itself and never listens on any
address but 127.0.0.1.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from agent import access

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m navigator", description=__doc__.split("\n", 1)[0])
    ap.add_argument("--port", type=int, default=8765, help="port on 127.0.0.1 (default 8765; 0 picks a free one)")
    ap.add_argument("--runs", type=Path, help="the agent's run directory (default: runs/ in the repository)")
    ap.add_argument("--captures", type=Path, action="append", default=[], help="a directory of eye-scan captures besides results/ (repeatable)")
    ap.add_argument("--handoff", type=Path, default=Path(os.environ.get("FDA_HANDOFF", Path.home() / "Claude_sandbox" / "_handoff")),
                    help="the directory with usage_log.txt, usage_check.sh and the lock files (default $FDA_HANDOFF or ~/Claude_sandbox/_handoff)")
    a = ap.parse_args(argv)
    access.require_or_exit("python -m navigator")
    from navigator.server import App, make_server
    app = App(ROOT, a.handoff, a.runs, extra_captures=a.captures)
    srv = make_server(app, port=a.port)
    print(f"navigator: open http://127.0.0.1:{app.port}/?t={app.token}")
    print("navigator: bound to 127.0.0.1 only; the address above carries this session's token; Ctrl-C stops it")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("navigator: stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
