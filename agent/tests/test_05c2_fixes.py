"""The six 05c2 fixes (brief 05c2: make the agent finish T1), each a general agent or tool principle, each tested
offline with no model and no network."""

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import yaml

from agent.core import dispatch, tool_list
from agent.core import tools as tl
from agent.core.runner import ContainerRunner, LocalRunner, RunResult
from agent.core.session import ROOT
from agent.graph import repair
from agent.graph import run as gr
from agent.graph.stages import MACHINE, exit_check
from flow import verif_gates as vg

T1 = ROOT / "designs" / "t1_dimmer_counter"
GOOD = yaml.safe_load((T1 / "spec.yaml").read_text())
FIX = Path(__file__).parent / "fixtures"


class OkRunner:
    def run(self, kind, argv, cwd, env=None, timeout=600):
        return RunResult(0, f"{kind}: ok", "", 0.0)


@pytest.fixture
def rt(tmp_path, monkeypatch):
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(gr, "RUNS", runs)
    cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", interview="off")
    r = gr.new_runtime(cfg, lambda *a, **k: None, runner=OkRunner())
    yield r
    import shutil
    shutil.rmtree(runs, ignore_errors=True)


# --- fix 1: repair, don't regenerate -----------------------------------------------------------------------------

def _ev(**kw):
    ev = {"lint": {"ok": True}, "contract": {"ok": True}, "simulate": {"ok": True}, "verif": {"reached": "V3"}}
    ev.update(kw)
    return ev


MISMATCH = {"test": "test_x_rtl[1]", "message": ["AssertionError: an: rtl=0xfd model=0xfe"], "where": "tests/b.py:9:",
            "cause": ["AssertionError: an: rtl=0xfd model=0xfe"], "frames": [], "log_errors": []}


def test_each_failure_goes_to_the_role_that_owns_it():
    o, _ = repair.stage2_owners(_ev(contract={"ok": False, "error": "AttributeError: no Model"}, simulate={"ok": False}))
    assert list(o) == ["model"] and "no Model" in o["model"][0]
    o, _ = repair.stage2_owners(_ev(lint={"ok": False, "text": "%Warning-UNUSEDSIGNAL"}))
    assert list(o) == ["rtl"]
    o, _ = repair.stage2_owners(_ev(simulate={"ok": False, "first_failure": MISMATCH, "text": "t"}))
    assert list(o) == ["rtl"]                                             # a model-vs-RTL mismatch: the RTL first
    v = {"reached": "V0", "first_failed": "V1", "stages": {"V1": {"checks": {
        "spec_items_traced": {"value": "5/32", "threshold": "all", "pass": False},
        "untraced_items": {"value": ["behaviour.a[0]", "reset"], "threshold": [], "pass": False}}}}}
    o, _ = repair.stage2_owners(_ev(verif=v))
    assert list(o) == ["tests"] and "behaviour.a[0]" in o["tests"][0] and "5/32" in o["tests"][0]


def test_code_errors_are_traced_to_the_file_they_name():
    comp = (FIX / "pytest_systemexit_compile.log").read_text()
    ff = tl.first_failure(comp)
    assert repair.classify_sim(ff, comp) == ("rtl", "code")               # a compile error in the HDL
    mod = (FIX / "pytest_systemexit_model.log").read_text()
    ff = tl.first_failure(mod)
    assert repair.classify_sim(ff, mod) == ("model", "code")              # KeyError raised in model.py
    ff2 = {**ff, "frames": ['File "/w/tests/bench.py", line 3, in t'], "cause": ["NameError: x"], "message": ["AssertionError: w"]}
    assert repair.classify_sim(ff2, "") == ("tests", "code")              # a NameError in the bench


def test_an_unchanged_failure_escalates_but_the_blind_model_never_sees_the_rtl_failure():
    ev = _ev(simulate={"ok": False, "first_failure": MISMATCH, "text": "rtl output rtl=0xfd"})
    o0, sig0 = repair.stage2_owners(ev, repeat=0)
    o1, sig1 = repair.stage2_owners(ev, repeat=1)
    o2, sig2 = repair.stage2_owners(ev, repeat=2)
    assert sig0 == sig1 == sig2                                           # the signature ignores the escalation
    assert list(o0) == ["rtl"] and list(o1) == ["tests", "rtl"] and list(o2) == ["model", "tests", "rtl"]
    assert "0xfd" not in o2["model"][0] and "test_x_rtl[1]" in o2["model"][0]


