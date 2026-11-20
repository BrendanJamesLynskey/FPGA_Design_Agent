"""Brief 107: record and replay (level 2), the --deterministic option, level 1 (temperature 0), and the questions the review asked:
can a deterministic run silently sample, can a tape leak a key or a prompt into the repository, does the run record tell the truth."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agent.graph.llm import Reply
from agent.models import determinism as D
from agent.models.config import build_table
from agent.models.resolver import Resolver
from agent.models.tape import DeterminismError, Tape

MSG = [{"role": "system", "content": "SECRET-PROMPT-TEXT"}, {"role": "user", "content": "hello"}]


def table(**cli):
    return build_table(user_file=Path("/nonexistent"), cli=cli or None)


def counting_factory(reply_for):
    calls = []

    def factory(e):
        def client(messages, tools=None):
            calls.append((e.purpose, messages[-1]["content"]))
            return reply_for(len(calls), messages)
        return client
    return factory, calls


def test_record_then_replay_is_exact_and_makes_no_live_call(tmp_path):
    t = table()
    fac, calls = counting_factory(lambda n, m: Reply(f"answer {n}", [{"id": "c", "name": "f", "args": {"n": n}}], 10, 5, 0.01, 1.0, "prov"))
    rec = Resolver(t, run_dir=tmp_path / "r1", factory=fac, tape=Tape.open(tmp_path / "tape", "record"))
    c = rec.chat("rtl")
    got = [c(MSG), c(MSG), c(MSG + [{"role": "user", "content": "more"}])]           # the same request twice: two different replies
    assert len(calls) == 3 and got[0].text != got[1].text
    rep = Resolver(t, run_dir=tmp_path / "r2", tape=Tape.open(tmp_path / "tape", "replay"))       # no factory, no client, no key
    c2 = rep.chat("rtl")
    back = [c2(MSG), c2(MSG), c2(MSG + [{"role": "user", "content": "more"}])]
    assert [(r.text, r.tool_calls, r.prompt_tokens) for r in back] == [(r.text, r.tool_calls, r.prompt_tokens) for r in got]
    assert len(calls) == 3                                                           # replay called nothing live
    s = rep.tape.state()
    assert s["served_from_tape"] == 3 and s["unused_recordings"] == 0 and s["live_calls"] == 0 and s["replay_misses"] == 0
    assert all(r.cost == 0.0 for r in back)                                          # replayed calls cost nothing


def test_a_missing_or_changed_request_is_an_error_never_a_live_call(tmp_path):
    t = table()
    fac, calls = counting_factory(lambda n, m: Reply("x", []))
    Resolver(t, factory=fac, tape=Tape.open(tmp_path / "tape", "record")).chat("rtl")(MSG)
    rep = Resolver(t, tape=Tape.open(tmp_path / "tape", "replay"))
    with pytest.raises(DeterminismError, match="replay miss"):
        rep.chat("rtl")([{"role": "user", "content": "a different prompt"}])
    c = rep.chat("rtl")
    c(MSG)
    with pytest.raises(DeterminismError, match="already served"):                    # more calls than recorded
        c(MSG)
    other = Resolver(table(purposes={"rtl": {"options": {"temperature": 0.9}}}), tape=Tape.open(tmp_path / "tape", "replay"))
    with pytest.raises(DeterminismError, match="replay miss"):                       # a different option is a different request
        other.chat("rtl")(MSG)
    assert len(calls) == 1


def test_the_tape_holds_hashes_not_prompts_and_no_key(tmp_path):
    t = table()
    fac, _ = counting_factory(lambda n, m: Reply("a design", []))
    Resolver(t, factory=fac, tape=Tape.open(tmp_path / "tape", "record")).chat("rtl")(MSG)
    text = (tmp_path / "tape" / "tape.jsonl").read_text()
    assert "SECRET-PROMPT-TEXT" not in text and "hello" not in text                  # only the per-message hashes
    row = [json.loads(x) for x in text.splitlines()][1]
    assert len(row["messages_sha256"]) == 2 and row["purpose"] == "rtl" and row["reply"]["text"] == "a design"
    bad, _ = counting_factory(lambda n, m: Reply("here is sk-abcdefghijklmnop1234", []))
    with pytest.raises(DeterminismError, match="looks like a key"):
        Resolver(t, factory=bad, tape=Tape.open(tmp_path / "t2", "record")).chat("rtl")(MSG)


def test_a_tape_inside_the_repository_that_git_would_track_is_refused():
    root = Path(__file__).resolve().parents[2]
    with pytest.raises(DeterminismError, match="not git-ignored"):
        Tape.open(root / "results" / "107_deterministic" / "tape_x", "record")
    Tape.check_location(root / "runs" / "some_run" / "tape")                          # runs/ is git-ignored
    Tape.check_location(Path.home() / ".local" / "share" / "fpga_design_agent" / "tapes" / "x")


def test_run_directory_names_are_neutralised(tmp_path):
    subs = [(str(tmp_path / "runA"), "<<run_dir>>"), ("runA-id", "<<run_id>>")]
    t = table()
    fac, _ = counting_factory(lambda n, m: Reply(f"wrote {tmp_path}/runA/file", [{"id": "1", "name": "w", "args": {"p": "runA-id/x"}}]))
    Resolver(t, factory=fac, tape=Tape.open(tmp_path / "tape", "record", subs)).chat("rtl")([{"role": "user", "content": f"in {tmp_path}/runA/d"}])
    subs2 = [(str(tmp_path / "runB"), "<<run_dir>>"), ("runB-id", "<<run_id>>")]
    r = Resolver(t, tape=Tape.open(tmp_path / "tape", "replay", subs2)).chat("rtl")([{"role": "user", "content": f"in {tmp_path}/runB/d"}])
    assert r.text == f"wrote {tmp_path}/runB/file" and r.tool_calls[0]["args"]["p"] == "runB-id/x"


def test_text_calls_through_the_cli_are_recorded_and_replayed(tmp_path, monkeypatch):
    from agent.models import claude_cli
    n = []
    monkeypatch.setattr(claude_cli, "text_call", lambda *a, **k: n.append(1) or {"result": f"out{len(n)}", "usage": {"output_tokens": 3}, "total_cost_usd": 0.5})
    t = table()
    e = t.entry("spectest")
    assert e.kind == "claude_code"
    r1 = Resolver(t, tape=Tape.open(tmp_path / "tape", "record"))
    a = r1.text_result(e, "sys", "user", timeout_s=9, effort="medium", prefix="p_")
    r2 = Resolver(t, tape=Tape.open(tmp_path / "tape", "replay"))
    b = r2.text_result(e, "sys", "user", timeout_s=900, effort="medium", prefix="p_")      # timeout is not part of the request
    assert a["result"] == b["result"] == "out1" and len(n) == 1


def test_a_claude_code_subagent_turn_cannot_be_replayed_and_is_refused(tmp_path):
    t = table()
    rec = Resolver(t, tape=Tape.open(tmp_path / "tape", "record"))
    rec.unreplayable("the rtl role")
    assert rec.tape.unreplayable == 1                                                  # recording counts it ...
    with pytest.raises(DeterminismError, match="cannot be recorded or replayed"):
        Resolver(t, tape=Tape.open(tmp_path / "tape", "replay")).unreplayable("the rtl role")      # ... replay refuses
    with pytest.raises(DeterminismError, match="no temperature"):
        Resolver(t, level1=True).unreplayable("the rtl role")


# --- level 1 ------------------------------------------------------------------------------------------------------------------

def test_level1_capability_per_kind():
    t = table()
    assert "no temperature" in D.level1_capable(t.entry("spectest"))                  # claude_code
    assert D.level1_capable(t.entry("rtl")) is None                                   # openrouter
    t2 = table(purposes={"rtl": {"endpoint": "anthropic_api", "model": "claude-sonnet-5-5"}})
    assert "rejects a temperature" in D.level1_capable(t2.entry("rtl"))
    t3 = table(purposes={"rtl": {"endpoint": "anthropic_api", "model": "claude-haiku-4-5"}})
    assert D.level1_capable(t3.entry("rtl")) is None
    t4 = table(purposes={"rtl": {"endpoint": "anthropic_api", "model": "claude-haiku-4-5", "options": {"thinking_budget": 2000}}})
    assert "thinking" in D.level1_capable(t4.entry("rtl"))


def test_level1_patch_sets_temperature_zero_and_seed_only_where_supported():
    t = table(purposes={"model": {"endpoint": "anthropic_api", "model": "claude-haiku-4-5"}})
    patched = build_table(user_file=Path("/nonexistent"), cli=[{"purposes": {"model": {"endpoint": "anthropic_api", "model": "claude-haiku-4-5"}}}, D.level1_patch(t)])
    assert patched.entry("rtl").options["temperature"] == 0 and patched.entry("rtl").options["seed"] == D.SEED
    assert patched.entry("model").options["temperature"] == 0 and "seed" not in patched.entry("model").options    # the API has no seed
    assert "temperature" not in patched.entry("spectest").options                      # claude_code: nothing to set
    assert patched.hash != t.hash                                                      # the level is in the table hash


def test_deterministic_fails_loudly_before_any_call_when_a_used_purpose_cannot_take_temperature_zero():
    from agent.graph.run import Config
    cfg = Config(spec_md=Path("x"), name="x", board="b", spec_tests=True)              # spectest is on claude_code by default
    with pytest.raises(DeterminismError, match="spectest.*claude_code"):
        D.check_level1(cfg.model_table(), cfg)
    ok = Config(spec_md=Path("x"), name="x", board="b")
    D.check_level1(ok.model_table(), ok)                                              # the default roles are on OpenRouter: allowed


def test_level1_runtime_guard_refuses_a_call_that_would_sample(tmp_path):
    t = table()                                                                       # temperature 0.2 on rtl
    fac, calls = counting_factory(lambda n, m: Reply("x", []))
    r = Resolver(t, factory=fac, level1=True)
    with pytest.raises(DeterminismError, match="would not run at temperature 0"):
        r.chat("rtl")(MSG)
    assert not calls
    z = build_table(user_file=Path("/nonexistent"), cli=D.level1_patch(t))
    Resolver(z, factory=fac, level1=True).chat("rtl")(MSG)
    assert len(calls) == 1
    e = z.entry("spectest")                                                           # a claude_code text call at level 1
    with pytest.raises(DeterminismError):
        Resolver(z, level1=True).text_result(e, "s", "u", timeout_s=1, effort=None, prefix="p")


def test_the_cli_chooses_the_level_and_never_falls_back(tmp_path, monkeypatch):
    import argparse

    from agent.__main__ import tape_spec_from
    from agent.graph.run import Config
    monkeypatch.setattr(D, "DEFAULT_TAPE_ROOT", tmp_path / "tapes")
    a = argparse.Namespace(deterministic=True, tape=None, record_tape=None, replay_tape=None)
    cfg = Config(spec_md=Path("x"), name="proj", board="b")
    s = tape_spec_from(a, cfg)                                                         # no tape: level 1, recorded
    assert s["level"] == 1 and s["mode"] == "record" and cfg.level1_seed == D.SEED
    (tmp_path / "tapes" / "proj").mkdir(parents=True)
    tp = Tape.open(tmp_path / "tapes" / "proj", "record", table_hash=cfg.model_table().hash, level1_seed=D.SEED)
    tp._store(tp.request(cfg.model_table().entry("rtl"), MSG, None), {"text": "x"})
    cfg2 = Config(spec_md=Path("x"), name="proj", board="b")
    s2 = tape_spec_from(a, cfg2)                                                       # a tape exists: level 2, same table
    assert s2["level"] == 2 and s2["mode"] == "replay" and cfg2.level1_seed == D.SEED and cfg2.model_table().hash == cfg.model_table().hash
    cfg3 = Config(spec_md=Path("x"), name="other", board="b", spec_tests=True)
    with pytest.raises(DeterminismError):
        tape_spec_from(a, cfg3)


def test_the_run_record_tells_the_level_truthfully():
    from agent.graph.run import determinism_level_at_end

    class R:
        pass
    r = R()
    r.tape = None
    assert determinism_level_at_end(r) == 0
    r.tape = Tape.__new__(Tape)
    r.tape.mode, r.tape.live, r.tape.misses, r.tape.unreplayable = "replay", 0, 0, 0
    r.tape._rows, r.tape._seen, r.tape.record_failures = {}, {}, 0
    r.level1 = False
    assert determinism_level_at_end(r) == 2
    r.tape.live = 1
    assert determinism_level_at_end(r) == 0                                            # a replay that went live is not level 2
    r.tape.mode, r.level1 = "record", True
    assert determinism_level_at_end(r) == 1
    r.tape.unreplayable = 1
    assert determinism_level_at_end(r) == 0                                            # an escaped sub-agent turn: not level 1
    r.level1 = False
    assert determinism_level_at_end(r) == 0                                            # recording only: sampled


def test_whole_graph_replay_is_exact():
    """The scripted T1 episode recorded to a tape and replayed with no model client: same tool calls, same files, same stage path."""
    from tools.determinism_replay_check import proof
    out = proof()
    assert out["exact"], out
    assert out["replay"]["tape"]["live_calls"] == 0 and out["replay"]["tape"]["served_from_tape"] == out["record"]["tape"]["calls_recorded"] > 10


# --- review fixes ---------------------------------------------------------------------------------------------------------------

def test_review_fixes(tmp_path):
    root = Path(__file__).resolve().parents[2]
    with pytest.raises(DeterminismError, match="not git-ignored"):               # a new nested path inside the checkout is still refused
        Tape.check_location(root / "agent" / "_zz_new" / "sub" / "tape")
    t = table()
    for secret in ("ghp_" + "a" * 20, "AKIA" + "A" * 16, "api_key=abcdefghij"):
        bad, _ = counting_factory(lambda n, m, s=secret: Reply(f"x {s}", []))
        r = Resolver(t, factory=bad, tape=Tape.open(tmp_path / f"t{len(secret)}", "record"))
        with pytest.raises(DeterminismError):
            r.chat("rtl")(MSG)
        assert r.tape.record_failures == 1
    fac, _ = counting_factory(lambda n, m: Reply("a literal <<repo>> stays", []))
    Resolver(t, factory=fac, tape=Tape.open(tmp_path / "e", "record", [("/home/u/repo", "<<repo>>")])).chat("rtl")(MSG)
    assert Resolver(t, tape=Tape.open(tmp_path / "e", "replay", [("/home/u/repo", "<<repo>>")])).chat("rtl")(MSG).text == "a literal <<repo>> stays"
    with pytest.raises(DeterminismError, match="already holds a recording"):
        Tape.open(tmp_path / "e", "record")
    (tmp_path / "e" / "tape.jsonl").write_text((tmp_path / "e" / "tape.jsonl").read_text() + '{"key": ')
    with pytest.raises(DeterminismError, match="damaged"):
        Tape.open(tmp_path / "e", "replay")


def test_a_partial_replay_is_not_level_2(tmp_path):
    from agent.graph.run import determinism_level_at_end
    t = table()
    fac, _ = counting_factory(lambda n, m: Reply(f"r{n}", []))
    c = Resolver(t, factory=fac, tape=Tape.open(tmp_path / "tp", "record")).chat("rtl")
    c(MSG)
    c([{"role": "user", "content": "two"}])
    r = Resolver(t, tape=Tape.open(tmp_path / "tp", "replay"))
    r.chat("rtl")(MSG)
    assert determinism_level_at_end(r) == 0                                       # one recording unused
    r.chat("rtl")([{"role": "user", "content": "two"}])
    assert determinism_level_at_end(r) == 2
