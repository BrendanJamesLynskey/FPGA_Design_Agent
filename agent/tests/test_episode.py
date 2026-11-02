"""A whole agent episode on T1 with no network and no tools (05b CI smoke): a scripted model, a fake runner that
returns the flow's recorded gate output, the spec oracle for one interview turn, review on with a scripted
reviewer, one rewind from stage 6 to stage 2 (hash-checked), and a scripted hardware approval.

The scripted model is a stand-in that writes plausible files; what is tested is the graph: stage order, gates
decide exits, isolation of sub-agent inputs, interview record, review pages, snapshots and rewind."""

import json
from pathlib import Path

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("deepagents")

from agent.core.runner import RunResult  # noqa: E402
from agent.graph import run as gr  # noqa: E402
from agent.graph.llm import Reply  # noqa: E402

T1 = Path(__file__).resolve().parents[2] / "designs" / "t1_dimmer_counter"
from agent.core.session import ROOT as ROOT_  # noqa: E402

STAGES = {k: {"ran": True, "gates": g} for k, g in {
    "rtl": {"rtl_methodology_no_critical": True},
    "post_synth": {"post_synth_no_unconstrained_endpoints": True, "post_synth_methodology_no_critical": True,
                   "post_synth_drc_clean": True, "post_synth_qor_assessment": True, "post_synth_cdc_no_critical": True,
                   "post_synth_resources_in_range": True},
    "post_place": {"post_place_hold": True},
    "post_route": {"setup": True, "hold": True, "pulse_width": True, "no_unconstrained_endpoints": True,
                   "drc_clean": True, "methodology_no_critical": True, "cdc_no_critical": True,
                   "power_junction_ok": True},
    "bitstream": {"bitstream_present": True}}.items()}
GATES = {"stages": STAGES, "timing": {"wns_ns": 3.911, "tns_ns": 0.0, "whs_ns": 0.106, "ths_ns": 0.0},
         "utilization": {"lut": 495, "lut_available": 63400, "ff": 488, "ff_available": 126800},
         "power": {"total_w": 0.15, "confidence": "Low"}, "power_environment": {"junction_c": 42.7, "ambient_c": 40}}


