"""What the navigator may send to a browser: nothing that looks like a key, token or prompt text.

The data readers (``sources.py``) copy named fields only, so a new field in a run record is not shown until someone adds it. This
module is the second line: every response passes ``scrub`` on its way out, which drops keys whose names say they hold a secret or prompt
text and replaces strings that look like a credential.
"""

from __future__ import annotations

import re
from typing import Any

#: key names whose values are never sent (lower case; matched as whole names or as a suffix after an underscore)
DENY_KEYS = {"prompt", "prompts_text", "system_prompt", "user_message", "messages", "message", "content", "text", "reply", "question", "stderr_tail",
             "key", "api_key", "apikey", "token", "secret", "password", "passwd", "authorization", "cookie", "email", "orgid", "org_id",
             "access_key", "salt", "env"}
DENY_SUFFIX = ("_key", "_token", "_secret", "_password", "_prompt")
#: strings that look like a credential
SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}|xox[bap]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{12,}|"
                    r"Bearer\s+[A-Za-z0-9._~+/=-]{12,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
                    r"(?:FDA_ACCESS_KEY|OPENROUTER_API_KEY|ANTHROPIC_API_KEY|CLAUDE_CODE_OAUTH_TOKEN)\s*=\s*\S+)")
REPLACED = "[redacted]"


def _denied(k: str) -> bool:
    k = k.lower()
    return k in DENY_KEYS or k.endswith(DENY_SUFFIX)


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
