"""Brief 182: the files behind the live console (tool output, the Claude Code stream), the run events in the trace, and the status, ask and request commands."""

import json
import sys
from pathlib import Path

import pytest

from agent.core import console
from agent.core.runner import LocalRunner, RunResult
from agent.core.trace import Trace
from agent.models import claude_cli


def rows(rd: Path):
    return [json.loads(ln) for ln in (rd / "trace.jsonl").read_text().splitlines()]


def test_a_tool_run_leaves_a_console_file_and_trace_pointers(tmp_path):
    r = LocalRunner()
    console.install(r, tmp_path, lambda: "synthesis")
    res = r.run("build", [sys.executable, "-c", "import sys; print('Starting synth_design'); print('warn', file=sys.stderr)"], tmp_path)
    assert res.returncode == 0 and res.stdout == "Starting synth_design\n" and "warn" in res.stderr           # the caller sees exactly what it saw before
    f = tmp_path / "console" / "001_build.log"
    assert f.read_text() == "Starting synth_design\n"
    ev = [x for x in rows(tmp_path) if x["kind"] == "event"]
    assert [e["event"] for e in ev] == ["console", "console_end"]
    assert ev[0]["step"] == "001_build" and ev[0]["stream"] == "tool_output" and ev[0]["source"] == "console/001_build.log" and ev[0]["stage"] == "synthesis"
    assert ev[1]["returncode"] == 0 and ev[1]["seconds"] >= 0
    r.run("lint", [sys.executable, "-c", "print(1)"], tmp_path)
    assert (tmp_path / "console" / "002_lint.log").is_file()                                                    # numbering continues
    console.install(r, tmp_path)                                                                                # installing twice wraps once
    r.run("lint", [sys.executable, "-c", "print(2)"], tmp_path)
    assert (tmp_path / "console" / "003_lint.log").is_file() and not (tmp_path / "console" / "004_lint.log").exists()


def test_the_console_file_grows_while_the_tool_runs(tmp_path):
    import threading
    import time
    r = LocalRunner()
    console.install(r, tmp_path)
    out = []
    t = threading.Thread(target=lambda: out.append(r.run("sim", [sys.executable, "-u", "-c", "import time; print('first'); time.sleep(1.5); print('second')"], tmp_path)))
    t.start()
    f = tmp_path / "console" / "001_sim.log"
    deadline = time.time() + 10
    while time.time() < deadline and not (f.is_file() and "first" in f.read_text()):
        time.sleep(0.05)
    assert "first" in f.read_text() and "second" not in f.read_text() and t.is_alive()                          # readable before the tool has ended
    t.join()
    assert out[0].stdout == "first\nsecond\n"


def test_a_runner_that_does_not_stream_still_leaves_its_output(tmp_path):
    class Fake:
        def run(self, kind, argv, cwd, env=None, timeout=600):
            return RunResult(1, "out text", "err text", 0.1)
    f = Fake()
    console.install(f, tmp_path)
    assert f.run("simulate", ["x"], tmp_path).stdout == "out text"
    assert (tmp_path / "console" / "001_simulate.log").read_text() == "out text\n--- stderr ---\nerr text"
    assert [e["returncode"] for e in rows(tmp_path) if e.get("event") == "console_end"] == [1]


def test_the_claude_code_stream_is_written_to_a_file_as_it_arrives(tmp_path):
    f = tmp_path / "console" / "001_rtl.log"
    p = claude_cli.run([sys.executable, "-c", "print('{\"type\":\"result\"}')"], cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, timeout=30, stdout_file=f)
    assert p.returncode == 0 and p.stdout == '{"type":"result"}\n' and f.read_text() == p.stdout
    q = claude_cli.run([sys.executable, "-c", "print(1)"], cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, timeout=30)
    assert q.stdout == "1\n"                                                                                    # without a file: as before


def test_trace_events_share_the_one_trace_file_and_carry_no_prompt(tmp_path):
    t = Trace(tmp_path / "trace.jsonl")
    t.model("m", {"input": 1, "output": 1}, 0.0, "clarify")
    t.event("stage_start", "clarify", n=0, visit=1)
    got = rows(tmp_path)
    assert [x["kind"] for x in got] == ["model", "event"] and got[1]["event"] == "stage_start" and got[1]["n"] == 0


