"""Brief 100: the RapidWright tools. Argument validation, the fixed argv, refusal outside the design, and the no-RapidWright path (CI has no
RapidWright, no Vivado and no device files, so every test here uses a fake runner)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.core import dispatch
from agent.core import rapidwright_tools as rt
from flow import rapidwright_pin as pin


@pytest.fixture()
def rwenv(session, monkeypatch):
    """A session whose design has build/base/post_route.dcp, with RapidWright reported as installed."""
    b = session.design / "build" / "base"
    b.mkdir(parents=True, exist_ok=True)
    (b / "post_route.dcp").write_bytes(b"x")
    monkeypatch.setattr(pin, "available", lambda: (True, ""))
    return session


def test_status_without_rapidwright(session, monkeypatch):
    monkeypatch.setattr(pin, "available", lambda: (False, "RapidWright venv not installed"))
    r = dispatch(session, "rw_status", {})
    assert r["ok"] is False and r["available"] is False and "not installed" in r["output"]
    r = dispatch(session, "rw_route", {"checkpoint": "post_route.dcp", "output": "o.dcp", "mode": "full"})
    assert r["ok"] is False and r["refused"] is True and "no checkpoint" in r["output"]       # refuses before it looks for the tool


def test_tools_say_so_when_not_installed(rwenv, monkeypatch):
    monkeypatch.setattr(pin, "available", lambda: (False, "RapidWright venv not installed"))
    r = dispatch(rwenv, "rw_route", {"checkpoint": "post_route.dcp", "output": "o.dcp", "mode": "full"})
    assert r["ok"] is False and "not installed" in r["output"] and not rwenv.runner.calls


def test_relocate_builds_a_fixed_argv(rwenv):
    r = dispatch(rwenv, "rw_relocate_block", {"checkpoint": "post_route.dcp", "output": "moved.dcp", "target_site": "SLICE_X41Y70"})
    kind, argv = rwenv.runner.calls[0]
    assert kind == "rw_relocate" and argv[1] == "-I" and argv[2].endswith("flow/rw/relocate.py") and argv[3] == "moveto"
    assert argv[4].endswith("build/base/post_route.dcp") and argv[5].endswith("build/base/rw/moved.dcp") and argv[6] == "SLICE_X41Y70"
    assert r["ok"] is False        # the fake runner printed no JSON line


@pytest.mark.parametrize("args", [
    {"checkpoint": "../post_route.dcp", "output": "o.dcp", "target_site": "SLICE_X1Y1"},
    {"checkpoint": "post_route.dcp", "output": "a/b.dcp", "target_site": "SLICE_X1Y1"},
    {"checkpoint": "post_route.dcp", "output": "o.dcp", "target_site": "SLICE_X1Y1; rm -rf /"},
    {"checkpoint": "post_route.dcp", "output": "o.dcp", "target_site": "BUFG_X0Y0"},
])
def test_relocate_refuses_bad_arguments(rwenv, args):
    r = dispatch(rwenv, "rw_relocate_block", args)
    assert r["ok"] is False and (r["refused"] or "pattern" in r["output"] or "match" in r["output"]) and not rwenv.runner.calls


def test_place_chain_writes_its_config_and_argv(rwenv):
    dispatch(rwenv, "rw_place_chain", {"checkpoint": "post_route.dcp", "output": "placed.dcp", "cells": ["u_pcs/*", "u_mac/x_d_reg[*]"],
                                       "anchor": "GTHE4_CHANNEL_X0Y6", "seed": 7})
    kind, argv = rwenv.runner.calls[0]
    cfg = json.loads(Path(argv[5]).read_text())
    assert kind == "rw_place" and cfg["anchor"] == "GTHE4_CHANNEL_X0Y6" and cfg["cells"] == ["u_pcs/*", "u_mac/x_d_reg[*]"]
    assert argv[-4:] == ["--seed", "7", "--iters", "200000"]


def test_route_nets_needs_names(rwenv):
    r = dispatch(rwenv, "rw_route", {"checkpoint": "post_route.dcp", "output": "r.dcp", "mode": "nets"})
    assert r["ok"] is False and r["refused"] is True
    dispatch(rwenv, "rw_route", {"checkpoint": "post_route.dcp", "output": "r.dcp", "mode": "nets", "nets": ["u_pcs/n[3]", "net_a"]})
    argv = rwenv.runner.calls[0][1]
    assert Path(argv[-1]).read_text().split() == ["u_pcs/n[3]", "net_a"]


def test_referee_runs_vivado_not_rapidwright(rwenv):
    dispatch(rwenv, "rw_referee", {"checkpoint": "post_route.dcp", "route": True})
    kind, argv = rwenv.runner.calls[0]
    assert kind == "rw_referee" and argv[0].endswith("vivado") and argv[-1].endswith("flow/rw/referee.tcl")


def test_enabled_needs_the_switch(monkeypatch):
    monkeypatch.setattr(pin, "available", lambda: (True, ""))
    monkeypatch.delenv("FDA_RAPIDWRIGHT", raising=False)
    assert rt.enabled() is False
    monkeypatch.setenv("FDA_RAPIDWRIGHT", "1")
    assert rt.enabled() is True


@pytest.mark.parametrize("part,ok", [("xck26-sfvc784-2LV-c", True), ("xc7a100tcsg324-1", True), ("xczu5ev-sfvc784-2-e", True),
                                     ("xck26-sfvc784-2LV-c; exit", False), ("x$(id)", False), ("xck26/../etc", False)])
def test_build_yaml_part_pattern(part, ok):
    """The agent's build tool refused the KR260's part name ("not a plain part name": the pattern wanted six characters before the first
    hyphen and a short suffix). The part still reaches Tcl, so the pattern stays a plain allow-list: letters, digits, up to three hyphen groups."""
    from agent.core import tools
    assert bool(tools._PART.match(part)) is ok


def test_rapidwright_env_puts_the_pinned_vivado_first():
    """The first stage 2 run failed in rw_place_chain ("Unable to find a readable EDIF file for the DCP"): RapidWright starts the first
    `vivado` on PATH, and the agent's scrubbed environment did not have the pinned one first."""
    from flow import version_pin
    first = pin.env()["PATH"].split(":")[0]
    assert first == str(Path(version_pin.vivado_path()).parent)
