"""The four 05c agent fixes from the 05b diagnosis, each with a test (no model, no network)."""

import uuid
from pathlib import Path

import pytest
import yaml

from agent.core.runner import LocalRunner, RunResult
from agent.core.session import ROOT
from agent.graph import run as gr
from agent.graph.contract import MODEL_CONTRACT, contract_argv, parse_result
from agent.graph.roles import RoleJail
from agent.graph.spec_schema import SpecError, load_spec, rate_params, validate
from agent.graph.stages import MACHINE, exit_check

T1 = ROOT / "designs" / "t1_dimmer_counter"
GOOD = yaml.safe_load((T1 / "spec.yaml").read_text())
BAD_YAML = "name: x\nregisters:\n  - name: DESIGN_ID\n    text: a: b? c\n  - x\n"


class OkRunner:
    def run(self, kind, argv, cwd, env=None, timeout=600):
        return RunResult(0, f"{kind}: ok", "", 0.0)


@pytest.fixture
def rt(tmp_path, monkeypatch):
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(gr, "RUNS", runs)
    cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", interview="off")
    r = gr.new_runtime(cfg, lambda *a, **k: None, runner=OkRunner())
    from flow import architecture as _am
    _am.write_approval(r.design, 'auto', 'agent')
    yield r
    import shutil
    shutil.rmtree(runs, ignore_errors=True)


# --- fix 1: no silent spec loss -----------------------------------------------------------------------------------

def test_invalid_yaml_raises_with_the_parsers_message(tmp_path):
    f = tmp_path / "spec.yaml"
    f.write_text(BAD_YAML)
    with pytest.raises(SpecError) as e:
        load_spec(f)
    assert "not valid YAML" in str(e.value) and "line" in str(e.value)


def test_clarify_gate_fails_on_invalid_yaml_and_leaves_the_file_alone(rt):
    (rt.design / "spec.yaml").write_text(BAD_YAML)
    out = gr.node_gate({"run_id": rt.run_id, "stage": 0})
    assert out["fails"] and "not valid YAML" in out["fails"][0] and "line" in out["fails"][0]
    assert "not valid YAML" in out["detail"]                      # fed back to the work agent
    assert (rt.design / "spec.yaml").read_text() == BAD_YAML       # never overwritten
    assert out["evidence"]["spec"] == {} and out["evidence"]["signed_off"] is False


def test_clarify_gate_fails_on_empty_spec_and_on_missing_sections(rt):
    (rt.design / "spec.yaml").write_text("open_questions: []\nresolved_questions: []\n")
    out = gr.node_gate({"run_id": rt.run_id, "stage": 0})
    assert out["fails"] and any("'ports'" in f for f in out["fails"])
    (rt.design / "spec.yaml").write_text("")
    assert gr.node_gate({"run_id": rt.run_id, "stage": 0})["fails"] == ["spec.yaml is empty"]


def test_valid_spec_signs_off(rt):
    spec = {**GOOD, "open_questions": []}
    (rt.design / "spec.yaml").write_text(yaml.safe_dump(spec))
    out = gr.node_gate({"run_id": rt.run_id, "stage": 0})
    assert out["fails"] == []


@pytest.mark.parametrize("missing", ["ports", "clocks", "reset", "registers", "timing", "name", "top"])
def test_schema_requires_each_section(missing):
    spec = {k: v for k, v in GOOD.items() if k != missing}
    assert validate(spec) and missing in validate(spec)[0]
    assert validate(GOOD) == []
    assert not exit_check(MACHINE[0], {"spec": spec, "signed_off": True, "spec_errors": validate(spec)})[0]


# --- fix 2: one model API contract + contract-check gate ----------------------------------------------------------

def _check(tmp_path, code, spec=None):
    (tmp_path / "model.py").write_text(code)
    a = contract_argv(tmp_path, spec or {"parameters": {"CLK_HZ": 100}})
    r = LocalRunner().run("contract", a, ROOT)
    return parse_result(r.returncode, r.stdout, r.stderr)


def test_contract_passes_a_conforming_model(tmp_path):
    ok = ("class Model:\n    def __init__(self, CLK_HZ=100):\n        self.c = 0\n    def reset(self):\n        self.c = 0\n"
          "    def step(self, inputs=None):\n        self.c += 1\n        return {'q': self.c}\n")
    assert _check(tmp_path, ok)["ok"]


