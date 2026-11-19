"""Brief 104: strategy options. The analysis, the request classifier, the options schema and its computed fields, the generator's repair loop, the
CLI (choose, more, edit), the run record, and the recorded back-test. No model is called: the generator is driven with fake replies. The prompts are
read from the private repository (``FDA_PROMPTS_DIR``); a test that needs them skips on a fork pull request, like the brief 99 tests."""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.core import managed
from agent.core import prompts as P
from flow.options import analysis as A
from flow.options import backtest as B
from flow.options import cli as C
from flow.options import generate as G
from flow.options import schema as S

ROOT = Path(__file__).resolve().parents[2]
BT = ROOT / "results" / "104_strategy_options" / "backtest"
FX10 = BT / "b96_10g_pre97"
FXC = BT / "c16_montgomery_200mhz"


def _prompts_available() -> bool:
    try:
        P.load(G.PROMPTS["system"])
        return True
    except P.PromptUnavailable:
        return False


needs_prompts = pytest.mark.skipif(not _prompts_available() or os.environ.get("FDA_PROMPTS_SKIP_NOTICE") == "1",
                                   reason="private prompts are not available here (fork pull request or no checkout)")


@pytest.fixture(scope="module")
def an10() -> dict:
    return A.analyse(FX10, build_dir=FX10 / "evidence")


@pytest.fixture(scope="module")
def anc() -> dict:
    return A.analyse(FXC, build_dir=FXC / "evidence")


@pytest.fixture()
def proj10() -> managed.Project:
    return managed.load(FX10)


def opt(**kw) -> dict:
    """A valid latency option on the 10G fixture; keyword arguments replace top-level keys."""
    o = {"id": "O1", "title": "Take the output register out of the go-pulse crossing", "scope": {"kind": "modules", "components": ["core"]},
         "approach": "Set REG_OUTPUT to 0 on u_p_go in b96_core.", "techniques": ["shorten_cdc"], "touches_stages": ["cross_go"],
         "gain": {"metric": "latency_clocks", "low": 1, "high": 1, "basis": "model", "cites": ["stage.cross_go.clocks", "stage.cross_go.removable"],
                  "basis_note": "the stage adds 4 clocks and the stage file says one is removable"},
         "cost": {"iterations": {"low": 1, "high": 2}, "note": "one edit, one build"},
         "risk": {"gates": ["whole-core bench passes", "report_cdc has no unsafe row"], "contract_change": False, "contract_note": "", "needs_eqy": False,
                  "needs_board": True, "summary": "fewer clocks in a crossing lowers its metastability margin"}, "interface_changes": []}
    o.update(kw)
    return o


def wide(**kw) -> dict:
    d = dict(id="O2", title="Rework the whole receive and transmit chain", scope={"kind": "whole_design", "components": [c.name for c in managed.load(FX10).owned()]},
             touches_stages=["rx_descramble", "rx_mac"], gain={"metric": "latency_clocks", "low": 0, "high": 2, "basis": "guess", "cites": [], "basis_note": "no basis: a guess"})
    d.update(kw)
    return opt(**d)


def check(doc, an, proj, **kw):
    return S.check_options(doc, an, proj, goal=kw.pop("goal", "latency"), **kw)


def doc_of(*options) -> dict:
    return {"status": "options", "options": list(options)}


# ---- the analysis ----------------------------------------------------------------------------------------------------------

def test_parsers_on_recorded_reports() -> None:
    ev = FX10 / "evidence"
    rows = A.parse_util_hier((ev / "utilization_hier.rpt").read_text())
    by = {r["path"]: r for r in rows}
    assert by[""]["lut"] == 5954 and by["u_core/u_rx/u_mr"]["module"] == "mac64_rx" and by["u_core/u_rx/u_mr"]["lut"] == 1352
    assert A.parse_timing_summary((ev / "timing_summary.rpt").read_text())["wns_ns"] == 0.115
    w = A.parse_worst_path((ev / "timing_worst_setup.rpt").read_text())
    assert w["logic_levels"] == 19 and w["levels_by_type"]["CARRY8"] == 7 and w["clock"] == "txusr2"
    assert any(r["source_clock"] == "rxusr2" and r["dest_clock"] == "txusr2" and r["endpoints"] == 151 for r in A.parse_cdc_summary((ev / "cdc_summary.rpt").read_text()))
    assert A.parse_clocks((ev / "timing_summary.rpt").read_text())[0]["period_ns"] == 40.0