def test_stage_2_plan_freezes_what_passed(rt):
    d = rt.design
    assert gr.stage2_plan(rt, {}) == {"model": None, "tests": None, "rtl": None}          # first visit: write all
    (d / "model.py").write_text("class Model: pass\n")
    (d / "tests").mkdir(exist_ok=True)
    (d / "tests" / "test_x_rtl.py").write_text("# t\n")
    (d / "rtl").mkdir(exist_ok=True)
    (d / "rtl" / "top.sv").write_text("module top; endmodule\n")
    owners = {"tests": ["V1 untraced"]}
    assert gr.stage2_plan(rt, {"owners": owners}) == {"tests": ["V1 untraced"]}           # model and rtl frozen
    plan = gr.stage2_plan(rt, {"owners": {}, "fails": ["post_route:setup"]})              # from a later stage
    assert list(plan) == ["rtl"] and "post_route:setup" in plan["rtl"][0]


def test_gate_sets_owners_and_counts_repeats(rt):
    (rt.design / "model.py").write_text("class Wrong:\n    pass\n")
    (rt.design / "spec.yaml").write_text(yaml.safe_dump(GOOD, sort_keys=False))
    rt.session.runner = type("R", (), {"run": lambda self, kind, argv, cwd, env=None, timeout=600: (
        LocalRunner().run(kind, argv, cwd, env, timeout) if kind == "contract" else RunResult(0, "ok", "", 0))})()
    s1 = gr.node_gate({"run_id": rt.run_id, "stage": 2})
    assert "model" in s1["owners"] and "no class named Model" in s1["owners"]["model"][0] and s1["repeat"] == 0
    s2 = gr.node_gate({"run_id": rt.run_id, "stage": 2, "sig": s1["sig"], "repeat": s1["repeat"]})
    assert s2["repeat"] == 1                                                              # same failure again


class _FakeAgent:
    """Stands in for create_deep_agent: returns the seeded files plus one change, like a repairing model."""

    def __init__(self, seeded, change):
        self.files, self.change = seeded, change

    def invoke(self, payload, cfg=None):
        out = dict(payload["files"])
        from deepagents.backends.utils import create_file_data
        out.update({k: create_file_data(v) for k, v in self.change.items()})
        return {"files": out}


def test_repair_edits_previous_output_and_deletes_nothing(rt, monkeypatch):
    import deepagents
    d = rt.design
    (d / "spec.yaml").write_text(yaml.safe_dump(GOOD, sort_keys=False))
    (d / "tests").mkdir(exist_ok=True)
    (d / "tests" / "keep.py").write_text("KEEP = 1\n")
    (d / "tests" / "fix.py").write_text("OLD = 1\n")
    (d / "model.py").write_text("class Model: pass\n")
    (d / "rtl").mkdir(exist_ok=True)
    (d / "rtl" / "top.sv").write_text("module secret_rtl; endmodule\n")
    seen = {}

    def fake(model, tools, system_prompt, backend=None):
        return _FakeAgent(None, {"/tests/fix.py": "NEW = 2\n"})
    monkeypatch.setattr(deepagents, "create_deep_agent", fake)
    from agent.graph import llm
    monkeypatch.setattr(gr, "chat_model", lambda *a, **k: None)
    written = gr.run_subagent(rt, "tests", "P", ("search_docs",), repair=True)
    assert written == {"tests/fix.py": "wrote 8 bytes to tests/fix.py"} or list(written) == ["tests/fix.py"]
    assert (d / "tests" / "fix.py").read_text() == "NEW = 2\n"
    assert (d / "tests" / "keep.py").exists()                              # not deleted: a repair edits in place
    # the same turn in fresh mode would delete files the role did not write again
    (d / "tests" / "fix.py").write_text("OLD = 1\n")
    gr.run_subagent(rt, "tests", "P", ("search_docs",), repair=False)
    assert not (d / "tests" / "keep.py").exists()