def test_contract_names_the_api_slip_of_run_1(tmp_path):
    bad = "class Model:\n    def __init__(self, CLK_HZ=100):\n        pass\n    def reset(self): pass\n    def step(self, i=None): return {}\n"
    r = _check(tmp_path, bad, {"parameters": {"clk_hz": 100}})               # test uses clk_hz, model takes CLK_HZ
    assert not r["ok"] and "clk_hz" in r["error"]
    r = _check(tmp_path, "class T1LedDimmerCounter:\n    pass\n")
    assert not r["ok"] and "no class named Model" in r["error"]
    r = _check(tmp_path, "class Model:\n    def reset(self): pass\n    def step(self, i=None): return None\n", {"parameters": {}})
    assert not r["ok"] and "not a dict" in r["error"]


def test_contract_is_a_stage_2_gate_and_in_both_prompts():
    assert "model_contract" in MACHINE[2].gates
    assert not exit_check(MACHINE[2], {"lint": {"ok": True}, "simulate": {"ok": True},
                                       "contract": {"ok": False, "error": "boom"}})[0]
    assert MODEL_CONTRACT in gr.PROMPTS["model"] and MODEL_CONTRACT in gr.PROMPTS["tests"]


def test_gate_skips_simulate_when_the_contract_fails(rt):
    (rt.design / "model.py").write_text("class Wrong:\n    pass\n")
    (rt.design / "spec.yaml").write_text(yaml.safe_dump(GOOD))
    calls = []
    rt.session.runner = type("R", (), {"run": lambda self, kind, argv, cwd, env=None, timeout=600: (
        calls.append(kind), LocalRunner().run(kind, argv, cwd, env, timeout) if kind == "contract"
        else RunResult(0, "ok", "", 0))[1]})()
    out = gr.node_gate({"run_id": rt.run_id, "stage": 2})
    assert "simulate" not in calls and any("model contract" in f for f in out["fails"])
    assert "no class named Model" in out["detail"]


# --- fix 3: integer cycle-count timing parameters -----------------------------------------------------------------

def test_rate_parameters_are_rejected_and_fractions_too():
    spec = {**GOOD, "parameters": {"PWM_HZ": 1000, "DEBOUNCE_MS": 10, "X": 1.5}}
    errs = validate(spec)
    assert any("PWM_HZ" in e for e in errs) and any("DEBOUNCE_MS" in e for e in errs) and any("fractional" in e for e in errs)
    assert validate(spec, allow_rates=True) == [e for e in errs if "fractional" in e]


def test_rate_to_cycles():
    r = {p["name"]: p for p in rate_params({**GOOD, "parameters": {"PWM_HZ": 1000, "DEBOUNCE_MS": 10}})}
    assert r["PWM_HZ"]["cycles"] == 100_000 and r["PWM_HZ"]["new_name"] == "PWM_CYCLES"
    assert r["DEBOUNCE_MS"]["cycles"] == 1_000_000 and r["DEBOUNCE_MS"]["new_name"] == "DEBOUNCE_CYCLES"


def test_interview_asks_for_the_cycle_count_and_rewrites_the_parameter(rt):
    spec = {**GOOD, "open_questions": [], "parameters": {"PWM_HZ": 1000, "CLKS_PER_BIT": 868}}
    (rt.design / "spec.yaml").write_text(yaml.safe_dump(spec))
    out = gr.node_gate({"run_id": rt.run_id, "stage": 0})
    q = out["interview"]["questions"]
    assert len(q) == 1 and "PWM_CYCLES" in q[0]["text"] and q[0]["answer"] == "100000"
    new = yaml.safe_load((rt.design / "spec.yaml").read_text())
    assert new["parameters"] == {"CLKS_PER_BIT": 868, "PWM_CYCLES": 100000} and out["fails"] == []


def test_clarify_prompt_demands_integer_cycle_counts():
    assert "INTEGER CYCLE COUNTS" in gr.PROMPTS["clarify"]


# --- fix 4: superseded files are deleted --------------------------------------------------------------------------

def test_superseded_test_files_are_deleted(rt):
    (rt.design / "tests").mkdir(exist_ok=True)
    stale, keep = rt.design / "tests" / "test_old_bench.py", rt.design / "tests" / "test_new.py"
    stale.write_text("# stale")
    keep.write_text("# new")
    before = [stale, keep]
    gone = gr.drop_superseded(rt.design, RoleJail(rt.session.jail, "tests"), before, {"tests/test_new.py": "# new"})
    assert gone == ["tests/test_old_bench.py"] and not stale.exists() and keep.exists()