def test_analysis_maps_stages_to_components_and_every_fact_has_a_file(an10: dict) -> None:
    st = {s["id"]: s for s in an10["latency"]["stages"]}
    assert st["cross_go"]["component"] == "core" and st["decide"]["component"] == "trade_decision" and st["fs_start"]["component"] == "tx_frame_src"
    assert st["tx_spill"]["component"] is None
    assert an10["latency"]["total_clocks"] == 11 and an10["latency"]["reconciled"]
    assert an10["gaps"] == []
    for f in an10["facts"].values():
        assert (ROOT / f["file"]).is_file() and f["origin"] in ("simulation", "post_route_report", "stage_file", "board", "prior_run")
    assert {s["file"] for s in an10["sources"]} >= {f["file"] for f in an10["facts"].values()}
    assert an10["facts"]["res.rx_mac.lut"]["value"] == 1352 and an10["facts"]["build.wall_s"]["value"] == 1176.6


def test_analysis_is_read_only_and_repeatable(an10: dict, tmp_path: Path) -> None:
    before = {p: p.stat().st_mtime_ns for p in FX10.rglob("*") if p.is_file()}
    again = A.analyse(FX10, build_dir=FX10 / "evidence")
    assert again["hash"] == an10["hash"]
    assert before == {p: p.stat().st_mtime_ns for p in FX10.rglob("*") if p.is_file()}


def test_a_missing_report_is_a_gap_not_a_build(tmp_path: Path) -> None:
    d = tmp_path / "d"
    shutil.copytree(FX10, d)
    shutil.rmtree(d / "evidence")
    a = A.analyse(d, build_dir=None)
    assert any("no build reports" in g for g in a["gaps"]) and a["timing"] is None and a["resources"] is None


def test_closure_analysis_has_totals_only_and_says_so(anc: dict) -> None:
    assert anc["timing"]["wns_ns"] == -0.615 and anc["timing"]["worst_path"]["source_component"] == "montgomery_core"
    assert anc["timing"]["worst_path_features"]["carry_chain"] == 18
    assert any("no per-module utilisation" in g for g in anc["gaps"]) and any("latency_stages" in g for g in anc["gaps"])


def test_excluded_components_are_not_in_the_analysis_or_the_model_view() -> None:
    d = ROOT / "designs" / "b102_managed_fcs"
    a = A.analyse(d, build_dir=ROOT / "results" / "102_managed" / "build_base")
    names = {c["name"] for c in a["components"]}
    assert "heartbeat" not in names and a["hidden_components"] == 1 and {"top", "ctrl", "crc"} <= names
    text = json.dumps(G.view(a), default=str).lower()
    assert "heartbeat" not in text and "excluded_components_hidden" not in text
    assert next(c for c in a["components"] if c["name"] == "crc")["ownership"] == "frozen"


def test_blind_view_withholds_the_hints(an10: dict) -> None:
    full, blind = json.dumps(G.view(an10)), json.dumps(G.view(an10, blind=True))
    assert "shorten_cdc" in full and "removable_clocks" in full
    assert "shorten_cdc" not in blind and "removable" not in blind and "technique" not in blind
    for f in G.view(an10)["facts"]:
        assert set(f) == {"id", "value", "unit", "text", "origin"}      # no file names or hashes to the model


# ---- the request ------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,reason", [("", "ambiguous"), ("make it faster", "ambiguous"), ("make it better", "ambiguous"), ("more throughput please", "unsupported"),
                                         ("lower latency and a smaller design", "ambiguous"), ("make it purple", "unsupported"), ("reduce power", "unsupported")])
def test_an_ambiguous_or_unsupported_request_is_a_question(text: str, reason: str, an10: dict, proj10: managed.Project) -> None:
    r = S.classify_request(text, proj10, an10)
    assert r["status"] == "question" and r["reason"] == reason and r["question"].endswith("?") or r["question"].endswith(".")


def test_clear_requests_get_a_goal_and_naming_components_pins_the_scope(an10: dict, proj10: managed.Project) -> None:
    assert S.classify_request("lower latency", proj10, an10)["goal"] == "latency"
    assert S.classify_request("reduce the latency of trade64", proj10, an10)["pinned"] == ["trade_decision"]
    assert S.classify_request("shrink the area", proj10, an10)["goal"] == "area"
    # a frozen component named: a question, not a scope
    q = S.classify_request("lower latency through the gth", proj10, an10)
    assert q["status"] == "question" and "frozen" in q["question"]


