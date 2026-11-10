"""Brief 27B P1: phase 0, the structured spec session (``project/phase0.py``), with canned model replies (no network).

The drafter and the oracle are fakes: the tests pin the harness rules, not a model. One question per field the spec
does not state; a quote counts only if it is in the spec; link fields asked once; unanswered questions become
assumptions; the drafter's unasked changes are logged; the files written pass ``check_project``.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from agent.graph.interview import Question, SpecOracle, is_register_question
from project import phase0
from project.phase0 import (Calls, Drafter, Session, contract_fields, inventory, quote_ok, spec_contract_errors,
                            values_by_path)
from project.schema import check_project

ROOT = Path(__file__).resolve().parents[2]
FMT = ROOT / "project" / "phase0_format"

SPEC = """# Byte ramp on the LEDs

A ramp generator counts up by STEP and streams the bytes to an LED sink, which holds the last byte on LED[7:0].
The step is a shell register at offset 0x00, RW, reset 1. Design ID "RAMP". The board's 100 MHz clock CLK100MHZ;
BTNC resets everything. LED[8] lights when the fast clock is locked.
"""

HIDDEN = """name: ramp_leds
behaviour:
  ramp: ["The ramp runs on a 125 MHz clock made by an MMCM from the 100 MHz board clock"]
  sink: ["The sink may stall the ramp: backpressure is allowed on the link"]