def test_repair_prompt_for_the_blind_model_has_only_the_spec_and_its_own_model(rt):
    d = rt.design
    (d / "spec.yaml").write_text(yaml.safe_dump(GOOD, sort_keys=False))
    (d / "model.py").write_text("class Model: pass  # mine\n")
    (d / "rtl").mkdir(exist_ok=True)
    (d / "rtl" / "top.sv").write_text("module secret_rtl; endmodule\n")
    (d / "tests").mkdir(exist_ok=True)
    (d / "tests" / "test_x_rtl.py").write_text("SECRET_TEST = 1\n")
    plan = gr.subagent_plan(rt, "model", "P" + gr.repair_note("model", ["[model contract] boom"]), (), repair=True)
    assert set(plan["inputs"]) == {"spec.yaml", "model.py"}
    assert "secret_rtl" not in plan["user_message"] and "SECRET_TEST" not in plan["user_message"]
    assert "REPAIR VISIT" in plan["user_message"] and "boom" in plan["user_message"] and plan["repair"] is True
    fresh = gr.subagent_plan(rt, "model", "P", (), repair=False)
    assert set(fresh["inputs"]) == {"spec.yaml"}


# --- fix 2: constraints by board resource name -------------------------------------------------------------------

BOARD = ROOT / "boards" / "nexys_a7_100t"


def test_board_constraints_writes_pins_from_the_master_xdc(rt):
    rt.session.stage = "board-and-device-planning"
    m = [{"resource": "clk100", "port": "clk"}, {"resource": "led[0:15]", "port": "led"},
         {"resource": "sw[0:3]", "port": "sw"}, {"resource": "seg", "port": "seg"}, {"resource": "an", "port": "an"},
         {"resource": "btnc", "port": "go"}, {"resource": "reset_n", "port": "rst_n"},
         {"resource": "sw[15]", "port": "mode"}]
    r = dispatch(rt.session, "board_constraints", {"map": m})
    assert r["ok"], r["output"]
    xdc = (rt.design / "design.xdc").read_text()
    assert "PACKAGE_PIN E3" in xdc and "[get_ports { clk }]" in xdc          # the board clock, from the master
    assert "create_clock -add -name sys_clk_pin -period 10.00" in xdc and "{ clk }" in xdc.split("create_clock")[1]
    assert "PACKAGE_PIN H17" in xdc and "led[15]" in xdc and "PACKAGE_PIN V10" in xdc and "{ mode }" in xdc
    assert r["ports"] == {"an": 8, "clk": 1, "go": 1, "led": 16, "mode": 1, "rst_n": 1, "seg": 8, "sw": 4}
    assert r["findings"] == []
    # the result passes the gate that remains
    cfg = (f"top: t\npart: xc7a100tcsg324-1\nsources: [shell/rtl/*.sv]\nconstraints: [{rt.design.relative_to(ROOT)}/design.xdc]\n")
    (rt.design / "build.yaml").write_text(cfg)
    assert dispatch(rt.session, "check_constraints", {})["ok"]


def test_board_constraints_errors_name_the_problem_and_write_nothing(rt):
    for m, word in (([{"resource": "clk", "port": "c"}], "unknown resource"),
                    ([{"resource": "led[0:16]", "port": "led"}], "no element 16"),
                    ([{"resource": "sw[0]", "port": "a"}, {"resource": "sw[0]", "port": "b"}], "used by both"),
                    ([{"resource": "led[0:1]", "port": "x"}, {"resource": "sw[0:1]", "port": "x"}], "mapped twice"),
                    ([{"resource": "led[0:3]", "port": "9bad"}], "not a plain port name")):
        r = dispatch(rt.session, "board_constraints", {"map": m})
        assert not r["ok"] and word in r["output"], (m, r["output"])
        assert not (rt.design / "design.xdc").exists()
    listing = dispatch(rt.session, "board_constraints", {})
    assert "clk100" in listing["output"] and "led[0:15]" in listing["output"] and "seg[0:7]" in listing["output"]


def test_board_constraints_is_a_stage_tool_and_on_the_mcp_server():
    assert "board_constraints" in MACHINE[1].tools and "board_constraints" in MACHINE[3].tools
    assert "board_constraints" in [t["name"] for t in tool_list()]
    assert "pin number" in gr.CONVENTIONS and "master XDC (search_docs" not in gr.CONVENTIONS


