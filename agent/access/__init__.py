"""The access gate (brief 94): the agent starts only with a key whose salted hash is committed.

What it is for: keeping casual users of a checkout from running the agent while it is developed. What it is not:
protection against someone who edits the code (they can delete the check); the licence (``LICENSE``) is what forbids
that. See ``agent/access/README.md``.

``agent/access/keys.json`` is a small list of named entries, each with its own salt::

    {"version": 1, "entries": [{"name": "owner", "salt": "<hex>", "sha256": "<hex>",
                                "expires": "2027-01-31" | null, "enabled": true}]}

The gate accepts a key that matches any entry that is enabled and not past its ``expires`` date. It records only the
entry's name, never the key. When the file is absent the gate is **not armed**: every entry point runs and says so
once. Once the file exists, an entry point without a valid key refuses with a one-line message.

The key is read from ``FDA_ACCESS_KEY`` in the environment, else from a git-ignored ``.env`` at the repo root.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KEYS_FILE = Path(__file__).resolve().parent / "keys.json"
ENV_NAME = "FDA_ACCESS_KEY"
ENV_FILE = ROOT / ".env"

#: The entry (name) that admitted this process, or None (unarmed, or not yet checked). Never holds the key.
CURRENT: str | None = None
#: Set only by the test suite's conftest, for in-process tests of entry points; gate tests turn it off.
_TEST_BYPASS = False
_NOTICE_DONE = False


class AccessDenied(Exception):
    """No valid key: the message names the variable and ``.env.example`` and never contains a key value."""


def hash_key(key: str, salt_hex: str) -> str:
    return hashlib.sha256(bytes.fromhex(salt_hex) + key.encode("utf-8")).hexdigest()


def load_entries(path: Path | None = None) -> list[dict] | None:
    """The committed entries, or None when the file is absent (gate not armed)."""
    p = path or KEYS_FILE
    if not p.is_file():
        return None
    return list(json.loads(p.read_text()).get("entries", []))


def read_dotenv(path: Path, name: str = ENV_NAME) -> str | None:
    """A tiny ``.env`` reader: ``NAME=value`` lines, optional quotes, ``#`` comments. No other syntax."""
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        return None
    return None


def read_key(env: dict | None = None, env_file: Path | None = None) -> str | None:
    e = os.environ if env is None else env
    return (e.get(ENV_NAME) or "").strip() or read_dotenv(env_file or ENV_FILE) or None


def _live(entry: dict, today: _dt.date) -> bool:
    if not entry.get("enabled", True):
        return False
    exp = entry.get("expires")
    return not exp or today <= _dt.date.fromisoformat(exp)


def match(key: str | None, entries: list[dict], today: _dt.date | None = None) -> str | None:
    """The name of the first enabled, unexpired entry the key matches, else None. Every live entry is compared."""
    if not key:
        return None
    today = today or _dt.date.today()
    found = None
    for e in entries:
        if _live(e, today) and hmac.compare_digest(hash_key(key, e["salt"]), e["sha256"]) and found is None:
            found = e["name"]
    return found


def require(entry_point: str, *, env: dict | None = None, env_file: Path | None = None,
            keys_file: Path | None = None, today: _dt.date | None = None) -> str | None:
    """Call first thing in every entry point that runs the agent. Returns the admitting entry's name (None when the
    gate is not armed); raises :class:`AccessDenied` when armed and the key is missing, wrong, revoked or expired."""
    global CURRENT, _NOTICE_DONE
    if _TEST_BYPASS and keys_file is None and env is None:
        return None
    entries = load_entries(keys_file)
    if entries is None:
        if not _NOTICE_DONE:
            _NOTICE_DONE = True
            print("fda access: gate not armed (agent/access/keys.json absent): running without a key", file=sys.stderr)
        return None
    name = match(read_key(env, env_file), entries, today)
    if name is None:
        raise AccessDenied(f"{entry_point}: access key required: set {ENV_NAME} in the environment or in .env "
                           f"(see .env.example); it is missing, wrong, revoked or expired")
    CURRENT = name
    return name


def require_or_exit(entry_point: str) -> str | None:
    """:func:`require`, but a refusal is one line on stderr and exit status 2 (for ``main`` functions)."""
    try:
        return require(entry_point)
    except AccessDenied as e:
        print(f"fda access: {e}", file=sys.stderr)
        raise SystemExit(2) from None