def test_superseded_never_reaches_outside_the_role(rt):
    (rt.design / "rtl").mkdir(exist_ok=True)
    f = rt.design / "rtl" / "x.sv"
    f.write_text("module x; endmodule")
    from agent.core.security import SecurityError
    with pytest.raises(SecurityError):
        gr.drop_superseded(rt.design, RoleJail(rt.session.jail, "tests"), [f], {})
    assert f.exists()


def test_one_canonical_spec_shape_and_the_gates_accept_it():
    """05c follow-up: list-valued registers crashed flow/verif_gates.spec_items. The schema now rejects every shape
    the gates cannot read, and the canonical one goes through spec_items."""
    from flow.verif_gates import spec_items
    assert validate(GOOD) == [] and spec_items(GOOD)
    bad = {**GOOD, "registers": [{"name": "COUNT", "offset": 0}]}
    assert any("'registers' must be a mapping" in e for e in validate(bad))
    with pytest.raises(TypeError):
        spec_items(bad)                                  # the crash the schema now prevents
    assert any("'timing' must be a mapping" in e for e in validate({**GOOD, "timing": [{"name": "d"}]}))
    assert any("'timing' must be a mapping" in e for e in validate({**GOOD, "timing": "fast"}))
    assert any("latency" in e for e in validate({**GOOD, "timing": {"latency": ["a"]}}))
    assert any("'behaviour' must be a mapping of lists" in e for e in validate({**GOOD, "behaviour": ["a"]}))
    assert any("behaviour" in e for e in validate({k: v for k, v in GOOD.items() if k != "behaviour"}))


# --- follow-up: the first failing assertion is a structured field, the log tail is kept --------------------------------

PYTEST_LOG = """F
=================================== FAILURES ===================================
________________________ test_t1_dimmer_counter_rtl[1] _________________________

seed = 1

    def test_t1_dimmer_counter_rtl(seed):
>       flow.cocotb_run.run("x", "top", [], "bench", Path("."), seed=seed)

tests/test_x_rtl.py:33:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
flow/cocotb_run.py:99: in run
    raise AssertionError(msg)
E   AssertionError: 1 cocotb test(s) failed:
E     test_counter_up: AssertionError: an: rtl=0xfd model=0xfe at 120 ns
=========================== short test summary info ============================
FAILED tests/test_x_rtl.py::test_t1_dimmer_counter_rtl[1] - AssertionError
"""


def test_first_failure_is_structured_and_the_tail_is_kept():
    from agent.core.tools import first_failure
    ff = first_failure(PYTEST_LOG)
    assert ff["test"] == "test_t1_dimmer_counter_rtl[1]"
    assert ff["message"] == ["AssertionError: 1 cocotb test(s) failed:",
                             "test_counter_up: AssertionError: an: rtl=0xfd model=0xfe at 120 ns"]
    assert ff["where"].startswith("tests/test_x_rtl.py:33")
    assert first_failure("all passed") is None
    sx = first_failure("run: iverilog -o x\nfoo.sv:3: error: Unable to bind wire/reg/memory `dp'\n"
                       "_____ test_a _____\n\n>  run()\nt.py:9: \nE   SystemExit: 1\n")
    assert sx["message"] == ["SystemExit: 1"] and "Unable to bind" in sx["log_errors"][0]


def test_simulate_returns_first_failure_and_unclipped_tail(rt):
    from agent.core import dispatch
    (rt.design / "tests").mkdir(exist_ok=True)
    (rt.design / "tests" / "test_x_rtl.py").write_text("x = 1\n")
    (rt.design / "design.xdc").write_text("# x\n")
    rel = rt.design.relative_to(ROOT)
    (rt.design / "build.yaml").write_text(f"top: t\npart: xc7a100tcsg324-1\nsources: [shell/rtl/*.sv]\nconstraints: [{rel}/design.xdc]\n")
    big = "noise line\n" * 5000 + PYTEST_LOG                  # 55 kB: the middle of this used to be clipped away
    rt.session.runner = type("R", (), {"run": lambda self, kind, argv, cwd, env=None, timeout=600:
                                       RunResult(1, big, "", 0.1)})()
    r = dispatch(rt.session, "simulate", {})
    assert r["ok"] is False, (r["output"][:300], r.get("rule"))
    assert "first_failure" in r, r["output"]
    assert r["first_failure"]["test"].startswith("test_t1_dimmer_counter_rtl")
    assert "rtl=0xfd model=0xfe" in " ".join(r["first_failure"]["message"])
    assert r["output"].startswith("[first failure] test_t1_dimmer_counter_rtl[1]")   # MCP text carries it too
    assert r["log_tail"].endswith("AssertionError\n".rstrip()) and "FAILED tests/test_x_rtl.py" in r["log_tail"]