def test_a_goal_the_analysis_cannot_serve_is_a_question(anc: dict) -> None:
    pc = managed.load(FXC)
    q = S.classify_request("lower latency", pc, anc)
    assert q["status"] == "question" and q["reason"] == "no_data" and "latency_stages" in q["question"]
    assert S.classify_request("close timing", pc, anc)["status"] == "ok"


def test_an_ambiguous_request_makes_no_model_call(an10: dict, proj10: managed.Project) -> None:
    def boom(system: str, user: str) -> str:
        raise AssertionError("the model must not be called")
    rec = G.improve(an10, "make it faster", proj10, boom)
    assert rec["status"] == "question" and rec["options"] == [] and rec["attempts"] == 0
    rec = G.improve(an10, "make it faster", proj10, None)
    assert rec["status"] == "question"


# ---- the checks -------------------------------------------------------------------------------------------------------------

def test_a_valid_set_passes_and_the_computed_fields_are_filled(an10: dict, proj10: managed.Project) -> None:
    r = check(doc_of(opt(), wide()), an10, proj10)
    assert r["status"] == "options" and [o["id"] for o in r["options"]] == ["O1", "O2"] and not r["rejected"]
    o = r["options"][0]
    assert o["scope"]["cli"] == "--scope core" and o["gain"]["ceiling"] == 1 and o["gain"]["sources"]
    assert o["cost"]["vivado_runs"] == {"low": 1, "high": 2} and o["cost"]["wall_minutes"]["cite"] == "build.wall_s"
    assert o["cost"]["wall_minutes"]["low"] == round(1176.6 / 60, 1)
    assert {n["component"] for n in o["not_touched"]} >= {"gt_wizard", "jtag_bus", "rx_mac"}
    assert next(n for n in o["not_touched"] if n["component"] == "gt_wizard")["why"].startswith("frozen")
    assert o["risk"]["needs_board"]                      # a clock-domain crossing stage: the checker requires board evidence


def test_the_schema_rejects_unknown_keys_and_wrong_types(an10: dict, proj10: managed.Project) -> None:
    for bad in (opt(extra=1), opt(title=""), opt(approach=5), opt(techniques="x"), opt(scope={"kind": "sideways", "components": ["core"]}),
                opt(cost={"iterations": {"low": 3, "high": 1}}), opt(risk={"gates": [], "contract_change": False, "needs_eqy": False, "needs_board": False, "summary": "x"})):
        r = check(doc_of(bad, wide()), an10, proj10)
        assert [x["id"] for x in r["rejected"]] == ["O1"], bad
    assert check([], an10, proj10)["status"] == "invalid" and check({"status": "maybe"}, an10, proj10)["status"] == "invalid"
    q = check({"status": "question", "question": "Which clock?"}, an10, proj10)
    assert q["status"] == "question" and q["question"] == "Which clock?"


def test_every_number_cites_a_source(an10: dict, proj10: managed.Project) -> None:
    def gain(**kw):
        g = copy.deepcopy(opt()["gain"])
        g.update(kw)
        return g
    # no cites on a model gain; an id that is not a fact; a measurement with no prior run behind it; no basis note
    for g in (gain(cites=[]), gain(cites=["stage.nope.clocks"]), gain(basis="measurement"), gain(basis_note=""), gain(basis="astrology"),
              gain(cites=["res.core.lut"]) if False else gain(cites=["build.wall_s"])):
        r = check(doc_of(opt(gain=g), wide()), an10, proj10)
        assert [x["id"] for x in r["rejected"]] == ["O1"], g
    # a guess may have no cites, and is labelled as one in the result
    ok = check(doc_of(opt(gain=gain(basis="guess", cites=[])), wide()), an10, proj10)
    assert ok["options"][0]["gain"]["basis"] == "guess" and "GUESS" in C.render({"status": "options", "request": "x", "goal": "latency", "analysis_hash": "0" * 12, "analysis_sources": [], "model": {},
                                                                                  "options": ok["options"], "rejected": [], "notes": []})
    # a recorded earlier change as a basis is accepted
    an = copy.deepcopy(an10)
    an["facts"]["prior.x"] = {"id": "prior.x", "value": 1, "unit": "clocks", "text": "an earlier cut", "file": an["facts"]["stage.cross_go.clocks"]["file"], "locator": "x", "origin": "prior_run"}
    assert not check(doc_of(opt(gain=gain(basis="measurement", cites=["prior.x"])), wide()), an, proj10)["rejected"]


