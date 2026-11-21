"""The Measurements page's data: the committed eye-scan captures, listed and drawn by flow/eyescan (one implementation, not two).

``flow.eyescan.page.build_page`` is the page the CLI writes (``python -m flow.eyescan page``); the navigator serves that same page for
one capture, or for two (which enables its Compare tab). This module never measures: a scan is a button elsewhere that runs the gated
board tool (``flow/eyescan``'s ``run``, through ``_handoff/board.lock``), and the navigator has no such button.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flow.eyescan import api
from flow.eyescan import capture as C
from navigator import sources as S


def listing(root: Path, extra: list[Path] | None = None) -> list[dict[str, Any]]:
    out = []
    for f in S.capture_files(root, extra):
        try:
            cap = C.load(f)
        except (C.CaptureError, ValueError, OSError):
            continue
        sm = api.summary(cap)
        st = cap["settings"]
        eye = sm.get("eye") or {}
        phase = ((cap.get("selftest") or {}).get("clk_phase") or {}) if isinstance(cap.get("selftest"), dict) else {}
        out.append({"id": S.src(root, f)["file"], "label": cap.get("label"), "synthetic": bool(cap.get("synthetic")), "created": cap.get("created"),
                    "equaliser": st.get("equaliser"), "line_rate_gbps": st.get("line_rate_gbps"), "complete": C.is_complete(cap) if st.get("expected_points") is not None else None,
                    "design": (cap.get("design") or {}).get("name"), "board": (cap.get("design") or {}).get("board"),
                    "no_data": C.no_data_stats(cap)["no_data"], "points": len(cap.get("points") or []), "target_ber": st.get("target_ber"),
                    "width_ui": eye.get("width_ui"), "width_ui_lo": eye.get("width_ui_lo"), "width_ui_hi": eye.get("width_ui_hi"),
                    "height_mv": eye.get("height_mv"), "height_mv_lo": eye.get("height_mv_lo"), "height_mv_hi": eye.get("height_mv_hi"), "counts": eye.get("counts"),
                    "shallow_note": eye.get("shallow_note"), "clk_phase_sel": phase.get("sel") if isinstance(phase.get("sel"), int) else None,
                    "tx": {k: (cap.get("settings") or {}).get("tx", {}).get(k) for k in ("diff", "pre", "post")} if isinstance((cap.get("settings") or {}).get("tx"), dict) else None, "post_equaliser": True,
                    "conditions": cap.get("conditions") or {}, "source": S.src(root, f, created=cap.get("created"))})
    return out


def resolve(root: Path, ids: list[str], extra: list[Path] | None = None) -> list[Path] | None:
    """The files for capture ids, only ids that ``listing`` itself produced (no path from the request is ever opened)."""
    known = {S.src(root, f)["file"]: f for f in S.capture_files(root, extra)}
    if not 1 <= len(ids) <= 2 or any(i not in known for i in ids):
        return None
    return [known[i] for i in ids]


def page(root: Path, ids: list[str], extra: list[Path] | None = None, labels: list[str] | None = None) -> str | None:
    from flow.eyescan import page as P
    files = resolve(root, ids, extra)
    if files is None:
        return None
    return P.build_page([C.load(f) for f in files], labels)