"""


def _bundle() -> dict[str, Any]:
    load = lambda p: yaml.safe_load((FMT / p).read_text())  # noqa: E731
    d = load("design.yaml")
    d.pop("assumptions")
    return {"design": d,
            "contracts": {"ramp": load("modules/ramp/contract.yaml"), "led_sink": load("modules/led_sink/contract.yaml")},
            "module_specs": {"ramp": "Counts by STEP.", "led_sink": "Holds the last byte."},
            "requirements": load("system/requirements.yaml")["requirements"],
            "sources": {"design.shell.design_id": 'Design ID "RAMP"',
                        "design.clocks.clk_sys": "The board's 100 MHz clock CLK100MHZ",
                        "design.board_ports.CLK100MHZ": "The board's 100 MHz clock CLK100MHZ",
                        "design.board_ports.BTNC": "BTNC resets everything",
                        "design.resets.rst_sys": "BTNC resets everything",
                        "ramp.contract.registers": "The step is a shell register at offset 0x00, RW, reset 1",
                        "led_sink.contract.ports.leds": "holds the last byte on LED[7:0]",
                        "design.board_ports.LED[7:0]": "holds the last byte on LED[7:0]",
                        "design.board_ports.LED[8]": "LED[8] lights when the fast clock is locked",
                        "ramp.contract.clocks.clk.max_mhz": "a quote that is not in the spec at all"},
            "reasons": {"led_sink.contract.interfaces.in.backpressure": "a sink that can stall is simpler"}}


def _y(data: Any) -> SimpleNamespace:
    return SimpleNamespace(text="```yaml\n" + yaml.safe_dump(data, sort_keys=False) + "```", prompt_tokens=100,
                           completion_tokens=50, cost=0.001, seconds=0.1)


class FakeDrafter:
    """Replies in order: pass 1, pass 2 draft, (repairs), apply."""

    def __init__(self, replies: list[Any]):
        self.replies, self.prompts = list(replies), []

    def __call__(self, messages: list[dict[str, str]], tools: Any = None) -> SimpleNamespace:
        self.prompts.append(messages[-1]["content"])
        r = self.replies.pop(0)
        return r if isinstance(r, SimpleNamespace) else _y(r)


PASS1 = {"requirements": [{"id": "S-1", "text": "LED[7:0] shows the ramp", "proof": ["simulation"], "modules": []},
                          {"id": "S-2", "text": "Timing closes at 125 MHz", "modules": []}],
         "questions": [{"question": "How fast does the ramp run?", "default": "100 MHz", "reason": "not stated",
                        "settles": ["S-2"]},
                       {"question": "What colour are the LEDs?", "default": "green", "reason": "cosmetic",
                        "settles": ["S-1"]}]}


def _oracle(tmp_path: Path, answers: dict[str, tuple[str, str]], calls: Calls) -> SpecOracle:
    h = tmp_path / "hidden.yaml"
    h.write_text(HIDDEN)

    def llm(system: str, user: str) -> dict[str, Any]:
        q = json.loads(user)["question"]
        calls.add("oracle", "answer", SimpleNamespace(prompt_tokens=10, completion_tokens=5, cost=0.0001, seconds=0))
        for key, (a, quote) in answers.items():
            if key in q:
                return {"answer": a, "quote": quote}
        return {"answer": "not specified", "quote": None}
    return SpecOracle(h, llm)


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "system").mkdir(parents=True)
    (root / "system" / "spec.md").write_text(SPEC)
    return root


ANSWERS = {"May the sink of ramp.out stall": ("yes, backpressure is allowed",
                                             "The sink may stall the ramp: backpressure is allowed on the link"),
           "How fast does the ramp run": ("125 MHz from an MMCM",
                                         "The ramp runs on a 125 MHz clock made by an MMCM from the 100 MHz board clock")}


def _run(tmp_path: Path, replies: list[Any], answers: dict[str, tuple[str, str]] = ANSWERS,
         budget: dict[str, int] | None = None) -> tuple[Path, dict[str, Any], FakeDrafter]:
    root = _project(tmp_path)
    calls = Calls()
    fake = FakeDrafter(replies)
    s = Session(root, Drafter(fake, calls, usd_cap=1.0), _oracle(tmp_path, answers, calls),
                budget=budget or dict(phase0.BUDGET))
    return root, s.run(), fake


def _applied() -> dict[str, Any]:
    b = _bundle()
    b["contracts"]["led_sink"]["summary"] = "unchanged"            # not a field: no unasked change
    return b


def test_the_format_example_is_a_valid_project() -> None:
    p = check_project(FMT)
    assert not p.errors, p.errors


def test_session_writes_valid_files_and_one_question_per_unstated_field(tmp_path: Path) -> None:
    root, out, fake = _run(tmp_path, [PASS1, _bundle(), _applied()])
    assert out["valid"], out["errors"]
    assert set(out["modules"]) == {"ramp", "led_sink"}
    p2 = json.loads((root / "phase0" / "pass2_contracts.json").read_text())
    b = _bundle()
    fields = inventory(b["design"], b["contracts"])
    assert p2["fields"] == len(fields)
    stated = {tuple(x["fields"]) for x in p2["stated"]}
    asked = [tuple(q["fields"]) for q in p2["questions"]]
    assert p2["asked"] == len(fields) - len(stated) == len(asked)        # every field: stated or asked, never both
    assert not stated & set(asked)
    assert ("design.shell.design_id",) in stated and ("ramp.contract.registers",) in stated
    # a quote that is not in the spec does not settle the field
    assert ("ramp.contract.clocks.clk.max_mhz",) in asked
    assert "ramp.contract.clocks.clk.max_mhz" in p2["bad_quotes"]
    # the questions carry the drafter's value as the default and its reason when given
    bp = next(q for q in p2["questions"] if "ramp.contract.interfaces.out.backpressure" in q["fields"])
    assert bp["default"] == "true" and bp["reason"] == "a sink that can stall is simpler"
    assert bp["status"] == "answered" and bp["by"] == "oracle"


def test_link_fields_are_asked_once_for_both_ends() -> None:
    b = _bundle()
    fs = inventory(b["design"], b["contracts"])
    bp = [f for f in fs if f.paths[0].endswith(".backpressure")]
    assert len(bp) == 1 and bp[0].paths == ["ramp.contract.interfaces.out.backpressure",
                                            "led_sink.contract.interfaces.in.backpressure"]
    # an unconnected interface keeps its own fields
    b["design"]["connections"] = []
    assert len([f for f in inventory(b["design"], b["contracts"]) if f.paths[0].endswith(".backpressure")]) == 2


def test_unanswered_questions_become_assumptions(tmp_path: Path) -> None:
    root, out, _ = _run(tmp_path, [PASS1, _bundle(), _applied()])
    d = yaml.safe_load((root / "design.yaml").read_text())
    p1 = json.loads((root / "phase0" / "pass1_requirements.json").read_text())
    p2 = json.loads((root / "phase0" / "pass2_contracts.json").read_text())
    defaulted = [q for q in p1["questions"] + p2["questions"] if q["status"] == "defaulted"]
    assert out["assumptions"] == len(defaulted) == len(d["assumptions"]) > 0
    ids = [a["id"] for a in d["assumptions"]]
    assert ids == [f"A-{n}" for n in range(1, len(ids) + 1)]
    colour = next(a for a in d["assumptions"] if "colour" in a["text"])
    assert colour["affects"] == ["S-1"] and colour["default"] == "green" and colour["status"] == "open"
    lat = [a for a in d["assumptions"] if "led_sink.contract.ports.leds" in a["affects"]]
    assert not lat                                                       # stated by a quote: no question, no assumption
    # the drafter's own assumptions are dropped: only unanswered questions are assumptions
    assert all(a.get("by") in ("oracle", "limit", "default") for a in d["assumptions"])


def test_pass1_answers_reach_the_pass2_prompt_and_proofs_are_filled(tmp_path: Path) -> None:
    root, out, fake = _run(tmp_path, [PASS1, _bundle(), _applied()])
    assert "125 MHz from an MMCM" in fake.prompts[1]
    assert any(n.startswith("S-2: proof") for n in out["notes"])
    p1 = json.loads((root / "phase0" / "pass1_requirements.json").read_text())
    assert p1["asked"] == 2 and p1["answered"] == 1 and p1["questions"][0]["settles"] == ["S-2"]


def test_the_apply_step_gets_the_answers_and_unasked_changes_are_logged(tmp_path: Path) -> None:
    b2 = _applied()
    b2["contracts"]["ramp"]["clocks"][0]["max_mhz"] = 200            # asked but defaulted: not an answered field
    b2["design"]["shell"]["design_id"] = "RMP2"                       # stated in the spec, never asked
    # the drafter keeps its unasked changes through every repair: they are sent back each time, then logged
    root, out, fake = _run(tmp_path, [PASS1, _bundle(), b2, b2, b2])
    assert "yes, backpressure is allowed" in fake.prompts[2]
    assert "design.shell.design_id: you changed this field" in fake.prompts[3]
    p2 = json.loads((root / "phase0" / "pass2_contracts.json").read_text())
    changed = {x["field"] for x in p2["unasked_changes"]}
    assert changed == {"ramp.contract.clocks.clk.max_mhz", "design.shell.design_id"}
    assert p2["drafter_repairs"]["apply"] == phase0.MAX_REPAIRS - 1
    # a drafter that puts the fields back leaves nothing to log
    root, out, fake = _run(tmp_path / "b", [PASS1, _bundle(), b2, _applied()])
    p2 = json.loads((root / "phase0" / "pass2_contracts.json").read_text())
    assert p2["unasked_changes"] == [] and p2["drafter_repairs"]["apply"] == 1


def test_no_apply_call_when_nothing_is_answered(tmp_path: Path) -> None:
    root, out, fake = _run(tmp_path, [PASS1, _bundle()], answers={})
    assert len(fake.prompts) == 2 and out["valid"]
    p2 = json.loads((root / "phase0" / "pass2_contracts.json").read_text())
    assert p2["answered"] == 0 and p2["defaulted"] == p2["asked"]


def test_checker_errors_go_back_to_the_drafter_as_repair_notes(tmp_path: Path) -> None:
    bad = _bundle()
    bad["design"]["connections"] = [{"from": "ramp.out", "to": "nobody.in"}]
    root, out, fake = _run(tmp_path, [PASS1, bad, _bundle(), _applied()])
    assert "project checker rejected" in fake.prompts[2] and "nobody" in fake.prompts[2]
    assert out["valid"]
    p2 = json.loads((root / "phase0" / "pass2_contracts.json").read_text())
    assert p2["drafter_repairs"]["draft"] == 1
    # a reply that is not YAML is a repair note too
    root2, out2, fake2 = _run(tmp_path / "b", [SimpleNamespace(text="```yaml\n: : :\n```", prompt_tokens=1,
                                                              completion_tokens=1, cost=0.0, seconds=0), PASS1,
                                              _bundle(), _applied()])
    assert "not valid YAML" in fake2.prompts[1] and out2["valid"]


def test_budget_overflow_is_defaulted_by_limit_and_kept_as_assumptions(tmp_path: Path) -> None:
    root, out, _ = _run(tmp_path, [PASS1, _bundle(), _applied()], budget={"requirements": 1, "contracts": 3})
    p2 = json.loads((root / "phase0" / "pass2_contracts.json").read_text())
    assert sum(q["by"] == "limit" for q in p2["questions"]) == p2["asked"] - 3
    d = yaml.safe_load((root / "design.yaml").read_text())
    assert sum(a["by"] == "limit" for a in d["assumptions"]) >= p2["asked"] - 3


def test_usd_cap_stops_the_drafter(tmp_path: Path) -> None:
    root = _project(tmp_path)
    calls = Calls()
    s = Session(root, Drafter(FakeDrafter([PASS1, _bundle()]), calls, usd_cap=0.0005), None)
    s.drafter.calls.rows.append({"who": "drafter", "step": "x", "prompt_tokens": 0, "completion_tokens": 0,
                                 "cost": 0.001, "seconds": 0})
    with pytest.raises(phase0.BudgetExceeded):
        s.run()


def test_interview_off_defaults_everything(tmp_path: Path) -> None:
    root = _project(tmp_path)
    s = Session(root, Drafter(FakeDrafter([PASS1, _bundle()]), Calls(), 1.0), None)
    out = s.run()
    p2 = json.loads((root / "phase0" / "pass2_contracts.json").read_text())
    assert out["valid"] and p2["answered"] == 0 and all(q["by"] == "default" for q in p2["questions"])


def test_quote_rule() -> None:
    assert quote_ok('Design ID "RAMP"', SPEC)
    assert quote_ok("holds the   last byte\non LED[7:0]", SPEC)          # whitespace normalised
    assert not quote_ok("RAM", SPEC)                                     # too short to count
    assert not quote_ok("LED[7:0]", SPEC) and not quote_ok("Design ID", SPEC)   # a bare name states nothing
    assert not quote_ok("the ramp runs at 125 MHz", SPEC)
    assert not quote_ok(None, SPEC)


def test_register_field_question_takes_the_oracles_whole_map_path() -> None:
    b = _bundle()
    f = next(f for f in contract_fields("ramp", b["contracts"]["ramp"]) if f.paths[0] == "ramp.contract.registers")
    assert is_register_question(f.ask)


def test_values_by_path_sees_both_ends_of_a_link() -> None:
    b = _bundle()
    v = values_by_path(b["design"], b["contracts"])
    assert v["ramp.contract.interfaces.out.backpressure"] == "true"
    assert v["led_sink.contract.interfaces.in.source_gaps"] == "true"


def test_spec_yaml_must_agree_with_the_contract() -> None:
    c = yaml.safe_load((FMT / "modules" / "ramp" / "contract.yaml").read_text())
    spec = {"ports": [{"name": p["name"], "dir": p["dir"], "width": 8 if p["name"] in ("step", "m_axis_tdata") else 1}
                      for p in c["ports"]],
            "registers": {"map": [{"name": "STEP", "offset": "0x00", "access": "RW"}]}}
    assert spec_contract_errors(spec, c) == []
    bad = copy.deepcopy(spec)
    bad["ports"][2]["width"] = 4
    bad["ports"].append({"name": "extra", "dir": "out", "width": 1})
    bad["registers"]["map"][0]["access"] = "RO"
    errs = spec_contract_errors(bad, c)
    assert any("step: spec.yaml says width 4" in e for e in errs)
    assert any("extra: in spec.yaml, not in the contract" in e for e in errs)
    assert any("STEP RO, the contract STEP RW" in e for e in errs)


def test_cli_spec_replay(tmp_path: Path) -> None:
    from project.cli import main
    root = _project(tmp_path)
    rec = tmp_path / "calls.json"
    rows = [_y(x).__dict__ | {"tool_calls": [], "provider": None} for x in (PASS1, _bundle())]
    rec.write_text(json.dumps(rows))
    assert main(["spec", str(root), "--interview", "off", "--replay", str(rec)]) == 0
    assert (root / "phase0" / "session.json").is_file() and (root / "design.yaml").is_file()
    assert main(["check", str(root)]) == 0
    assert main(["spec", str(tmp_path / "nowhere"), "--interview", "off", "--replay", str(rec)]) == 1


def test_left_out_latency_and_throughput_are_asked() -> None:
    b = _bundle()
    led = b["contracts"]["led_sink"]
    led["interfaces"].append({"name": "out", "protocol": "axi4-stream", "role": "master", "prefix": "m_axis",
                              "clock": "clk", "reset": "rst", "tdata": {"width": 8}})
    paths = {p for f in contract_fields("led_sink", led) for p in f.paths}
    assert {"led_sink.contract.latency.in.out", "led_sink.contract.throughput.out"} <= paths
    # a stated latency is not asked twice
    led["latency"] = [{"from": "in", "to": "out", "cycles": 3}]
    assert [f.paths for f in contract_fields("led_sink", led)].count(["led_sink.contract.latency.in.out"]) == 1


def test_a_contract_for_a_module_not_in_the_design_is_a_repair_note(tmp_path: Path) -> None:
    bad = _bundle()
    bad["contracts"]["fpga_shell"] = copy.deepcopy(bad["contracts"]["led_sink"])
    root, out, fake = _run(tmp_path, [PASS1, bad, _bundle(), _applied()])
    assert "fpga_shell is not in design.modules" in fake.prompts[2] and out["valid"]
    assert not (root / "modules" / "fpga_shell").exists()


def test_an_apply_step_that_never_passes_keeps_the_draft_and_the_answers_as_assumptions(tmp_path: Path) -> None:
    bad = _bundle()
    bad["design"]["connections"] = [{"from": "ramp.out", "to": "nobody.in"}]
    root, out, fake = _run(tmp_path, [PASS1, _bundle(), bad, bad, bad, bad])
    assert out["valid"]
    p2 = json.loads((root / "phase0" / "pass2_contracts.json").read_text())
    assert p2["apply_failed"] and p2["answered"] == 0
    kept = [q for q in p2["questions"] if q["by"] == "oracle, not applied"]
    assert kept and kept[0]["answer"] == "yes, backpressure is allowed"
    d = yaml.safe_load((root / "design.yaml").read_text())
    assert any(a["default"] == "yes, backpressure is allowed" and a["status"] == "open" for a in d["assumptions"])


def test_the_last_apply_repair_is_kept_for_checker_errors(tmp_path: Path) -> None:
    b2 = _applied()
    b2["design"]["shell"]["design_id"] = "RMP2"                       # unasked: sent back twice, then only logged
    root, out, fake = _run(tmp_path, [PASS1, _bundle(), b2, b2, b2])
    p2 = json.loads((root / "phase0" / "pass2_contracts.json").read_text())
    assert p2["apply_failed"] is None and p2["drafter_repairs"]["apply"] == 2
    assert [x["field"] for x in p2["unasked_changes"]] == ["design.shell.design_id"]