def test_a_gain_cannot_exceed_what_the_analysis_allows(an10: dict, proj10: managed.Project) -> None:
    # cross_go carries 4 clocks but the stage file says 1 is removable: 3 is more than the analysis allows; blind, the touched stage's own 4 clocks is the bound
    g = copy.deepcopy(opt()["gain"])
    g["high"] = 3
    r = check(doc_of(opt(gain=g), wide()), an10, proj10)
    assert r["rejected"] and "exceeds what the analysis allows" in r["rejected"][0]["problems"][0]
    assert not check(doc_of(opt(gain=g), wide()), an10, proj10, blind=True)["rejected"]
    g["high"] = 5
    assert check(doc_of(opt(gain=g), wide()), an10, proj10, blind=True)["rejected"]
    # a timing gain cannot exceed a clock period; an area gain cannot exceed the LUTs in scope
    t = opt(scope={"kind": "modules", "components": ["rx_mac"]}, touches_stages=["rx_mac"],
            gain={"metric": "lut", "low": 1, "high": 5000, "basis": "model", "cites": ["res.rx_mac.lut"], "basis_note": "x"})
    r = S.check_options(doc_of(t, wide()), an10, managed.load(FX10), goal="area")
    assert r["rejected"] and "LUTs in the scoped components" in r["rejected"][0]["problems"][0]


def test_scopes_respect_ownership(an10: dict, proj10: managed.Project) -> None:
    for sc, why in (({"kind": "modules", "components": ["gt_wizard"]}, "frozen"), ({"kind": "modules", "components": ["jtag_bus"]}, "frozen"),
                    ({"kind": "modules", "components": ["heartbeat"]}, "not a component"), ({"kind": "whole_design", "components": ["core"]}, "whole_design"),
                    ({"kind": "modules", "components": ["core", "core"]}, "twice")):
        r = check(doc_of(opt(scope=sc), wide()), an10, proj10)
        assert r["rejected"] and why in " ".join(r["rejected"][0]["problems"]), sc
    # a stage that lives outside the scope would be edited outside it
    r = check(doc_of(opt(touches_stages=["cross_go", "decide"]), wide()), an10, proj10)
    assert r["rejected"] and "outside the option's scope" in " ".join(r["rejected"][0]["problems"])
    # a stage in a frozen component cannot be touched at all
    an = copy.deepcopy(an10)
    next(s for s in an["latency"]["stages"] if s["id"] == "tx_encode")["component"] = "gt_wizard"
    r = check(doc_of(opt(touches_stages=["tx_encode"], scope={"kind": "modules", "components": ["tx_pcs"]}), wide()), an, proj10)
    assert r["rejected"] and "frozen" in " ".join(r["rejected"][0]["problems"])
    # the request named a component: the scope stays inside it
    r = check(doc_of(opt(), wide()), an10, proj10, pinned=["trade_decision"])
    assert len(r["rejected"]) == 2 and "must stay inside" in r["rejected"][0]["problems"][-1]


def test_a_boundary_change_is_flagged_by_code_and_needs_the_owners_approval(an10: dict, proj10: managed.Project) -> None:
    both = opt(id="O3", title="Fire combinationally and drop the crossing register", scope={"kind": "subsystem", "components": ["core", "trade_decision"]},
               touches_stages=["cross_go", "decide"],
               gain={"metric": "latency_clocks", "low": 1, "high": 2, "basis": "model", "cites": ["stage.cross_go.removable", "stage.decide.removable"], "basis_note": "1 + 1"})
    r = check(doc_of(both, wide()), an10, proj10)
    o = r["options"][0]
    assert o["risk"]["contract_change"] and o["risk"]["contract_flag_added_by_checker"] and o["risk"]["needs_owner_approval"]
    assert "boundary between core and trade_decision" in o["risk"]["contract_flags"][0]
    rendered = C.render({"status": "options", "request": "x", "goal": "latency", "analysis_hash": "0" * 12, "analysis_sources": [], "model": {}, "options": r["options"], "rejected": [], "notes": []})
    assert "CONTRACT CHANGE" in rendered and "owner's approval" in rendered
    # the model saying "no change" does not clear it; saying "yes" without a computed cause keeps it
    assert not check(doc_of(opt(), wide()), an10, proj10)["options"][0]["risk"]["contract_change"]
    said = opt(risk={**opt()["risk"], "contract_change": True})
    assert check(doc_of(said, wide()), an10, proj10)["options"][0]["risk"]["contract_change"]
    # a port change the option declares is flagged too
    ic = opt(interface_changes=[{"component": "core", "port": "go", "change": "output now combinational"}])
    assert check(doc_of(ic, wide()), an10, proj10)["options"][0]["risk"]["contract_flags"]
    # approved in the manifest: no approval needed (still flagged)
    approved = managed.load(FX10)
    approved.approved_contract_changes = ["core", "trade_decision"]
    o2 = check(doc_of(both, wide()), an10, approved)["options"][0]
    assert o2["risk"]["contract_change"] and not o2["risk"]["needs_owner_approval"]


