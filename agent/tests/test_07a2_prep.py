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
    a, q = o.answer(Question("q1", "At which offset is the result register Y?", "0x08", "r"))
    assert a == "0x08" and q
    assert "Register map" in seen["system"] and "A_LO: offset 0x00, RW" in seen["system"]
    a, _ = o.answer(Question("q2", "Offset of ACC?", "0x09", "r"))
    assert a == "0x09"                                                          # quote differs only in white space
    a, q = o.answer(Question("q3", "Offset of an invented register?", "0x0B", "r"))
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
