"""``python -m flow <command>``: the flow's front door. Only ``inspect`` (brief 118) so far; the other tools are run as ``python -m flow.<module>``."""
from __future__ import annotations

import sys

COMMANDS = {"inspect": "flow.inspect_build"}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in COMMANDS:
        print("usage: python -m flow inspect <designs/name> [options]   (python -m flow inspect -h)", file=sys.stderr)
        return 2
    import importlib
    return importlib.import_module(COMMANDS[argv[0]]).main(argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