def test_a_set_needs_a_narrow_and_a_broad_option_when_both_are_possible(an10: dict, proj10: managed.Project) -> None:
    r = check(doc_of(opt(), opt(id="O2", title="Another narrow one", touches_stages=["cross_go"])), an10, proj10)
    assert any("narrow option" in x for x in r["repairable"]) or any("narrow" in n for n in r["notes"])
    assert r["status"] == "options"
    one = check(doc_of(opt()), an10, proj10)
    assert any("only 1 valid" in x for x in one["repairable"])
    assert len(check(doc_of(*[opt(id=f"O{i}") for i in range(1, 7)]), an10, proj10)["options"]) == S.MAX_OPTIONS


# ---- the generator ----------------------------------------------------------------------------------------------------------

@needs_prompts
def test_the_generator_repairs_once_and_the_record_holds_hashes_not_prompt_text(an10: dict, proj10: managed.Project) -> None:
    seen: list[tuple[str, str]] = []
    bad = opt(gain={"metric": "latency_clocks", "low": 1, "high": 1, "basis": "model", "cites": [], "basis_note": "x"})
    replies = [json.dumps(doc_of(bad, wide())), "```json\n" + json.dumps(doc_of(opt(), wide())) + "\n```"]

    def llm(system: str, user: str) -> str:
        seen.append((system, user))
        return replies[len(seen) - 1]
    rec = G.improve(an10, "lower latency", proj10, llm, model_info={"model": "fake"})
    assert rec["status"] == "options" and rec["attempts"] == 2 and len(rec["options"]) == 2 and not rec["unresolved"]
    assert "cites the facts it rests on" in seen[1][1]                       # the repair call is told what failed
    text = json.dumps(rec, default=str)
    for name in G.PROMPTS.values():
        assert rec["prompts"][[k for k, v in G.PROMPTS.items() if v == name][0]]["sha256"] == G._sha(P.load(name))
        assert P.load(name)[:80] not in text                                    # the record carries hashes only
    assert rec["analysis_hash"] == an10["hash"] and rec["analysis_sources"] and rec["options_hash"]


@needs_prompts
def test_a_reply_that_never_passes_is_failed_with_the_reasons(an10: dict, proj10: managed.Project) -> None:
    rec = G.improve(an10, "lower latency", proj10, lambda s, u: "I think you should add pipeline stages.")
    assert rec["status"] == "failed" and rec["options"] == [] and rec["attempts"] == 2 and rec["unresolved"]
    assert "nothing is offered" in C.render(rec)


@needs_prompts
def test_the_model_may_ask_a_question(an10: dict, proj10: managed.Project) -> None:
    rec = G.improve(an10, "lower latency", proj10, lambda s, u: json.dumps({"status": "question", "question": "Which direction: transmit or receive?"}))
    assert rec["status"] == "question" and rec["question"].startswith("Which direction") and rec["attempts"] == 1


@needs_prompts
def test_edit_mode_rewrites_one_option(an10: dict, proj10: managed.Project) -> None:
    prev = check(doc_of(opt(), wide()), an10, proj10)["options"]
    sent = []
    one = opt(id="O1", title="Narrower: the output register only")

    def llm(s: str, u: str) -> str:
        sent.append(u)
        return json.dumps(doc_of(one))
    rec = G.improve(an10, "lower latency", proj10, llm, mode="edit", previous=prev, edit={"id": "O1", "instruction": "keep the synchroniser flops"})
    assert rec["status"] == "options" and len(rec["options"]) == 1 and rec["options"][0]["id"] == "O1"
    assert "keep the synchroniser flops" in sent[0] and '"min_options": 1' in sent[0]


# ---- the command ------------------------------------------------------------------------------------------------------------