# --- fix 3: only offer tools that work here ----------------------------------------------------------------------

def test_simulate_offers_only_simulators_that_work(rt, monkeypatch):
    monkeypatch.setattr(tl, "available_sims", lambda: ("icarus",))
    sim = next(t for t in tool_list() if t["name"] == "simulate")
    assert sim["inputSchema"]["properties"]["sim"]["enum"] == ["icarus"] and "available here: icarus" in sim["description"]
    r = dispatch(rt.session, "simulate", {"sim": "verilator"})
    assert r["refused"] and "icarus" in r["output"]                          # the schema itself refuses it
    monkeypatch.setattr(tl, "available_sims", lambda: ("icarus", "verilator"))
    assert next(t for t in tool_list() if t["name"] == "simulate")["inputSchema"]["properties"]["sim"]["enum"] == \
        ["icarus", "verilator"]
    rt.session.runner = ContainerRunner(rt.design, ROOT)                     # the container image has Icarus only
    (rt.design / "tests").mkdir(exist_ok=True)
    r = dispatch(rt.session, "simulate", {"sim": "verilator"})
    assert not r["ok"] and "not available here" in r["output"]


def test_verilator_is_found_the_way_lint_finds_it(tmp_path, monkeypatch):
    from agent.core import runner as rn
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "verilator").write_text("#!/bin/sh\necho 'Verilator 5.048 2026-01-01 rev x'\n")
    (bindir / "verilator").chmod(0o755)
    f = tmp_path / "tools.yaml"
    f.write_text(f"path: [{bindir}]\n")
    monkeypatch.setattr(rn, "TOOLS_FILE", f)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    assert tl._verilator_version() == (5, 48)
    monkeypatch.setattr(rn, "TOOLS_FILE", tmp_path / "none.yaml")
    assert tl._verilator_version() is None


def test_load_skill_schema_lists_the_valid_section_ids(session, monkeypatch):
    monkeypatch.setattr(tl, "section_ids", lambda: ("clocking", "verification-stages"))
    t = next(x for x in tool_list() if x["name"] == "load_skill")
    assert t["inputSchema"]["properties"]["sections"]["items"]["enum"] == ["clocking", "verification-stages"]
    assert "clocking, verification-stages" in t["description"]
    r = dispatch(session, "load_skill", {"sections": ["rtl-design-creation"]})      # a stage name, not a section id
    assert r["refused"] and "rtl-design-creation" in r["output"]
    assert dispatch(session, "load_skill", {"sections": ["clocking"]})["ok"]


# --- fix 4: clean errors for malformed artefacts -----------------------------------------------------------------

BAD_PLAN = "schema: x\nrequirements:\n  - id: R1\n    spec: [clocks[0], reset\n"


def test_write_file_refuses_malformed_artefacts_with_line_and_column(rt):
    f = rt.design / "verif" / "testplan.yaml"
    f.parent.mkdir(exist_ok=True)
    f.write_text("schema: good\n")
    r = dispatch(rt.session, "write_file", {"path": "verif/testplan.yaml", "content": BAD_PLAN})
    assert not r["ok"] and r["output"].startswith("not written: verif/testplan.yaml: not valid YAML at line ")
    assert "column" in r["output"] and f.read_text() == "schema: good\n"             # the previous file is kept
    assert "Traceback" not in r["output"]
    cases = {"spec.yaml": ("name: x\nregisters: [a]\n", "'registers' must be a mapping"),
             "build.yaml": ("top: t\n", "missing key 'part'"),
             "verif/testplan.yaml": ("schema: s\n", "missing key 'design'"),
             "ARCHITECTURE.md": ("# A\nno diagram\n", "## Block diagram"),
             "probes.yaml": ("a: [1\n", "not valid YAML")}
    r = dispatch(rt.session, "write_file", {"path": "probes.yaml", "content": "ila:\n  name: x\n  clock_net: c\n  depth: 1024\n  probes: [a, b]\n"})
    assert not r["ok"] and "top-level" in r["output"] and "expected form" in r["output"]   # the form the ILA build reads
    assert dispatch(rt.session, "write_file", {"path": "probes.yaml", "content":
                    "ila: {name: x, clock_net: c, depth: 1024}\nprobes:\n  - {name: a, pins: 'u/a_reg[*]/Q', width: 4}\n"})["ok"]
    for path, (content, word) in cases.items():
        r = dispatch(rt.session, "write_file", {"path": path, "content": content})
        assert not r["ok"] and word in r["output"], (path, r["output"])
    ok = dispatch(rt.session, "write_file", {"path": "ARCHITECTURE.md", "content": "# A\n\n## Block diagram\n\n```\n[a]\n```\n"})
    assert ok["ok"]
    assert dispatch(rt.session, "write_file", {"path": "notes.txt", "content": "a: [1\n"})["ok"]    # unknown file: not checked


