"""Brief 05l: the V3 evidence is produced by the harness, and no text addressed to a role names a tool the role does not
have. The guard builds the role's tool tuple from the code path the graph uses (``role_allowed`` -> ``role_tools`` ->
the registry) and every text the roles are given: prompts, the stage-entry checklist, the repair notes and the gate's
``why`` texts."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import agent.core.tools  # noqa: F401  (registers the tools)
from agent.core.registry import TOOLS
from agent.graph import repair as repair_mod
from agent.graph import run as R
from agent.graph.stages import MACHINE
from flow import verif_gates as G

ROOT = Path(__file__).resolve().parents[2]
ROLES = ("clarify", "model", "tests", "rtl")
LEVELS = ("V1", "V2", "V3")


def tool_mentions(text: str) -> set[str]:
    """Registered tool names a text tells its reader to use: a backticked name (or call), ``name(`` or "call/run/use name"."""
    found = set()
    for name in TOOLS:
        pats = (rf"`{name}(?:\(|`)", rf"(?<![\w.]){name}\(", rf"\b(?:call|calls|calling|run|use|using)\s+(?:the\s+)?{name}\b")
        if any(re.search(p, text) for p in pats):
            found.add(name)
    return found


def role_tool_set(role: str, stage_n: int, level: str) -> set[str]:
    return set(R.effective_tools(role, stage_n, level))


def _strings(path: Path) -> list[str]:
    return [n.value for n in ast.walk(ast.parse(path.read_text())) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _fake_rt(level: str, name: str = "t1_dimmer_counter"):
    return SimpleNamespace(cfg=SimpleNamespace(name=name, verif_level=level))


@pytest.fixture(params=[True, False], ids=["sby", "no_sby"])
def sby(request, monkeypatch):
    import agent.core.runner as runner
    monkeypatch.setattr(runner, "tool_available", lambda n: request.param if n == "sby" else True)
    return request.param


def addressed_texts(sby) -> list[tuple[str, int, str, str, str]]:
    """(role, stage, level, label, text) for everything a role is given that names tools."""
    out = []
    fmt = {"board": "nexys_a7_100t", "name": "t1_dimmer_counter", "stage": 2, "stage_name": "x", "allowed": "x",
           "fails": "none", "note": "none", "design_rel": "designs/t1_dimmer_counter"}
    for level in LEVELS:
        for n in (2, 9):
            for repair in (False, True):
                out.append(("tests", n, level, f"checklist stage {n} repair={repair}", R.tests_checklist(_fake_rt(level), n, repair)))
    for role, key, n in (("clarify", "clarify", 0), ("model", "model", 2), ("tests", "tests", 2), ("tests", "hwtests", 9)):
        for level in LEVELS:
            out.append((role, n, level, f"prompt {key}", R.PROMPTS[key].format(**fmt)))
    for level in LEVELS:
        out.append(("tests", 2, level, "tests conventions", R.tests_conventions_text(fmt)))
        for n in range(1, 10):
            out.append(("rtl", n, level, "conventions", R.conventions_text({**fmt, "stage": n})))
            out.append(("rtl", n, level, "rtl prompt", R.PROMPTS["rtl"].format(**{**fmt, "stage": n})))
    for level in LEVELS:
        out.append(("tests", 9, level, "HW_FORMAT", R.HW_FORMAT.format(**fmt)))
        out.append(("tests", 2, level, "FRESH_TESTS", R.FRESH_TESTS))
    return out


#: A finding the guard made that is not fixed here (brief 05l, "follow-ups"): the shared CONVENTIONS text tells the RTL
#: writer to call board_constraints, a tool only stages 1 and 3 have, at stages 2 and 4-9. Listing it keeps a NEW
#: mismatch failing; fixing it means deleting the entries.
KNOWN_GAPS = {("rtl", n, "conventions"): {"board_constraints"} for n in (2, 4, 5, 6, 7, 8, 9)}
#: brief 71: HW_FORMAT's ``check(samples)`` is the hw_checks.py function the Verifier writes, not the ``check`` tool
KNOWN_GAPS[("tests", 9, "HW_FORMAT")] = {"check"}


def test_every_text_names_only_tools_its_role_has(sby):
    bad = []
    for role, n, level, label, text in addressed_texts(sby):
        missing = tool_mentions(text) - role_tool_set(role, n, level) - KNOWN_GAPS.get((role, n, label), set())
        if missing:
            bad.append(f"{role} stage {n} {level} {label}: {sorted(missing)}")
    assert not bad, "\n".join(bad)


def test_gate_why_texts_name_only_tools_the_tests_role_has():
    """Every string literal of the V0-V3 gates and the repair router: they are addressed to the tests role (or the model
    writer, which has no flow tool at all)."""
    have = role_tool_set("tests", 2, "V3")
    bad = []
    for path in (ROOT / "flow" / "verif_gates.py", ROOT / "agent" / "graph" / "repair.py"):
        for s in _strings(path):
            missing = tool_mentions(s) - have
            if missing:
                bad.append(f"{path.name}: {sorted(missing)} in {s[:120]!r}")
    assert not bad, "\n".join(bad)


# --- the harness produces the V3 evidence ---------------------------------------------------------------------------

def test_mutate_is_offered_to_no_role():
    for role in ROLES:
        for n in range(len(MACHINE)):
            for level in LEVELS:
                assert "mutate" not in R.effective_tools(role, n, level)
    assert "mutate" not in next(st for st in MACHINE if st.n == 2).tools and "mutate" in TOOLS      # still a registered tool


def test_role_tools_match_what_the_graph_hands_each_role():
    assert set(R.effective_tools("tests", 2, "V3")) == {"read_file", "write_file", "list_files", "search_docs", "load_skill",
                                                       "spec_items", "formal"}
    assert set(R.effective_tools("model", 2, "V3")) == {"read_file", "write_file"}
    assert "simulate" in R.effective_tools("rtl", 2, "V3") and "program" not in R.effective_tools("rtl", 9, "V3")


class _Calls:
    def __init__(self, sim=None, mut=None):
        self.calls, self.sim, self.mut = [], sim, mut

    def __call__(self, sess, name, args=None):
        self.calls.append((name, dict(args or {})))
        if name == "simulate":
            return self.sim if self.sim is not None else {"ok": True, "output": "passed"}
        if name == "mutate":
            return self.mut if self.mut is not None else {"ok": True, "output": "score 100"}
        raise AssertionError(name)


def _rt(session):
    return SimpleNamespace(design=session.design, session=session)


def _v3(session, monkeypatch, sims=("icarus", "verilator"), **kw):
    import agent.core.tools as T
    monkeypatch.setenv("FDA_HEAVY_LOCK", str(session.design.parent / "lock"))
    monkeypatch.setattr(T, "available_sims", lambda: sims)
    calls = _Calls(**kw)
    monkeypatch.setattr(R, "dispatch", calls)
    return calls, R.v3_evidence(_rt(session), True)


def test_the_harness_runs_the_coverage_simulation_then_the_mutation_run(session, monkeypatch):
    calls, st = _v3(session, monkeypatch)
    assert [c[0] for c in calls.calls] == ["simulate", "mutate"]
    assert calls.calls[0][1] == {"sim": "verilator", "coverage": True}
    assert calls.calls[1][1] == R.V3_MUTATION_ARGS
    assert st["coverage"]["ok"] and st["mutation"]["ok"]
    assert (session.design / "build" / "verif" / "v3_evidence.json").is_file()


def test_busy_lock_is_recorded_as_not_measured_with_the_reason(session, monkeypatch, tmp_path):
    _, st = _v3(session, monkeypatch, mut={"ok": False, "busy": True, "output": "busy, retry: held"})
    assert st["mutation"]["busy"] and "busy" in st["mutation"]["why"]
    rep = _gate_text(session, tmp_path)
    assert "busy" in rep["stages"]["V3"]["checks"]["mutation_score_pct"]["why"]


def test_a_failed_coverage_run_skips_the_mutation_run(session, monkeypatch):
    calls, st = _v3(session, monkeypatch, sim={"ok": False, "output": "x", "first_failure": {"test": "t", "message": ["boom"]}})
    assert [c[0] for c in calls.calls] == ["simulate"] and not st["mutation"]["ok"] and "coverage run" in st["mutation"]["why"]
    assert st["coverage"]["first_failure"]["test"] == "t"


def test_a_held_lock_makes_the_coverage_run_busy_and_stops_there(session, monkeypatch):
    (session.design.parent / "lock").write_text("someone big-job 10:00 11:00\n")
    monkeypatch.setitem(R.V3_MUTATION_ARGS, "lock_wait_s", 0)
    calls, st = _v3(session, monkeypatch)
    assert calls.calls == [] and st["coverage"]["busy"] and "busy" in st["coverage"]["why"]
    assert (session.design.parent / "lock").read_text().startswith("someone")          # never released by us


def test_the_coverage_run_releases_its_own_lock(session, monkeypatch):
    calls, _ = _v3(session, monkeypatch)
    assert not (session.design.parent / "lock").exists()


def test_no_verilator_says_so_and_runs_nothing(session, monkeypatch):
    calls, st = _v3(session, monkeypatch, sims=("icarus",))
    assert calls.calls == [] and "Verilator" in st["coverage"]["why"] and not tool_mentions(st["coverage"]["why"])


def test_the_same_sources_are_not_run_twice(session, monkeypatch):
    import json
    calls, st = _v3(session, monkeypatch)
    out = session.design / "build" / "verif"
    (out / "mutation.json").write_text(json.dumps({"score_pct": 100.0, "evaluated": 3}))
    (out / "sim" / "seed1").mkdir(parents=True, exist_ok=True)
    (out / "sim" / "seed1" / "coverage.dat").write_text("")
    n = len(calls.calls)
    again = R.v3_evidence(_rt(session), True)
    assert again.get("reused") and len(calls.calls) == n
    (session.design / "tests" / "extra.py").write_text("# new test\n")
    R.v3_evidence(_rt(session), True)
    assert len(calls.calls) == n + 2


def _gate_text(session, tmp_path):
    """V0-V3 gates on the real T1 plan, three seeds of recorded results, and this session's evidence status file."""
    import shutil
    runs = tmp_path / "sim"
    for n in (1, 2, 3):
        (runs / f"seed{n}").mkdir(parents=True)
        shutil.copy(ROOT / "flow" / "tests" / "data" / "opus_run_results.xml", runs / f"seed{n}" / "results.xml")
    return G.evaluate(ROOT / "designs" / "t1_dimmer_counter", runs, [], tmp_path / "nof", None, None, None,
                      session.design / "build" / "verif" / "v3_evidence.json")


# --- the gate texts say what the evidence showed and what the tests role can do ----------------------------------------

def test_mutation_text_names_survivors_by_file_line_and_change_and_the_fix():
    t = G.mutation_why({"score_pct": 50.0, "evaluated": 2, "survived": 1,
                        "survivor_text": ["rtl/x.sv line 3: `a == b` became `a != b`"]})
    assert "rtl/x.sv line 3" in t and "became" in t and "Tighten the checks" in t
    assert "mutate" not in t and "call " not in t


def test_unmeasured_texts_carry_the_flows_reason_not_a_tool_call():
    assert G.mutation_why(None, "the mutation run did not start: busy").startswith("not measured: the mutation run did not start")
    plain = G.mutation_why(None)
    assert "the flow runs the mutation step itself" in plain and not tool_mentions(plain)
    assert not tool_mentions(G.HOW_CODE_COV) and not tool_mentions(G.HOW_FUNC_COV)
