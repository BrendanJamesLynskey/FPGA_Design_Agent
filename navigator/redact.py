"""What the navigator may send to a browser: nothing that looks like a key, token or prompt text.

The data readers (``sources.py``) copy named fields only, so a new field in a run record is not shown until someone adds it. This
module is the second line: every response passes ``scrub`` on its way out, which drops keys whose names say they hold a secret, an identity or
prompt text (names are lower-cased and stripped of ``-`` and ``_``, then matched by substring), and replaces strings that look like a credential.
"""

from __future__ import annotations

import re
from typing import Any

DENY_SUB = ("key", "token", "secret", "passw", "auth", "credential", "bearer", "cookie", "salt", "prompt", "message", "content", "text", "transcript", "stderr", "stdout",
            "account", "email", "orgid", "login", "session", "reply", "question", "answer", "instruction", "completion", "response", "body", "raw", "history", "system", "env")
#: names that contain a denied word but are numbers, hashes or labels the pages need
ALLOW = {"key_state", "key_env", "prompt_tokens", "completion_tokens", "tokens", "fingerprints", "fp_note", "user_fp", "system_fp", "history_note", "hash", "layers"}
SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}|xox[bap]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{12,}|AIza[0-9A-Za-z_-]{20,}|"
                    r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}|(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{12,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
                    r"(?:FDA_ACCESS_KEY|OPENROUTER_API_KEY|ANTHROPIC_API_KEY|CLAUDE_CODE_OAUTH_TOKEN)\s*=\s*\S+)")
REPLACED = "[redacted]"


def _denied(k: str) -> bool:
    if k in ALLOW:
        return False
    n = k.lower().replace("-", "").replace("_", "")
    if n.endswith("tokens"):
        return False
    return any(w in n for w in DENY_SUB)


def scrub(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: scrub(v) for k, v in o.items() if not (isinstance(k, str) and _denied(k))}
    if isinstance(o, (list, tuple)):
        return [scrub(v) for v in o]
    if isinstance(o, str):
        return SECRET.sub(REPLACED, o)
    return o


def text(s: str) -> str:
    return SECRET.sub(REPLACED, s)


def brief(s: str, n: int = 80) -> str:
    """First line of a tool's error output, capped: never a traceback, never a long fragment."""
    lines = (s or "").strip().splitlines()
    return text(lines[0][:n]) if lines else ""