def test_gates_report_a_malformed_testplan_as_a_failed_gate_not_a_traceback(rt):
    (rt.design / "verif").mkdir(exist_ok=True)
    (rt.design / "verif" / "testplan.yaml").write_text(BAD_PLAN)                     # written outside the tool
    rt.session.runner = LocalRunner()
    r = dispatch(rt.session, "gates", {"kind": "verif"})
    g = r["gates"]
    assert g["first_failed"] == "V0" and g["reached"] is None
    msg = g["stages"]["V0"]["checks"]["testplan_valid"]["value"]
    assert "not valid YAML at line" in msg and "column" in msg
    assert "Traceback" not in r["output"]
    # also a testplan that parses but is the wrong shape, and a spec of the wrong shape
    (rt.design / "verif" / "testplan.yaml").write_text("schema: x\n")
    g = dispatch(rt.session, "gates", {"kind": "verif"})["gates"]
    assert "has no 'spec'" in g["stages"]["V0"]["checks"]["testplan_valid"]["value"]
    out = subprocess.run([sys.executable, str(ROOT / "flow" / "verif_gates.py"), str(rt.design)],
                         capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 1 and "Traceback" not in out.stdout + out.stderr


def test_verif_gates_not_bound_to_one_designs_names(tmp_path):
    """The V1/V2 checks looked for T1's model class and test names; any design's bench that imports the model, and
    any test with 'random' in its name, satisfies them."""
    src = open(vg.__file__).read()
    assert "DimmerCounterModel" not in src and "t1_verif.constrained" not in src


# --- fix 5: traceability made checkable --------------------------------------------------------------------------

def test_spec_items_tool_lists_the_exact_ids_the_gate_checks(rt):
    (rt.design / "spec.yaml").write_text(yaml.safe_dump(GOOD, sort_keys=False))
    r = dispatch(rt.session, "spec_items", {})
    assert r["ok"] and r["ids"] == vg.spec_items(GOOD) and r["count"] == len(vg.spec_items(GOOD))
    assert r["output"].splitlines()[0].startswith("behaviour.") and ": " in r["output"].splitlines()[0]
    (rt.design / "spec.yaml").write_text("name: x\nregisters: [a]\n")
    assert not dispatch(rt.session, "spec_items", {})["ok"]
    assert "spec_items" in gr.FLOW_TOOLS and "spec_items" in gr.PROMPTS["tests"]


def test_the_gate_failure_lists_the_untraced_ids(rt):
    d = rt.design
    rel = d.relative_to(ROOT)
    (d / "spec.yaml").write_text(yaml.safe_dump(GOOD, sort_keys=False))
    (d / "model.py").write_text("class Model: pass\n")
    (d / "tests").mkdir(exist_ok=True)
    (d / "tests" / "bench.py").write_text("import cocotb\nimport model\n\n@cocotb.test()\nasync def t_one(dut):\n    pass\n")
    (d / "verif" / "checkers").mkdir(parents=True, exist_ok=True)
    (d / "verif" / "formal").mkdir(parents=True, exist_ok=True)
    ids = vg.spec_items(GOOD)
    plan = {"schema": "s", "design": "x", "spec": f"{rel}/spec.yaml", "model": f"{rel}/model.py",
            "bench": {"modules": ["bench"], "dir": f"{rel}/tests"}, "checkers": f"{rel}/verif/checkers",
            "formal_dir": f"{rel}/verif/formal",
            "thresholds": {"seeds_min": 3, "functional_bins_pct": 100, "cover_properties_pct": 100, "line_pct": 90,
                           "toggle_pct": 80, "mutation_score_pct": 90},
            "requirements": [{"id": "R1", "spec": ids[:5], "tests": ["bench.t_one"]}]}
    (d / "verif" / "testplan.yaml").write_text(yaml.safe_dump(plan))
    rt.session.runner = LocalRunner()
    g = dispatch(rt.session, "gates", {"kind": "verif"})["gates"]
    assert g["first_failed"] == "V1"
    assert g["stages"]["V1"]["checks"]["bench_uses_blind_model"]["pass"]          # no T1 class name needed
    ok, why = exit_check(MACHINE[2], {"lint": {"ok": True}, "contract": {"ok": True}, "simulate": {"ok": True},
                                      "verif": g})
    text = "\n".join(why)
    assert not ok and f"5/{len(ids)}" in text
    assert all(i in text for i in ids[5:])                                         # every untraced id is named


# --- fix 6: cocotb wrapper failures carry the cause --------------------------------------------------------------

def test_systemexit_failure_carries_the_underlying_cause():
    ff = tl.first_failure((FIX / "pytest_systemexit_compile.log").read_text())
    assert ff["message"] == ["SystemExit: 1"]
    assert any("Unable to bind" in c for c in ff["cause"])                         # the simulator's own error
    ff = tl.first_failure((FIX / "pytest_systemexit_model.log").read_text())
    assert any("KeyError: 'btn'" in c for c in ff["cause"]) and any("model.py" in f for f in ff["frames"])


def test_simulate_output_heads_with_the_cause(rt):
    (rt.design / "tests").mkdir(exist_ok=True)
    (rt.design / "tests" / "test_x_rtl.py").write_text("x = 1\n")
    (rt.design / "design.xdc").write_text("# x\n")
    rel = rt.design.relative_to(ROOT)
    (rt.design / "build.yaml").write_text(f"top: t\npart: xc7a100tcsg324-1\nsources: [shell/rtl/*.sv]\nconstraints: [{rel}/design.xdc]\n")
    log = (FIX / "pytest_systemexit_compile.log").read_text()
    rt.session.runner = type("R", (), {"run": lambda self, kind, argv, cwd, env=None, timeout=600: RunResult(1, log, "", 0.1)})()
    r = dispatch(rt.session, "simulate", {})
    assert r["output"].startswith("[first failure]") and "cause: rtl/top.sv:42: error: Unable to bind" in r["output"]


def test_check_constraints_accepts_renamed_ports_and_still_catches_wrong_pins():
    """Ports may carry the design's own names; the pin and standard are checked against the master by pin."""
    from agent.core import constraints as con
    good = "set_property -dict { PACKAGE_PIN E3 IOSTANDARD LVCMOS33 } [get_ports { clk }];\ncreate_clock -period 10 [get_ports { clk }];\n"
    assert con.check_xdc(good, BOARD) == []
    wrong_pin = "set_property -dict { PACKAGE_PIN W5 IOSTANDARD LVCMOS33 } [get_ports { clk }];\n"
    assert [x["rule"] for x in con.check_xdc(wrong_pin, BOARD)] == ["FDA-CON-4"]       # W5 is not a pin the board uses
    dup = ("set_property -dict { PACKAGE_PIN J15 IOSTANDARD LVCMOS33 } [get_ports { a }];\n"
           "set_property -dict { PACKAGE_PIN J15 IOSTANDARD LVCMOS33 } [get_ports { b }];\n")
    assert [x["rule"] for x in con.check_xdc(dup, BOARD)] == ["FDA-CON-4"]
    clk_on_button = ("set_property -dict { PACKAGE_PIN N17 IOSTANDARD LVCMOS33 } [get_ports { b }];\n"
                     "create_clock -period 10 [get_ports { b }];\n")
    assert "FDA-CON-1" in [x["rule"] for x in con.check_xdc(clk_on_button, BOARD)]


# --- found by the first live run: gate evidence must belong to the design, and the level is explicit --------------

def test_verif_gate_reads_only_this_designs_runs_and_the_level_is_configurable(rt):
    seen = []
    rt.session.runner = type("R", (), {"run": lambda self, kind, argv, cwd, env=None, timeout=600: (
        seen.append(argv), RunResult(0, "", "", 0))[1]})()
    dispatch(rt.session, "gates", {"kind": "verif"})
    a = seen[0]
    assert a[a.index("--runs") + 1] == f"{rt.design.relative_to(ROOT)}/build/verif/sim"      # never build/verif/verilator
    v1 = {"reached": "V1", "first_failed": "V2", "stages": {"V2": {"checks": {"seeds_run": {"value": [], "threshold": ">=1", "pass": False}}}}}
    base = {"lint": {"ok": True}, "contract": {"ok": True}, "simulate": {"ok": True}, "verif": v1}
    assert not exit_check(MACHINE[2], {**base, "verif_level": "V3"})[0]
    verif_lines = lambda lvl: [w for w in exit_check(MACHINE[2], {**base, "verif_level": lvl})[1] if w.startswith("V")]
    assert verif_lines("V1") == [] and verif_lines("V2") and verif_lines("V3")
    assert gr.Config(spec_md=T1 / "spec.md", name="x").verif_level == "V3"                   # the default is unchanged


# --- found by the second live run: stage 9 never gave the model a turn before its builds --------------------------

def test_stage_9_work_runs_before_the_hardware_approval(rt, monkeypatch):
    """The ILA build needs probes.yaml, which only the model writes; the work step used to be skipped until the board
    was approved, so the ILA build always failed and the failure was routed back to timing closure."""
    ran = []
    monkeypatch.setattr(gr, "run_subagent", lambda rt_, role, prompt, allowed=(), repair=False: ran.append((role, allowed)) or {})
    gr.node_work({"run_id": rt.run_id, "stage": 9, "visits": {}})
    assert ran and ran[0][0] == "rtl" and "program" not in ran[0][1] and "bringup" not in ran[0][1]
    from agent.graph.stages import classify, route_failure
    fails = ["bitstream: did not run"]
    assert route_failure(MACHINE[9], classify(MACHINE[9], fails)) == 9              # retry here, not stages 6-8
    assert route_failure(MACHINE[9], classify(MACHINE[9], ["bitstream:bitstream_present"])) == 6


def test_gates_on_a_missing_build_directory_is_a_failed_gate_not_a_traceback(tmp_path):
    out = subprocess.run([sys.executable, str(ROOT / "flow" / "gates.py"), str(tmp_path / "nothing"), "--json",
                          str(tmp_path / "g.json")], capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 1 and "Traceback" not in out.stdout + out.stderr and "FAIL" in out.stdout
    assert json.loads((tmp_path / "g.json").read_text())["pass"] is False


def test_prepare_runs_as_a_script_for_the_ila_variant(rt, tmp_path):
    """flow/prepare.py is run as a plain script by the flow: it must not import the agent package (a live run lost an
    hour to exactly that)."""
    d = rt.design
    rel = d.relative_to(ROOT)
    (d / "rtl").mkdir(exist_ok=True)
    (d / "rtl" / "t.sv").write_text("module t(input logic clk); endmodule\n")
    (d / "design.xdc").write_text("# x\n")
    (d / "probes.yaml").write_text("ila: {name: x, clock_net: c, depth: 512}\nprobes:\n  - {name: a, pins: 'a_reg[*]/Q', width: 4}\n")
    (d / "build.yaml").write_text(f"top: t\npart: xc7a100tcsg324-1\nsources: [{rel}/rtl/*.sv]\nconstraints: [{rel}/design.xdc]\n"
                                  f"probes: {rel}/probes.yaml\n")
    out = subprocess.run([sys.executable, str(ROOT / "flow" / "prepare.py"), str(d), "--variant", "ila", "--out", str(tmp_path)],
                         capture_output=True, text=True, cwd=ROOT, env={"PATH": "/usr/bin:/bin"})
    assert out.returncode == 0 and (tmp_path / "probes.tcl").is_file(), out.stderr[-400:]
    (d / "probes.yaml").write_text("ila: {name: x}\nprobes: [a]\n")
    bad = subprocess.run([sys.executable, str(ROOT / "flow" / "prepare.py"), str(d), "--variant", "ila", "--out", str(tmp_path)],
                         capture_output=True, text=True, cwd=ROOT, env={"PATH": "/usr/bin:/bin"})
    assert bad.returncode != 0 and "malformed" in bad.stderr and "Traceback" not in bad.stderr
