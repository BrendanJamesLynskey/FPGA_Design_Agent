"""Brief 05k: the `mutate` tool is in the schema and returns 'busy, retry' when the heavy lock is held. (05l: no role is
offered it; the harness runs it itself, see test_05l.)"""

from agent.core import dispatch
import agent.core.tools  # noqa: F401  (registers the tools)
from agent.core.registry import TOOLS
from agent.core.runner import RunResult
from agent.core.session import ROOT
from agent.graph import run as R


def test_mutate_is_a_registered_tool_with_schema():
    assert "mutate" in TOOLS and "mutate" in R.FLOW_TOOLS
    assert set(TOOLS["mutate"].input_schema["properties"]) == {"max_mutants", "seed", "lock_wait_s"}


def test_no_role_is_offered_it():
    a = ("lint", "mutate", "simulate")
    for role, n, level in (("tests", 2, "V3"), ("tests", 2, "V2"), ("rtl", 2, "V3"), ("tests", 9, "V3")):
        assert R.role_tools(role, n, level, a) == ("lint", "simulate")


def test_busy_result(session):
    rt = type("RT", (), {"session": session})
    rt.session.runner = type("R", (), {"run": lambda self, kind, argv, cwd, env=None, timeout=600:
                                       RunResult(75, "BUSY: another heavy job holds the lock (s j 1 2); retry later", "", 0.1)})()
    r = dispatch(rt.session, "mutate", {"lock_wait_s": 0})
    assert r["ok"] is False and r["busy"] is True and r["output"].startswith("busy, retry")


def test_result_carries_the_survivors_in_words(session):
    import json
    rt = type("RT", (), {"session": session, "design": session.design})
    out = rt.design / "build" / "verif" / "mutation.json"

    class Fake:
        def run(self, kind, argv, cwd, env=None, timeout=600):
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps({"score_pct": 50.0, "evaluated": 2, "killed": 1, "survived": 1,
                                       "survivor_text": ["rtl/x.sv line 3: `a == b` became `a != b`"]}))
            return RunResult(0, "mutation score 50.0%", "", 1.0)
    rt.session.runner = Fake()
    r = dispatch(rt.session, "mutate", {})
    assert r["ok"] and r["score_pct"] == 50.0 and r["surviving_mutants"] == ["rtl/x.sv line 3: `a == b` became `a != b`"]
