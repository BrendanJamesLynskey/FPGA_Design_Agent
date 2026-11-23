"""Brief 194: the verification profile through the run: scripted interview (no model), config round trip, run summary."""

import shutil
import uuid

import pytest
import yaml

pytest.importorskip("langgraph")
pytest.importorskip("deepagents")
from agent.core.session import ROOT  # noqa: E402
from agent.graph import run as gr  # noqa: E402
from agent.tests.test_episode import FakeRunner, T1  # noqa: E402

SPEC = yaml.safe_load((T1 / "spec.yaml").read_text())


@pytest.fixture
def rt(monkeypatch):
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(gr, "RUNS", runs)
    cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", interview="off", verif_ask=True)
    r = gr.new_runtime(cfg, lambda *a, **k: None, runner=FakeRunner())
    (r.design / "spec.md").write_text("A PWM dimmer counter for the board.\n")
    yield r
    shutil.rmtree(runs, ignore_errors=True)


def test_the_interview_proposes_a_profile_and_applies_it(rt):
    spec = dict(SPEC, open_questions=[], requirements=[{"id": "R1", "text": "Counts presses", "proof": ["simulation"]},
                                                       {"id": "R2", "text": "Survives a single event upset in the counter", "proof": ["simulation"]}])
    spec, summary = gr._interview(rt, spec, {})
    qs = summary["questions"]
    prof = [q for q in qs if q["text"].startswith("Which verification profile")]
    assert len(prof) == 1 and prof[0]["default"] == "high_reliability" and prof[0]["status"] == "defaulted" and prof[0]["reason"]
    assert rt.cfg.verif_profile == "high_reliability" and rt.cfg.verif_ask is False and spec["verif_profile"] == "high_reliability"
    assert any(q["id"].startswith("s") for q in qs)                  # the structure question for the counter
    assert spec["reliability"] and yaml.safe_load((rt.design / "spec.yaml").read_text())["verif_profile"] == "high_reliability"
    rec = gr._profile_record(rt.cfg)
    assert rec["profile"] == "high_reliability" and rec["effective"]["fault_injection"] is True and "advisory" in rec


def test_no_question_without_ask(rt):
    rt.cfg.verif_ask = False
    spec = dict(SPEC, open_questions=[], requirements=[{"id": "R1", "text": "Counts presses", "proof": ["simulation"]}])
    _, summary = gr._interview(rt, spec, {})
    assert summary["asked"] == 0 and rt.cfg.verif_profile == "standard"


def test_config_round_trips_through_config_json():
    from agent.__main__ import config_from_json
    cfg = gr.Config(spec_md=T1 / "spec.md", name="x", verif_profile="ip_release", verif_sets={"seeds": 9})
    c = {k: str(v) for k, v in cfg.__dict__.items()}
    back = config_from_json(c)
    assert back.verif_profile == "ip_release" and back.verif_sets == {"seeds": 9}
    assert config_from_json({k: v for k, v in c.items() if not k.startswith("verif_")}).verif_profile == "standard"   # old runs


def test_the_pin_holds_and_a_role_cannot_move_it(rt):
    from agent.core.security import SecurityError
    from agent.graph import profiles as P, ownership
    from agent.graph.roles import RoleJail
    rt.cfg.verif_ask = False
    gr._pin_run(rt)
    assert (rt.run_dir / "policy.json").is_file() and P.check_pin(rt.run_dir, rt.cfg.verif_profile, rt.cfg.verif_sets, rt.design) == []
    assert any(r["what"] == "verification profile" for r in ownership.load(rt.design))      # who set it, in who_did_what.json
    # the model writes spec.yaml with another profile: a breach is logged, the pin stays
    (rt.design / "spec.yaml").write_text("verif_profile: prototype\n")
    assert "pinned to 'standard'" in P.check_pin(rt.run_dir, "standard", None, rt.design)[0]
    # the live settings drift: a breach
    assert "differ from the pin" in P.check_pin(rt.run_dir, "prototype", None)[0]
    # no role's jail reaches the run directory, where the pin lives
    rel = "../" * 6 + str(rt.run_dir / "policy.json").lstrip("/")
    for role in ("rtl", "tests", "model"):
        with pytest.raises((SecurityError, ValueError, OSError)):
            RoleJail(rt.session.jail, role).resolve(rel, write=True)
    # a second pin call (a resume) keeps the first
    assert P.write_pin(rt.run_dir, "prototype", None)["new"] is False
    assert yaml.safe_load((rt.run_dir / "policy.json").read_text())["profile"] == "standard"


