"""A recorded Messages API response as a fake streamed response (brief 224). ``StreamResp(d)`` takes the non-streaming body shape
(``content``, ``usage``, ``stop_reason``) and iterates as the server-sent events the API would send for it; tests only, no network."""
from __future__ import annotations

import json


def events(d: dict, *, split: int = 3, drop_after: int | None = None, error: dict | None = None):
    """The event dicts of ``d``. ``split``: text and tool-call JSON are sent in pieces of this many characters. ``drop_after``: stop after
    that many events (a dropped connection). ``error``: end with an error event instead of ``message_stop``."""
    u = dict(d.get("usage") or {})
    out_tokens = u.pop("output_tokens", 0)
    ev: list[dict] = [{"type": "message_start", "message": {"id": "m", "role": "assistant", "content": [], "usage": {**u, "output_tokens": 1}}}]
    for i, b in enumerate(d.get("content") or []):
        if b["type"] == "text":
            ev.append({"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}})
            t = b["text"]
            for j in range(0, len(t), split):
                ev.append({"type": "content_block_delta", "index": i, "delta": {"type": "text_delta", "text": t[j:j + split]}})
        elif b["type"] == "tool_use":
            ev.append({"type": "content_block_start", "index": i, "content_block": {"type": "tool_use", "id": b["id"], "name": b["name"], "input": {}}})
            t = b.get("raw_json") if b.get("raw_json") is not None else json.dumps(b.get("input") or {})
            for j in range(0, len(t), split):
                ev.append({"type": "content_block_delta", "index": i, "delta": {"type": "input_json_delta", "partial_json": t[j:j + split]}})
        elif b["type"] == "thinking":
            ev.append({"type": "content_block_start", "index": i, "content_block": {"type": "thinking", "thinking": ""}})
            ev.append({"type": "content_block_delta", "index": i, "delta": {"type": "thinking_delta", "thinking": b.get("thinking", "")}})
        ev.append({"type": "content_block_stop", "index": i})
    ev.append({"type": "message_delta", "delta": {"stop_reason": d.get("stop_reason") or "end_turn"}, "usage": {"output_tokens": out_tokens}})
    if error is not None:
        ev.append({"type": "error", "error": error})
    else:
        ev.append({"type": "message_stop"})
    return ev[:drop_after] if drop_after is not None else ev


class StreamResp:
    def __init__(self, d: dict, **kw):
        self.d, self.kw = d, kw

    def read(self):
        return json.dumps(self.d).encode()

    def __iter__(self):
        for e in events(self.d, **self.kw):
            yield f"event: {e['type']}\n".encode()
            yield f"data: {json.dumps(e)}\n".encode()
            yield b"\n"
            if e["type"] == "content_block_delta":
                yield b"event: ping\n"
                yield b'data: {"type": "ping"}\n'
                yield b"\n"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False
