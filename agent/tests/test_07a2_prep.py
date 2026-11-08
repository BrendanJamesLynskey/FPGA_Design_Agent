"""Brief 07a2-prep, the parts that need the agent package: lint and conventions for a UART-subject design, the task data
files in the run, and the interview oracle's register-map answers (see flow/tests/test_07a2_prep.py for the flow side)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from flow.srcorder import NO_SHELL_MARKER

ROOT = Path(__file__).resolve().parents[2]
OWN_UART = "module uart_rx (input logic clk, output logic v);\n  assign v = 1'b1;\nendmodule\n"
TOP_NOSHELL = ("module nsh_top (input logic clk, output logic v);\n  logic w;\n  uart_rx u (.clk(clk), .v(w));\n"
               "  assign v = w;\nendmodule\n")


def write(d: Path, files: dict) -> list:
    d.mkdir(parents=True, exist_ok=True)
    for n, t in files.items():
        (d / n).write_text(t)
    return [d / n for n in files]


def test_lint_and_standards_drop_the_shell_for_no_shell_designs(session) -> None:
    from agent.core import dispatch
    d = session.design
    (d / "rtl").mkdir(exist_ok=True)
    for f in (d / "rtl").glob("*"):
        f.unlink()
    write(d / "rtl", {"uart_rx.sv": OWN_UART, "nsh_top.sv": TOP_NOSHELL})
    (d / NO_SHELL_MARKER).write_text("")
    (d / "spec.yaml").unlink(missing_ok=True)        # 08a: the T1 spec's ports are not this toy top's (FDA-CON-8 would fire)
    cfg = yaml.safe_load((d / "build.yaml").read_text())
    cfg["top"] = "nsh_top"
    cfg["sources"] = ["shell/rtl/*.sv", f"{d.relative_to(session.root)}/rtl/*.sv"]
    (d / "build.yaml").write_text(yaml.safe_dump(cfg))
    r = dispatch(session, "lint", {})
    argv = session.runner.calls[-1][1]
    assert not any("shell/rtl" in a for a in argv) and any(a.endswith("rtl/uart_rx.sv") for a in argv), argv
    assert r["ok"]


def test_conventions_text_for_no_shell_names_no_shell() -> None:
    from agent.graph.run import conventions_text, tests_conventions_text
    fmt = {"board": "nexys_a7_100t", "name": "x", "stage": 2, "stage_name": "s", "allowed": "a", "fails": "none",
           "note": "none", "design_rel": "runs/r/x"}
    plain = conventions_text(fmt)
    assert "shell/rtl/*.sv, runs/r/x/rtl/*.sv" in plain and "must instantiate the test shell" in plain
    ns = conventions_text({**fmt, "no_shell": True})
    assert "sources: [runs/r/x/rtl/*.sv]" in ns and "does NOT use the test shell" in ns
    assert "must instantiate the test shell" not in ns and "SHELL_RTL" not in ns
    assert "SHELL_RTL" in tests_conventions_text(fmt) and "SHELL_RTL" not in tests_conventions_text({**fmt, "no_shell": True})


def test_task_no_shell_is_read_from_the_bench_yaml_next_to_the_hidden_spec() -> None:
    from agent.__main__ import task_no_shell
    t = ROOT / "benchmark" / "course" / "tasks"
    assert task_no_shell(t / "c16_nexys_aes_uart" / "hidden" / "spec.yaml") is True
    assert task_no_shell(t / "c14_int8_dot_requant" / "hidden" / "spec.yaml") is False
    assert task_no_shell(None) is False


def test_install_data_files_copies_lists_and_protects(tmp_path: Path) -> None:
    from agent.core.security import PathJail, SecurityError
    from agent.graph.roles import ROLES
    from agent.graph.run import install_data_files
    src = tmp_path / "task" / "data"
    write(src, {"w.hex": "00\n01\n", "img.hex": "ff\n"})
    design = tmp_path / "run" / "x"
    design.mkdir(parents=True)
    (design / "spec.md").write_text("# request\n")
    got = install_data_files(design, src)
    assert got == ["img.hex", "w.hex"] and (design / "data" / "w.hex").read_text() == "00\n01\n"
    spec = (design / "spec.md").read_text()
    assert "## Data files supplied" in spec and "data/w.hex (6 bytes)" in spec and "readmemh" in spec
    j = PathJail(design)
    assert j.resolve("data/w.hex").is_file() and j.resolve("/data/w.hex").is_file()
    with pytest.raises(SecurityError):
        j.resolve("data/w.hex", write=True)
    for role in ("clarify", "model", "tests", "rtl"):
        assert any(__import__("fnmatch").fnmatch("data/w.hex", p) for p in ROLES[role]["read"]), role


def test_oracle_prompt_carries_the_register_map_and_quotes_are_checked() -> None:
    from agent.graph.interview import Question, SpecOracle, render_register_map
    hidden = ROOT / "benchmark" / "course" / "tasks" / "c14_int8_dot_requant" / "hidden" / "spec.yaml"
    text = hidden.read_text()
    rendered = render_register_map(text)
    assert "Y: offset 0x08, RO, reset 0:" in rendered and "GO: offset 0x07, WO" in rendered
    seen = {}
    replies = iter([
        {"answer": "0x08", "quote": "Y: offset 0x08, RO, reset 0: [7:0] limited answer (two's complement); [31:8] read 0"},
        {"answer": "0x09", "quote": "{offset: 0x09,   name: ACC, access: RO,\n reset: 0, bits: \"[31:0] the signed accumulator including the bias\"}"},
        {"answer": "0x0B", "quote": "RESULT: offset 0x0B"}])

    def llm(system, user):
        seen["system"] = system
        return next(replies)
    o = SpecOracle(hidden, llm)
    a, q = o.answer(Question("q1", "What does the Y field hold?", "0x08", "r"))
    assert a == "0x08" and q
    assert "Register map" in seen["system"] and "A_LO: offset 0x00, RW" in seen["system"]
    a, _ = o.answer(Question("q2", "What does ACC hold?", "0x09", "r"))
    assert a == "0x09"                                                          # quote differs only in white space
    a, q = o.answer(Question("q3", "What does an invented field hold?", "0x0B", "r"))
    assert a == "not specified" and q is None                                  # an invented quote is still refused


def test_oracle_register_questions_work_for_every_course_task_with_a_map() -> None:
    from agent.graph.interview import render_register_map
    n = 0
    for h in sorted((ROOT / "benchmark" / "course" / "tasks").glob("*/hidden/spec.yaml")):
        spec = yaml.safe_load(h.read_text())
        rows = (spec.get("registers") or {}).get("map") or []
        if rows:
            n += 1
            r = render_register_map(h.read_text())
            assert all(str(x["name"]) + ": offset" in r for x in rows), h
    assert n >= 5


def test_cc_oracle_parses_replies_and_never_uses_openrouter() -> None:
    from agent.claude_code_arm.oracle import _argv, parse_answer
    assert parse_answer('{"answer": "x", "quote": "y"}') == {"answer": "x", "quote": "y"}
    assert parse_answer('```json\n{"answer": "x", "quote": null}\n```')["answer"] == "x"
    assert parse_answer('Here: {"answer": "x", "quote": "q"} done')["quote"] == "q"
    assert parse_answer("no json")["answer"] == "not specified"
    a = _argv("S", "U", "claude-haiku-5-5")
    assert a[a.index("--tools") + 1] == "" and "--strict-mcp-config" in a and "claude-haiku-5-5" in a
    from agent.__main__ import _NoOpenRouter
    with pytest.raises(RuntimeError):
        _NoOpenRouter()()


def test_a_caller_that_holds_the_heavy_slot_can_give_mutate_its_own_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    """The mutation tool takes the machine's heavy-slot lock itself and reports busy when the caller already holds it; the
    caller sets FDA_HEAVY_LOCK to a private path, and the scrubbed tool environment must carry it."""
    from agent.core.runner import scrubbed_env
    monkeypatch.setenv("FDA_HEAVY_LOCK", "/tmp/x/private.lock")
    assert scrubbed_env(tools={})["FDA_HEAVY_LOCK"] == "/tmp/x/private.lock"


# --- 07a2 fix 1: the register map is asked for, and the oracle answers with the whole map ------------------------

RUN1_QUESTION = "What are the shell's actual register addressing and word format?"      # recorded in run 1 (oracle_calls.jsonl)
C14 = ROOT / "benchmark" / "course" / "tasks" / "c14_int8_dot_requant"


def test_oracle_answers_a_register_addressing_question_with_the_whole_map() -> None:
    from agent.graph.interview import Question, SpecOracle

    def llm(system, user):                  # the old behaviour: prose that does not list the map
        return {"answer": "Partly specified. Offsets 0x00 to 0x0A; byte or word not stated.", "quote": "shell: shell/PROTOCOL.md (version 1.0)"}
    o = SpecOracle(C14 / "hidden" / "spec.yaml", llm)
    a, quote = o.answer(Question("q1", RUN1_QUESTION, "32-bit word registers", "r"))
    rows = [l for l in a.splitlines() if ": offset 0x" in l]
    assert len(rows) == 11 and rows[0].startswith("A_LO: offset 0x00, RW") and rows[8].startswith("Y: offset 0x08, RO"), a
    assert quote in o._text
    # a question that is not about the map still goes to the model
    a, _ = o.answer(Question("q2", "Should ready clear when a new go is issued?", "yes", "r"))
    assert a.startswith("Partly")


def test_register_question_detector() -> None:
    from agent.graph.interview import is_register_question
    for t in (RUN1_QUESTION, "Which offset is the result register?", "What is the register map?", "Offsets and widths of the registers?"):
        assert is_register_question(t), t
    for t in ("Should ready clear on go?", "What baud rate does the shell use?", "Does the register file reset?"):
        assert not is_register_question(t), t


def test_clarify_gate_needs_a_register_map_question_when_the_request_gives_no_offsets() -> None:
    from agent.graph.interview import register_map_errors
    req = (C14 / "spec.md").read_text()
    spec = {"registers": {"map": [{"offset": 0, "name": "ID", "access": "RO", "reset": 0, "bits": "x"}]},
            "open_questions": [{"question": "What if bias overflows?", "default": "wrap", "reason": "r"}]}
    errs = register_map_errors(req, spec)
    assert errs and "register map" in errs[0]                                  # run 1's spec: invented map, no question
    spec["open_questions"].append({"question": RUN1_QUESTION, "default": "d", "reason": "r"})
    assert register_map_errors(req, spec) == []
    # a request that gives offsets, or names no registers, is not asked
    assert register_map_errors("Registers: | 0x00 | A | RW |", {}) == []
    assert register_map_errors("A blinking LED on the board.", {}) == []


def test_clarify_gate_checks_the_answered_map_reaches_registers_map() -> None:
    from agent.graph.interview import Question, SpecOracle, register_map_errors
    req = (C14 / "spec.md").read_text()
    o = SpecOracle(C14 / "hidden" / "spec.yaml", lambda s, u: {"answer": "not specified", "quote": None})
    ans, _ = o.answer(Question("q1", RUN1_QUESTION, "d", "r"))
    spec = {"registers": {"map": [{"offset": 0, "name": "ID", "access": "RO", "reset": 0, "bits": "x"}]},
            "resolved_questions": [{"question": RUN1_QUESTION, "answer": ans, "status": "answered", "by": "oracle"}]}
    errs = register_map_errors(req, spec)
    assert errs and "0x08" in errs[0]
    spec["registers"]["map"] = [{"offset": i, "name": f"R{i}", "access": "RW", "reset": 0, "bits": "x"} for i in range(11)]
    assert register_map_errors(req, spec) == []


def test_clarify_prompt_tells_the_agent_to_ask_for_the_register_map() -> None:
    from agent.graph.run import PROMPTS
    assert "REGISTER MAP" in PROMPTS["clarify"] and "must not invent" in PROMPTS["clarify"]
