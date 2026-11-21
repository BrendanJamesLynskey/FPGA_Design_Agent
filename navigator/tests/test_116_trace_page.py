"""Brief 116: the navigator's Traceability page reads flow/trace_v1.py's data and shows only what the code computed."""
import json
from pathlib import Path

from navigator.tests.test_103_navigator import Live, make_app

ROOT = Path(__file__).resolve().parents[2]


def test_trace_endpoint_returns_every_design_with_computed_statuses(tmp_path):
    app, _ = make_app(tmp_path)
    s = Live(app)
    try:
        st, _, body = s.get("/api/trace")
    finally:
        s.srv.shutdown()
    assert st == 200
    d = json.loads(body)
    assert "b96_kr260_10g" in {g["design"] for g in d["designs"]}
    b = next(g for g in d["designs"] if g["design"] == "b96_kr260_10g")
    assert {i["status"] for i in b["items"]} <= {"pass", "fail", "not_run", "stale", "bounded", "unapproved"}
    assert any(r.get("external") for r in b["requirements"])
    assert any(i["method"] == "board_measurement" and i.get("instrument") for i in b["items"])


def test_page_is_in_the_nav_and_draws_text_not_html():
    js = (ROOT / "navigator" / "static" / "app.js").read_text()
    assert '["trace", "Traceability"]' in js and "trace: pageTrace" in js
    assert "innerHTML" not in js