class FakeResolver:
    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.table = SimpleNamespace(hash="t" * 16)
        self.calls = 0

    def entry(self, purpose: str):
        return SimpleNamespace(endpoint="claude_code", kind="claude_code", model="claude-sonnet-5-5", options={"effort": "medium"}, hash="e" * 16)

    def text(self, purpose: str):
        def llm(system: str, user: str) -> str:
            self.calls += 1
            return self.replies.pop(0)
        return llm


def ns(design: Path, request: str | None = None, **kw) -> SimpleNamespace:
    d = dict(design=design, request=request, analyse_only=False, more=False, edit=None, choose=None, dry_run=False, build_dir=design / "evidence", blind=False, latency_path=None,
             out=None, json=False, models_file=None, model_config=None, replay=None, record=None, board=None, verif_level=None, stop_after=None, max_usd=None)
    d.update(kw)
    return SimpleNamespace(**d)


@pytest.fixture()
def design10(tmp_path: Path) -> Path:
    d = tmp_path / "b96_10g_pre97"
    shutil.copytree(FX10, d)
    return d


@needs_prompts
def test_cli_prints_options_saves_them_and_choose_runs_the_scoped_resume(design10: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    res = FakeResolver([json.dumps(doc_of(opt(), wide()))])
    monkeypatch.setattr(C, "_resolver", lambda a, d, o: res)
    assert C.improve_cmd(ns(design10, "lower latency"), main_fn=None) == 0
    out = capsys.readouterr().out
    assert "Option 1 (O1)" in out and "--scope core" in out and "expected gain: 1 clock" in out and "not touched:" in out and "gt_wizard (frozen" in out
    st = json.loads(C.state_path(design10).read_text())
    assert st["current"]["status"] == "options" and st["choice"] is None
    # nothing in the design changed
    assert {p.relative_to(design10) for p in design10.rglob("*") if p.is_file() and "build" not in p.relative_to(design10).parts} == \
           {p.relative_to(FX10) for p in FX10.rglob("*") if p.is_file()}
    # choose: the ordinary resume, with the option's scope and the strategy file, nothing else
    calls = []
    assert C.improve_cmd(ns(design10, choose=1, dry_run=True), main_fn=lambda argv: calls.append(argv) or 0) == 0
    argv = calls[0]
    assert argv[0] == "resume" and argv[1] == str(design10) and argv[argv.index("--scope") + 1] == "core" and "--dry-run" in argv and "--strategy-file" in argv
    assert "lower latency" in argv[2] and "REG_OUTPUT" in argv[2]
    assert json.loads(C.state_path(design10).read_text())["choice"]["chosen"] == "O1"
    # the run record keeps the analysis, the options offered and the choice
    s = C.strategy_for_run(design10)
    assert s["chosen"] == "O1" and len(s["options_offered"]) == 2 and s["analysis_hash"] and s["analysis_sources"] and s["chosen_option"]["scope"]["components"] == ["core"]


@needs_prompts
def test_a_chosen_option_cannot_edit_outside_its_scope(design10: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The scope --choose passes is the option's own, and the 102 policy built from it refuses an edit to any other component (the frozen ones too)."""
    res = FakeResolver([json.dumps(doc_of(opt(), wide()))])
    monkeypatch.setattr(C, "_resolver", lambda a, d, o: res)
    C.improve_cmd(ns(design10, "lower latency"), main_fn=None)
    calls = []
    C.improve_cmd(ns(design10, choose=1, dry_run=True), main_fn=lambda argv: calls.append(argv) or 0)
    scope_arg = calls[0][calls[0].index("--scope") + 1].split(",")
    project = managed.load(design10)
    r = managed.resolve_request(project, "x", scope_arg)
    assert r.scope is not None and list(r.scope.components) == ["core"]
    pol = managed.ManagedPolicy(project, r.scope)
    pol.check("rtl/b96_core.sv", True)                                       # in scope: allowed
    for rel in ("rtl/trade64.sv", "rtl/tx_path.sv", "ext/jtag_bus.sv", "ip/amd_ip.tcl", "project.yaml"):
        with pytest.raises(Exception):
            pol.check(rel, True)


@needs_prompts
def test_choose_refuses_a_contract_change_until_the_owner_approves_and_a_stale_analysis(design10: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    both = opt(id="O3", scope={"kind": "subsystem", "components": ["core", "trade_decision"]}, touches_stages=["cross_go", "decide"],
               gain={"metric": "latency_clocks", "low": 1, "high": 2, "basis": "model", "cites": ["stage.cross_go.removable", "stage.decide.removable"], "basis_note": "1 + 1"})
    monkeypatch.setattr(C, "_resolver", lambda a, d, o: FakeResolver([json.dumps(doc_of(both, wide()))]))
    C.improve_cmd(ns(design10, "lower latency"), main_fn=None)
    capsys.readouterr()
    ran = []
    assert C.improve_cmd(ns(design10, choose=1), main_fn=lambda a: ran.append(a) or 0) == 3 and not ran
    assert "approved_contract_changes" in capsys.readouterr().err
    # the owner lists them in project.yaml: allowed
    pf = design10 / "project.yaml"
    pf.write_text(pf.read_text().replace("unclaimed: owned", "unclaimed: owned\napproved_contract_changes: [core, trade_decision]"))
    assert C.improve_cmd(ns(design10, choose=1, dry_run=True), main_fn=lambda a: ran.append(a) or 0) == 0 and ran
    # the design changed since the options were made
    (design10 / "evidence" / "core_sim.json").write_text((design10 / "evidence" / "core_sim.json").read_text().replace('"max": 12', '"max": 13'))
    assert C.improve_cmd(ns(design10, choose=1), main_fn=lambda a: 0) == 2
    assert "changed since" in capsys.readouterr().err
    assert C.improve_cmd(ns(design10, choose=9), main_fn=lambda a: 0) == 2


@needs_prompts
def test_more_and_edit_keep_the_state(design10: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    other = opt(id="O1", title="Drop the decision register", scope={"kind": "modules", "components": ["trade_decision"]}, touches_stages=["decide"],
                gain={"metric": "latency_clocks", "low": 0, "high": 1, "basis": "model", "cites": ["stage.decide.clocks"], "basis_note": "one register"})
    res = FakeResolver([json.dumps(doc_of(opt(), wide())), json.dumps(doc_of(other, wide(id="O2"))), json.dumps(doc_of(opt(id="O1", title="Edited")))])
    monkeypatch.setattr(C, "_resolver", lambda a, d, o: res)
    C.improve_cmd(ns(design10, "lower latency"), main_fn=None)
    assert C.improve_cmd(ns(design10, more=True), main_fn=None) == 0
    st = json.loads(C.state_path(design10).read_text())
    assert len(st["current"]["options"]) == 4 and [o["n"] for o in st["current"]["options"]] == [1, 2, 3, 4] and len({o["id"] for o in st["current"]["options"]}) == 4
    assert C.improve_cmd(ns(design10, "keep the flops", edit=1), main_fn=None) == 0
    st = json.loads(C.state_path(design10).read_text())
    assert any(o["title"] == "Edited" for o in st["current"]["options"]) and len(st["current"]["options"]) == 4 and len(st["history"]) == 2


def test_an_unclear_request_prints_a_question_and_saves_no_options(design10: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setattr(C, "_resolver", lambda a, d, o: FakeResolver([]))
    assert C.improve_cmd(ns(design10, "make it faster"), main_fn=None) == 0
    out = capsys.readouterr().out
    assert "A question first" in out and "no model was called" in out and "Option 1" not in out
    assert json.loads(C.state_path(design10).read_text())["current"]["status"] == "question"
    assert C.improve_cmd(ns(design10, choose=1), main_fn=lambda a: 0) == 2


def test_analyse_only_makes_no_model_call(design10: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setattr(C, "_resolver", lambda a, d, o: (_ for _ in ()).throw(AssertionError("no resolver")))
    assert C.improve_cmd(ns(design10, analyse_only=True), main_fn=None) == 0
    assert "tick-to-trade" in capsys.readouterr().out
    assert not C.state_path(design10).exists()


def test_the_run_summary_carries_the_strategy(design10: Path) -> None:
    from agent.__main__ import with_scope
    st = {"current": {"request": "lower latency", "goal": "latency", "analysis_hash": "a", "options_hash": "b", "options": [{"id": "O1", "title": "t", "scope": {"components": ["core"]}}],
                      "model": {"model": "m"}, "prompts": {}, "analysis_sources": []},
          "choice": {"chosen": "O1", "scope": ["core"], "time": "now"}}
    f = C.state_path(design10)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(st))
    s = with_scope({"x": 1}, design10)
    assert s["strategy"]["chosen"] == "O1" and s["strategy"]["options_offered"][0]["scope"] == ["core"]
    assert "strategy" not in with_scope({"x": 1}, design10 / "evidence")


# ---- the options purpose and the back-test -----------------------------------------------------------------------------------

def test_options_is_a_model_table_purpose_on_the_subscription() -> None:
    from agent.models.config import PURPOSES, build_table
    t = build_table()
    e = t.entry("options")
    assert "options" in PURPOSES and (e.kind, e.model) == ("claude_code", "claude-sonnet-5-5")
    from agent.models import inventory
    assert any("options" in s["purposes"] and s["file"] == "flow/options/generate.py" for s in inventory.SITES) and "options" not in inventory.RESERVED


def test_the_generator_never_builds_a_client() -> None:
    for f in (ROOT / "flow" / "options").glob("*.py"):
        t = f.read_text()
        assert "OpenRouterClient" not in t and "anthropic" not in t.lower().replace("anthropic_api", "") and "subprocess" not in t, f


RUNS = BT / "runs"


@pytest.mark.skipif(not (BT / "results.json").is_file(), reason="the back-test has not been run")
def test_recorded_backtest_rescoring_reproduces_the_committed_scores() -> None:
    """Every recorded run is re-checked with the current checker (so a rule that tightened later shows up) and re-scored by code."""
    res = json.loads((BT / "results.json").read_text())
    assert res["runs"]
    for r in res["runs"]:
        rec = json.loads((RUNS / r["run"] / "strategy.json").read_text())["current"]
        truth = B.load_truth(BT / "truth" / f"{r['case']}.json")
        assert B.score(rec, truth) == r["score"], r["run"]
        fx = FX10 if r["case"] == "b96_10g_pre97" else FXC
        an = A.analyse(fx, build_dir=fx / "evidence")
        assert an["hash"] == rec["analysis_hash"], r["run"]
        again = S.check_options({"status": "options", "options": [_raw(o) for o in rec["options"]]}, an, managed.load(fx), goal=rec["goal"], blind=rec["blind"], min_options=1)
        assert not again["rejected"], (r["run"], again["rejected"])


def _raw(o: dict) -> dict:
    """An offered option back in the shape the model wrote it (the checker's own fields dropped)."""
    g = o["gain"]
    return {"id": o["id"], "title": o["title"], "scope": {"kind": o["scope"]["kind"], "components": o["scope"]["components"]}, "approach": o["approach"], "techniques": o["techniques"],
            "touches_stages": o["touches_stages"], "gain": {k: g[k] for k in ("metric", "low", "high", "basis", "cites", "basis_note")},
            "cost": {"iterations": o["cost"]["iterations"], "note": o["cost"]["note"] or "x"},
            "risk": {"gates": o["risk"]["gates"], "contract_change": o["risk"]["contract_change"], "contract_note": o["risk"]["contract_note"], "needs_eqy": o["risk"]["needs_eqy"],
                     "needs_board": o["risk"]["needs_board"], "summary": o["risk"]["summary"]}, "interface_changes": o["interface_changes"]}


def test_scoring_finds_a_variant_only_by_its_exact_stage_set() -> None:
    truth = B.load_truth(BT / "truth" / "b96_10g_pre97.json")
    mk = lambda stages, lo, hi: {"id": "O" + "".join(stages)[:3], "title": "t", "scope": {"kind": "modules", "components": ["core"]}, "touches_stages": stages,
                                 "gain": {"metric": "latency_clocks", "low": lo, "high": hi, "basis": "model"}}
    rec = {"status": "options", "options": [mk(["cross_go"], 1, 1), mk(["cross_go", "decide"], 1, 3), mk(["rx_mac"], 0, 1)]}
    sc = B.score_latency(rec, truth)
    assert sc["variants"]["agent_cdc"]["in_range"] and sc["variants"]["agent_both"]["found"] and sc["variants"]["agent_both"]["over"] == 1
    assert not sc["variants"]["all3"]["found"] and sc["variants"]["all3"]["best_overlap"] == 0.67
    assert sc["found_named"] == 2 and sc["found_all"] == 2 and [o["stages"] for o in sc["other_options"]] == [["rx_mac"]]
    tc = B.load_truth(BT / "truth" / "c16_montgomery_200mhz.json")
    one = {"id": "O1", "title": "t", "scope": {"kind": "modules", "components": ["montgomery_core"]}, "approach": "carry-save", "techniques": [],
           "gain": {"metric": "wns_ns", "low": 0.3, "high": 1.0, "basis": "guess"}}
    assert B.score_change({"status": "options", "options": [one]}, tc)["changes"]["carry_save"]["in_range"]
