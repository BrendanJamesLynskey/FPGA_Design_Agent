"""b82p2: a build refused only because another Vivado holds the PC's slot waits for the slot instead of failing the gate."""

from __future__ import annotations

from types import SimpleNamespace

from agent.graph import run as R

BUSY = {"ok": False, "refused": False, "output": "run_vivado: 1 Vivado job(s) running (PIDs 1), limit FDA_VIVADO_MAX=1 on this PC"}


def _rt(tmp_path):
    return SimpleNamespace(session=None, run_dir=tmp_path, last_build_output="")


def _patch(monkeypatch, replies, slept):
    calls = []

    def fake_dispatch(_s, tool, args):
        if tool == "build":
            calls.append(args)
            return replies[min(len(calls), len(replies)) - 1]
        return {"gates": {"ok": True}}

    monkeypatch.setattr(R, "dispatch", fake_dispatch)
    monkeypatch.setattr(R, "_sources_hash", lambda rt: "h")
    monkeypatch.setattr(R.time, "sleep", lambda s: slept.append(s))
    return calls


def test_a_busy_slot_is_waited_for_and_not_cached_as_a_failure(tmp_path, monkeypatch) -> None:
    slept: list = []
    calls = _patch(monkeypatch, [BUSY, BUSY, {"ok": True, "returncode": 0}], slept)
    out = R._build(_rt(tmp_path), "synth")
    assert out["build"]["ok"] is True and len(calls) == 3 and slept == [R.VIVADO_POLL_S] * 2


def test_the_wait_is_bounded_and_a_real_failure_is_not_waited_for(tmp_path, monkeypatch) -> None:
    slept: list = []
    monkeypatch.setenv("FDA_VIVADO_WAIT_S", "90")
    calls = _patch(monkeypatch, [BUSY], slept)
    rt = _rt(tmp_path)
    assert R._build(rt, "synth")["build"]["ok"] is False and len(slept) == 3 and "FDA_VIVADO_MAX" in rt.last_build_output
    slept.clear()
    calls = _patch(monkeypatch, [{"ok": False, "output": "synth_design failed: syntax error"}], slept)
    (tmp_path / "build_cache_base.json").unlink()
    assert R._build(_rt(tmp_path), "synth")["build"]["ok"] is False and slept == [] and len(calls) == 1