@pytest.fixture
def run_dir(tmp_path):
    rd = tmp_path / "runs" / "20261122-000000-cccc"
    rd.mkdir(parents=True)
    (rd / "config.json").write_text(json.dumps({"name": "t1", "run_limits": {"usd": 3.0}, "hidden_spec": "None"}))
    (rd / "trace.jsonl").write_text(json.dumps({"v": 1, "kind": "event", "event": "stage_start", "stage": "clarify", "t": 1.0, "n": 0, "visit": 1}) + "\n")
    return rd


def test_the_status_ask_and_request_commands(run_dir, capsys, monkeypatch):
    from agent.__main__ import main
    assert main(["status", str(run_dir)]) == 0
    out = capsys.readouterr().out
    assert "Doing now:" in out and "Next:" in out and "Cost:" in out
    assert main(["request", str(run_dir), "--control", "stop-after", "2"]) == 0
    assert "request r001 queued: stop after stage 2" in capsys.readouterr().out
    assert main(["request", str(run_dir), "--design", "use block RAM for the FIFO"]) == 0
    assert main(["request", str(run_dir), "--control", "stop-after"]) == 2 and main(["request", str(run_dir), "--control", "pause", "3"]) == 2
    with pytest.raises(SystemExit):                                                                              # a flag is not text
        main(["request", str(run_dir), "--design", "--allow-fable"])
    capsys.readouterr()
    assert main(["status", str(run_dir)]) == 0
    assert "request r001" in capsys.readouterr().out
    assert main(["status", str(run_dir), "--console"]) == 0
    from navigator import ask as NA
    monkeypatch.setattr(NA, "default_llm", lambda: (lambda s, u: {"text": "It is at stage 0 [R1].", "plan_estimate_usd": 0.02, "cost_usd": None, "tokens": 5, "model": "claude-sonnet-5-5"}))
    assert main(["ask", str(run_dir), "Where is it?"]) == 0
    out = capsys.readouterr().out
    assert "It is at stage 0 [R1]." in out and "cited: R1" in out and "plan estimate" in out
    with pytest.raises(SystemExit):                                                                              # a flag-looking question is not accepted as text either
        main(["ask", str(run_dir), "-x"])
    assert main(["ask", str(run_dir), "- x"]) == 2


def test_the_claude_code_arm_tools_run_in_the_mcp_server_and_leave_console_files_too(tmp_path, monkeypatch):
    """The Claude Code arm runs the agent's tools in a separate MCP server process: the arm names the run in FDA_RUN_DIR and the server installs the console on its runner."""
    from types import SimpleNamespace

    from agent.claude_code_arm import arm
    from agent.mcp_server import server
    rt = SimpleNamespace(run_dir=tmp_path / "run", design=tmp_path / "run" / "d", cfg=SimpleNamespace(board="nexys_a7_100t", skill_routing="off"))
    cfg = arm.mcp_config(rt, {"role": "rtl", "stage": "synthesis", "file_tools": [], "core_tools": []})
    assert cfg["mcpServers"]["fda"]["env"]["FDA_RUN_DIR"] == str(rt.run_dir)
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "d").mkdir()
    got = []
    monkeypatch.setenv("FDA_RUN_DIR", str(tmp_path / "run"))
    monkeypatch.setattr(server.anyio, "run", lambda f, s, t: got.append(s))
    assert server.main(["--design", str(tmp_path / "run" / "d"), "--stage", "synthesis"]) == 0
    s = got[0]
    assert s.runner._console_installed == str(tmp_path / "run")
    s.runner.run("simulate", [sys.executable, "-c", "print('PASS')"], tmp_path)
    assert (tmp_path / "run" / "console" / "001_simulate.log").read_text() == "PASS\n"
    assert [e["stage"] for e in rows(tmp_path / "run") if e.get("event") == "console"] == ["synthesis"]


def test_a_container_runner_streams_through_its_inner_local_runner(tmp_path):
    class Outer:                                                    # what ContainerRunner does: hand the run, re-argv'd, to ``inner``
        def __init__(self):
            self.inner = LocalRunner()

        def run(self, kind, argv, cwd, env=None, timeout=600):
            return self.inner.run(kind, argv, cwd, env, timeout)
    o = Outer()
    console.install(o, tmp_path)
    res = o.run("simulate", [sys.executable, "-c", "print('4 passed')"], tmp_path)
    assert res.stdout == "4 passed\n" and (tmp_path / "console" / "001_simulate.log").read_text() == "4 passed\n" and o.inner._tee_to is None
