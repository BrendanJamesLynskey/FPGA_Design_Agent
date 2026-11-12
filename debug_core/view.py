"""A capture as one static HTML page (debug_core/viewer.html with the capture embedded): no server, no network, no build.

The page is sober black and white and follows the system's dark mode. It also opens any other ``fda-capture/1`` JSON file
from disk (the "Open capture JSON" button), so the empty template works as a local viewer too.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TEMPLATE = Path(__file__).with_name("viewer.html")


def page(cap: dict[str, Any] | None, answer_text: str = "") -> str:
    html = TEMPLATE.read_text()
    data = json.dumps(cap, separators=(",", ":")).replace("</", "<\\/") if cap is not None else "null"
    return (html.replace("/*CAPTURE_JSON*/null", data, 1)
                .replace('/*ANSWER_TEXT*/""', json.dumps(answer_text).replace("</", "<\\/"), 1))


def write_view(cap: dict[str, Any], out: Path, answer_text: str = "") -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(cap, answer_text))
    return out