def _proposals(tmp_path, board):
    import shutil
    from pathlib import Path
    from agent.graph import settings as S
    d = tmp_path / f"{board}_pkg"
    d.mkdir()
    shutil.copy(ROOT / "boards" / board / "board.yaml", d / "board.yaml")
    return d, S.write(d, S.propose(d))


def test_settings_are_confirmed_inside_the_interview(rt, tmp_path):
    from agent.graph import settings as S
    d, f = _proposals(tmp_path, "nexys_a7_100t")
    rt.cfg.verif_ask = False
    rt.cfg.settings_file = f
    rt.cfg.board = "nexys_a7_100t"
    spec = dict(SPEC, open_questions=[], requirements=[{"id": "R1", "text": "Counts presses", "proof": ["simulation"]}])
    spec, summary = gr._interview(rt, spec, {})
    keys = {q["text"].rsplit("[", 1)[1][:-1]: q for q in summary["questions"] if q["text"].endswith("]")}
    assert set(keys) == set(S.KEYS) and all(q["reason"] for q in keys.values())
    assert keys["part"]["default"] == '"xc7a100tcsg324-1"' and keys["part"]["status"] == "defaulted"
    assert keys["phys"]["default"] == S.SENTINEL
    assert "phys: nothing was proposed" in "; ".join(summary["unconfirmed"])            # a gap stays open: the run cannot leave the interview
    assert not (rt.design / "confirmed_settings.yaml").exists()


def test_answered_gap_lets_the_run_leave_with_a_confirmed_file(rt, tmp_path, monkeypatch):
    from agent.graph import settings as S
    d, f = _proposals(tmp_path, "nexys_a7_100t")
    doc = yaml.safe_load(f.read_text())
    doc["settings"]["phys"].update(value=["none"], status="proposed")      # as if the human had been asked and the value read back
    f.write_text(yaml.safe_dump(doc))
    rt.cfg.verif_ask, rt.cfg.settings_file, rt.cfg.board = False, f, "nexys_a7_100t"
    spec = dict(SPEC, open_questions=[], requirements=[{"id": "R1", "text": "Counts presses", "proof": ["simulation"]}])
    spec, summary = gr._interview(rt, spec, {})
    assert "unconfirmed" not in summary
    conf = yaml.safe_load((rt.design / "confirmed_settings.yaml").read_text())
    assert conf["settings"]["board"]["status"] == "confirmed" and conf["settings"]["board"]["confirmed_by"].startswith("interview: defaulted")
    assert spec["settings"]["part"] == "xc7a100tcsg324-1" and spec["verif_profile"] == "standard"


def test_a_confirmed_board_that_is_not_the_runs_board_stays_open(rt, tmp_path):
    d, f = _proposals(tmp_path, "kr260")
    doc = yaml.safe_load(f.read_text())
    for k in ("io_standards", "phys", "interfaces", "speed_grade"):
        doc["settings"][k].update(value=["x"] if k != "speed_grade" else "-2L", status="proposed")
    f.write_text(yaml.safe_dump(doc))
    rt.cfg.verif_ask, rt.cfg.settings_file, rt.cfg.board = False, f, "nexys_a7_100t"
    spec, summary = gr._interview(rt, dict(SPEC, open_questions=[], requirements=[{"id": "R1", "text": "t", "proof": ["simulation"]}]), {})
    assert any(u.startswith("board: the confirmed board kr260") for u in summary["unconfirmed"])