class FakeRunner:
    """Answers each flow command as the real flow would on T1 (gates from a real T1 build)."""

    def __init__(self):
        self.kinds = []

    def run(self, kind, argv, cwd, env=None, timeout=600):
        self.kinds.append(kind)
        if kind == "contract":                                       # the real contract check, on the host
            from agent.core.runner import LocalRunner
            return LocalRunner().run(kind, argv, cwd, env, timeout)
        if kind == "standards":                                      # the real static rules on the scripted RTL; the
            from flow import standards_check as sc               # Verilator/Yosys rules are tested where those tools are
            design = Path(argv[2])
            from unittest import mock
            out = Path(argv[argv.index("--json") + 1])
            out.parent.mkdir(parents=True, exist_ok=True)
            with mock.patch.object(sc.Check, "rule_latch_loop", lambda self: None):
                res = sc.evaluate(design, ROOT_, "base")
            out.write_text(json.dumps(res))
            return RunResult(0 if res["pass"] else 1, "standards: " + ("PASS" if res["pass"] else "FAIL " + json.dumps(
                [(r["id"], r["findings"]) for r in res["rules"] if r["status"] in ("fail", "not_run")])), "", 0.01)
        if kind == "architecture":
            from flow import architecture as am
            out = Path(argv[argv.index("--json") + 1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(am.check_design(Path(argv[3]))))
        if kind == "gates":
            out = Path(argv[argv.index("--json") + 1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(GATES))
        if kind == "verif_gates":
            out = cwd / argv[argv.index("--json") + 1]
            assert "/build/verif/" in str(out) and str(out).startswith(str(cwd / "runs")), out   # never shared
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps({"reached": "V3", "first_failed": None,
                                       "stages": {"SIGNOFF": {"pass": True, "checks": {}}},
                                       "traceability": [{"requirement": "REQ-01", "method": "simulation", "artefact": "t.x",
                                                         "result": "pass", "detail": "passed on 3 seed(s)", "text": "x"}]}))
        if kind == "build":                                         # run_vivado.sh <design> <variant>
            b = Path(argv[1]) / "build" / argv[2]
            b.mkdir(parents=True, exist_ok=True)
            (b / "post_synth.dcp").write_bytes(b"DCP " + str(len(self.kinds)).encode())
            (b / "clock_networks_synth.rpt").write_text("Clock sys_clk_pin (100MHz)(endpoints: 488 clock)\nPort CLK100MHZ\n")
            if (env or {}).get("FDA_STOP_AFTER") == "bitstream":
                (b / "top.bit").write_bytes(b"BIT")
        if kind == "bringup":
            out = Path(argv[argv.index("--results-dir") + 1])
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{Path(argv[2]).name}_bringup.json").write_text(json.dumps({"pass": True}))
        return RunResult(0, f"{kind}: ok", "", 0.01)


# the hand-written T1 model predates the 05c contract (`Model`, `step`); the scripted episode adds the thin adapter
SHIM = "\n\nclass Model(DimmerCounterModel):\n    def step(self, inputs=None):\n        return {}\n"


def scripted_client(seen, where):
    spec = (T1 / "spec.yaml").read_text().replace("default: no, linear", "reason: not in the request\n    default: no, linear")
    files = {"clarify": {"/spec.yaml": spec}, "model": {"/model.py": (T1 / "model.py").read_text() + SHIM},
             "tests": {"/tests/test_t1_dimmer_counter_rtl.py": "# bench\n", "/verif/testplan.yaml": "items: []\n",
                       "/tests/test_t1_dimmer_counter_hw.py": (T1 / "tests" / "test_t1_hw.py").read_text(),
                       "/hw_checks.py": (T1 / "hw_checks.py").read_text()}}
    rtl1 = {"/architecture.yaml": (T1 / "architecture.yaml").read_text(),
            "/ARCHITECTURE.md": "# T1\n\n## Block diagram\n\n```\n[buttons] -> [debounce] -> [counter] -> [pwm]\n```\n",
            "/build.yaml": (T1 / "build.yaml").read_text().replace("designs/t1_dimmer_counter/", "{d}/"),
            "/design.xdc": (T1 / "design.xdc").read_text(), "/probes.yaml": (T1 / "probes.yaml").read_text(), "/BRINGUP.md": (T1 / "BRINGUP.md").read_text(),
            **{f"/rtl/{f.name}": f.read_text() for f in sorted((T1 / "rtl").glob("*.sv"))}}

    def client(messages, tools=None):
        system = messages[0]["content"]
        role = ("clarify" if "turn a short design request" in system else "model" if "blind golden model" in system
                else "tests" if ("cocotb tests" in system or "bring-up tests" in system) else "rtl")
        seen.append({"role": role, "user": messages[1]["content"] if len(messages) > 1 else ""})
        if messages[-1]["role"] == "tool":
            return Reply("DONE", [])
        if role == "rtl" and "stage 1 " in system:
            todo = {k: v.replace("{d}", where["design"]) for k, v in rtl1.items()}
        else:
            todo = files.get(role, {})
        calls = [{"id": f"c{i}", "name": "write_file", "args": {"file_path": p, "content": c}}
                 for i, (p, c) in enumerate(todo.items())]
        return Reply("" if calls else "DONE", calls, prompt_tokens=100, completion_tokens=20, cost=0.0)
    return client


def test_t1_episode_interview_review_rewind(tmp_path, monkeypatch):
    import shutil
    import uuid

    from agent.core.session import ROOT
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"        # sources in build.yaml are repo-relative
    monkeypatch.setattr(gr, "RUNS", runs)
    from flow import hw                              # no board in CI: the board file and power_ok are stubbed
    monkeypatch.setattr(hw, "load_board", lambda b: {"cable_serial": "TEST0000"})
    monkeypatch.setattr(hw, "power_ok", lambda d, b: {"pass": True, "total_w": 0.15, "junction_c": 42.7,
                                                      "source": "wall"})
    try:
        _episode(tmp_path, runs)
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def _episode(tmp_path, runs):
    from agent.core.session import ROOT
    hidden = tmp_path / "t1_full_spec.yaml"
    hidden.write_text((T1 / "spec.yaml").read_text())
    seen = []
    cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", interview="oracle", review="on",
                    hidden_spec=hidden)
    oracle_replies = iter([{"answer": "not specified", "quote": None}, {"answer": "not specified", "quote": None}])
    runner = FakeRunner()
    where = {}
    rt = gr.new_runtime(cfg, scripted_client(seen, where), run_id="ci", runner=runner,
                        oracle_llm=lambda s, u: next(oracle_replies))
    # build.yaml must name this run's design directory
    from agent.core.session import ROOT
    where["design"] = str(rt.design.relative_to(ROOT))
    graph = gr.build_graph(gr.checkpointer_for(rt.run_dir))
    from langgraph.types import Command
    lg = {"configurable": {"thread_id": "ci"}}
    inp = {"run_id": "ci", "stage": 0, "visits": {}, "history": []}
    reviews, hashes = [], {}
    while True:
        graph.invoke(inp, lg)
        st = graph.get_state(lg)
        pend = [i.value for t in st.tasks for i in (t.interrupts or [])]
        if not pend:
            break
        p = pend[0]
        reviews.append((p["stage"], p.get("hardware")))
        if p["stage"] == 2 and 2 not in hashes:
            hashes[2] = rt.snaps.latest_for(2)["manifest"]
        if p["stage"] == 6 and not any(h.get("rewind") for h in st.values.get("history", [])):
            inp = Command(resume={"decision": "rewind", "to": 2, "by": "planner", "note": "check the rewind"})
        else:
            inp = Command(resume={"decision": "approve", "by": "planner"})
    s = gr.summary(rt, st.values)
    hist = st.values["history"]
    rew = [h["rewind"] for h in hist if h.get("rewind")]
    assert rew and rew[0]["to"] == 2 and rew[0]["verified"], ([(h["n"], h["passed"]) for h in hist], st.values.get("fails"), st.values.get("detail"), st.values.get("stop"))
    assert s["stages_visited"][:7] == [0, 1, 2, 3, 4, 5, 6] and s["stages_visited"][7] == 2
    assert s["stages_visited"][-1] == 9 and s["bringup"] is True and s["stop"] == "done"
    assert (9, True) in reviews                                  # hardware always pauses for approval
    assert s["questions"]["asked"] == 2 and s["questions"]["defaulted"] == 2
    # sub-agent isolation: the blind model's prompt carried only spec.yaml; the test writer never the RTL
    model_prompt = next(x["user"] for x in seen if x["role"] == "model")
    assert "--- spec.yaml ---" in model_prompt and "--- model.py ---" not in model_prompt
    tests_prompt = next(x["user"] for x in seen if x["role"] == "tests")
    assert "--- ARCHITECTURE.md ---" not in tests_prompt and "--- rtl/" not in tests_prompt and "endmodule" not in tests_prompt
    idx = (rt.design / "build" / "review" / "review_index.html").read_text()
    assert "planner" in idx and "rewind" in idx
    assert (rt.design / "build" / "review" / "06_timing-closure.html").is_file()
    assert "3.911" in (rt.design / "build" / "review" / "06_timing-closure.html").read_text()
    assert "simulate" in runner.kinds and "bringup" in runner.kinds
