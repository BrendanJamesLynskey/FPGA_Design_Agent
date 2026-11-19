"""Brief 106: the core tools stamp builds and simulations, and a gate result read from changed inputs is marked stale."""
from __future__ import annotations

import json

import pytest

from agent.core import dispatch


def _rtl(session):
    return sorted((session.design / "rtl").glob("*.sv"))[0]


def test_build_stamps_and_gates_say_stale_after_an_edit(session) -> None:
    assert dispatch(session, "build", {"until": "synth"})["ok"]
    stamp = json.loads((session.design / "build" / "lineage.json").read_text())["stamps"]["build:base"]
    assert any("/rtl/" in k for k in stamp["inputs"])
    fresh = dispatch(session, "gates", {"kind": "stages"})
    assert "stale" not in fresh and "STALE" not in fresh["output"]
    f = _rtl(session)
    f.write_text(f.read_text() + "\n// edited after the build\n")
    r = dispatch(session, "gates", {"kind": "stages"})
    assert r["stale"]["status"] == "stale" and r["output"].startswith("STALE:")
    assert r["ok"] is True                                  # advisory by default: the note is there, the verdict is the flow's


def test_enforce_makes_a_stale_read_fail(session, monkeypatch: pytest.MonkeyPatch) -> None:
    dispatch(session, "build", {"until": "synth"})
    f = _rtl(session)
    f.write_text(f.read_text() + "\n// edited\n")
    monkeypatch.setenv("FDA_STALE", "enforce")
    assert dispatch(session, "gates", {"kind": "stages"})["ok"] is False


def test_a_rebuild_makes_it_fresh_again(session) -> None:
    dispatch(session, "build", {"until": "synth"})
    f = _rtl(session)
    f.write_text(f.read_text() + "\n// edited\n")
    assert dispatch(session, "gates", {"kind": "stages"}).get("stale")
    dispatch(session, "build", {"until": "synth"})
    assert "stale" not in dispatch(session, "gates", {"kind": "stages"})


def test_a_gate_read_with_no_record_is_unchanged(session) -> None:
    r = dispatch(session, "gates", {"kind": "stages"})
    assert "stale" not in r and not r["output"].startswith("STALE")


def test_the_check_tool_offers_the_new_checks(session) -> None:
    from agent.core.tools import CHECK_NAMES
    assert {"constants", "stale"} <= set(CHECK_NAMES)
