"""The skill index as a small HTTP service (brief 36): the same code as the in-process index
(``agent/core/skill_index.py``), with fastembed and the model inside the image, so a client needs neither.

    POST /search  {"query": str, "k": int, "sections": [str], "mode": "bm25"|"vector"|"hybrid"|null, "names": [str]}
                  -> {"hits": [{name, section, description, path, score, ...}], "mode": str}
    GET  /healthz -> {"mode", "skills", "stale", "model"}

The bank is mounted read-only at ``FDA_KNOWLEDGE`` (default /bank); board and part come from ``FDA_BOARD`` / ``FDA_PART``.
``names`` (optional) limits the answer to the caller's catalogue. Stdlib HTTP only; no write path; the skill text is
data and is never returned (names, sections, descriptions and scores only).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = Path(os.environ.get("FDA_CORE", HERE.parent / "core"))


def _mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)          # type: ignore[union-attr]
    return m


bank_mod = _mod("fda_bank", CORE / "bank.py")
SI = _mod("fda_skill_index", CORE / "skill_index.py")
MAX_BODY = 64_000


def make_index():
    bank = bank_mod.LocalBank(Path(os.environ.get("FDA_KNOWLEDGE", "/bank")))
    ents = SI.entries_from(bank.catalogue(os.environ.get("FDA_BOARD", "nexys_a7_100t"), None,
                                          part=os.environ.get("FDA_PART", "xc7a100tcsg324-1")))
    return SI.SkillIndex(ents, SI.load_vectors(bank.root), SI.local_encoder())


def handler_for(idx):
    class H(BaseHTTPRequestHandler):
        def _send(self, code: int, obj) -> None:
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):  # noqa: N802
            if self.path == "/healthz":
                return self._send(200, {"mode": idx.mode, "skills": len(idx.entries), "stale": len(idx.stale),
                                        "model": getattr(idx.encoder, "model", None)})
            self._send(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if self.path != "/search":
                return self._send(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._send(413, {"error": "request too large"})
            try:
                req = json.loads(self.rfile.read(n) or b"{}")
                q = str(req["query"])[:4000]
                k = max(1, min(int(req.get("k") or 8), 50))
                mode = req.get("mode") if req.get("mode") in ("bm25", "vector", "hybrid") else None
                secs = [str(x) for x in (req.get("sections") or [])][:20]
            except Exception as e:
                return self._send(400, {"error": f"bad request: {type(e).__name__}"})
            names = set(req.get("names") or [])
            hits = [h for h in idx.search(q, k=len(idx.entries), sections=secs, mode=mode) if not names or h["name"] in names]
            self._send(200, {"hits": hits[:k], "mode": mode or idx.mode})

        def log_message(self, fmt, *args):      # quiet: no request bodies in the log
            pass
    return H


def main() -> int:
    idx = make_index()
    port = int(os.environ.get("PORT", "8088"))
    print(json.dumps({"listening": port, "mode": idx.mode, "skills": len(idx.entries)}), flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), handler_for(idx)).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
