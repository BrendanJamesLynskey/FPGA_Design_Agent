"""Brief 218 in the agent: the two flags are off by default, change nothing when off, and the gate step applies only where the loop can help
(agent/graph/covsva.py). The roles and the rounds are covered with fakes in flow/tests/test_218_coverage_loop.py; no model is called here."""
from __future__ import annotations

import json
from types import SimpleNamespace

from agent.graph import covsva
from agent.graph.run import Config
from flow import coverage_loop as CL


def rt(tmp_path, loop="off", sva="off", level="V3"):
    cfg = SimpleNamespace(coverage_loop=loop, req_sva=sva, verif_level=level)
    return SimpleNamespace(cfg=cfg, design=tmp_path, visit=2, meter=SimpleNamespace(run={"tokens": 1234, "usd": 0.5}), run_dir=tmp_path)


def ev(failed: dict | None = None, reached="V2", lint=True, sim=True):
    checks = {"functional_bins_unhit": {"pass": True, "value": []}}
    for k, v in (failed or {}).items():
        checks[k] = {"pass": False, "value": v, "threshold": 0}
    return {"lint": {"ok": lint}, "simulate": {"ok": sim}, "verif": {"reached": reached, "stages": {"V3": {"checks": checks}}, "code_coverage_unhit": {}}}


def test_both_flags_are_off_by_default():
    import dataclasses
    d = {f.name: f.default for f in dataclasses.fields(Config)}
    assert d["coverage_loop"] == "off" and d["req_sva"] == "off"


def test_the_cli_carries_the_flags_and_a_resumed_run_keeps_them():
    from agent.__main__ import config_from_json
    base = {"spec_md": "s.md", "name": "n", "board": "b", "interview": "off", "review": "off", "model": "m"}
    c = config_from_json({**base, "coverage_loop": "on", "req_sva": "on"})
    assert (c.coverage_loop, c.req_sva) == ("on", "on")
    c = config_from_json(base)
    assert (c.coverage_loop, c.req_sva) == ("off", "off")


def test_the_loop_does_not_run_when_off_or_when_v3_is_not_about_stimulus(tmp_path):
    e = ev({"functional_bins_unhit": ["a:b"]})
    assert covsva.coverage_gate(rt(tmp_path, "off"), e, None, []) is None                       # the flag
    assert covsva.coverage_gate(rt(tmp_path, "on", level="V2"), e, None, []) is None            # not V3
    assert covsva.coverage_gate(rt(tmp_path, "on"), ev({"functional_bins_unhit": ["a:b"]}, lint=False), None, []) is None
    assert covsva.coverage_gate(rt(tmp_path, "on"), ev({"functional_bins_unhit": ["a:b"]}, sim=False), None, []) is None
    assert covsva.coverage_gate(rt(tmp_path, "on"), ev({"functional_bins_unhit": ["a:b"]}, reached="V1"), None, []) is None
    assert covsva.coverage_gate(rt(tmp_path, "on"), ev({"seeds_run": 1}), None, []) is None      # a seed count is not stimulus
    assert not CL.log_path(tmp_path).exists()


def test_the_sva_step_does_nothing_when_off(tmp_path):
    assert covsva.sva_step(rt(tmp_path, sva="off")) is None


def test_the_passive_record_is_written_in_either_arm_and_never_raises(tmp_path):
    r = rt(tmp_path)
    covsva.observe(r, ev({"functional_bins_unhit": ["t1.op:A", "t1.op:B"]}))
    covsva.observe(r, {"verif": {"stages": {}}})                          # no V3: nothing written
    covsva.observe(r, {})                                                 # nothing at all: no error
    lines = (tmp_path / "build" / "verif" / "coverage_visits.jsonl").read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["holes"] == ["bin:t1.op:A", "bin:t1.op:B"] and rec["tokens"] == 1234 and rec["visit"] == 2 and rec["loop"] is False
