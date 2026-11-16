#!/usr/bin/env python3
"""Add, replace or revoke an entry in agent/access/keys.json (brief 94). Prints no key and no hash.

    python3 tools/access/set_key_hash.py                       # the owner's key, from .env or the environment
    python3 tools/access/set_key_hash.py --name alice --env-file /path/alice.env --expires 2027-03-31
    python3 tools/access/set_key_hash.py --revoke alice

The key is read from FDA_ACCESS_KEY (environment, else ``--env-file``, default ``.env`` at the repo root). A new salt
is drawn for every add or replace. Only ``keys.json`` is written.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent import access  # noqa: E402


def main(argv: list[str] | None = None, keys_file: Path | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--name", default="owner")
    ap.add_argument("--env-file", type=Path, default=access.ENV_FILE)
    ap.add_argument("--expires", help="YYYY-MM-DD, the last day the key works (default: never)")
    ap.add_argument("--revoke", metavar="NAME", help="disable this entry (it stays in the file)")
    a = ap.parse_args(argv)
    path = keys_file or access.KEYS_FILE
    entries = access.load_entries(path) or []
    if a.revoke:
        hit = [e for e in entries if e["name"] == a.revoke]
        if not hit:
            print(f"no entry named {a.revoke!r}", file=sys.stderr)
            return 1
        hit[0]["enabled"] = False
        msg = f"revoked {a.revoke!r}"
    else:
        key = access.read_key({}, a.env_file) if a.env_file != access.ENV_FILE else access.read_key(None, a.env_file)
        if not key:
            print(f"{access.ENV_NAME} is not set in the environment or in {a.env_file}", file=sys.stderr)
            return 1
        if a.expires:
            dt.date.fromisoformat(a.expires)
        salt = secrets.token_hex(16)
        entry = {"name": a.name, "salt": salt, "sha256": access.hash_key(key, salt),
                 "expires": a.expires, "enabled": True}
        entries = [e for e in entries if e["name"] != a.name] + [entry]
        msg = f"set entry {a.name!r}"
    path.write_text(json.dumps({"version": 1, "entries": entries}, indent=1) + "\n")
    print(f"{msg}; {len(entries)} entries in {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
