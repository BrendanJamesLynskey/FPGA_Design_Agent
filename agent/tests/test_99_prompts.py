"""Brief 99: the private prompt loader. Fixtures are made up here (no real prompt text is ever in this repository)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from agent.core import prompts as P

TEXT = "Line one.\n\n  indented line with trailing space \r\nUnicode: µs – end\n"


def _make(root: Path, files: dict[str, str]) -> str:
    ents = {}
    for name, text in files.items():
        f = root / f"{name}.txt"
        f.parent.mkdir(parents=True, exist_ok=True)
        raw = text.encode("utf-8")
        f.write_bytes(raw)
        ents[name] = {"file": f"{name}.txt", "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    mf = json.dumps({"version": 1, "prompts": ents}, indent=1).encode()
    (root / "MANIFEST.json").write_bytes(mf)
    return hashlib.sha256(mf).hexdigest()


def _pin(sha=None):
    return {"version": 1, "kb_commit": "0" * 40 if sha else None, "manifest_sha256": sha, "names": []}


def test_load_returns_the_bytes_exactly(tmp_path):
    sha = _make(tmp_path, {"graph/demo/one": TEXT})
    assert P.load("graph/demo/one", root=tmp_path, pin=_pin(sha)).encode() == TEXT.encode()      # CRLF, trailing spaces kept
    assert P.names(root=tmp_path, pin=_pin(sha)) == ["graph/demo/one"]
    assert P.verify_all(root=tmp_path, pin=_pin(sha)) == 1


def test_unpinned_stage0_still_checks_file_against_manifest(tmp_path):
    _make(tmp_path, {"a": "x"})
    assert P.load("a", root=tmp_path, pin=_pin(None)) == "x"
    (tmp_path / "a.txt").write_text("changed")
    with pytest.raises(P.PromptUnavailable, match="file hash"):
        P.load("a", root=tmp_path, pin=_pin(None))


def test_a_manifest_that_is_not_the_pinned_one_is_refused(tmp_path):
    sha = _make(tmp_path, {"a": "x"})
    _make(tmp_path, {"a": "x", "b": "y"})                       # the checkout moved on
    with pytest.raises(P.PromptUnavailable, match="not the pinned"):
        P.load("a", root=tmp_path, pin=_pin(sha))


def test_unpinned_switch_skips_only_the_pin_comparison(tmp_path, monkeypatch):
    sha = _make(tmp_path, {"a": "x"})
    _make(tmp_path, {"a": "x", "b": "y"})
    monkeypatch.setenv(P.ENV_UNPINNED, "1")
    assert P.load("b", root=tmp_path, pin=_pin(sha)) == "y"
    assert P.provenance(root=tmp_path, pin=_pin(sha))["enforced"] is False
    monkeypatch.delenv(P.ENV_UNPINNED)
    assert P.provenance(root=tmp_path, pin=_pin(sha))["enforced"] is True


def test_missing_things_refuse_and_there_is_no_fallback_text(tmp_path):
    with pytest.raises(P.PromptUnavailable, match="manifest not found"):
        P.load("a", root=tmp_path / "nowhere", pin=_pin())
    sha = _make(tmp_path, {"a": "x"})
    with pytest.raises(P.PromptUnavailable, match="not in the manifest"):
        P.load("b", root=tmp_path, pin=_pin(sha))
    (tmp_path / "a.txt").unlink()
    with pytest.raises(P.PromptUnavailable, match="missing"):
        P.load("a", root=tmp_path, pin=_pin(sha))


@pytest.mark.parametrize("bad", ["", "../x", "/abs", "A", "a//b", "a/b/", "a b", "a.txt", "a\n"])
def test_bad_names_are_refused(tmp_path, bad):
    sha = _make(tmp_path, {"a": "x"})
    with pytest.raises(P.PromptUnavailable, match="bad prompt name"):
        P.load(bad, root=tmp_path, pin=_pin(sha))


def test_a_manifest_file_path_cannot_leave_the_directory(tmp_path):
    root = tmp_path / "prompts"
    root.mkdir()
    (tmp_path / "secret.txt").write_text("x")
    ents = {"a": {"file": "../secret.txt", "sha256": hashlib.sha256(b"x").hexdigest(), "bytes": 1}}
    (root / "MANIFEST.json").write_text(json.dumps({"version": 1, "prompts": ents}))
    with pytest.raises(P.PromptUnavailable, match="leaves"):
        P.load("a", root=root, pin=_pin())


def test_errors_never_carry_prompt_text(tmp_path):
    secret = "SECRET-PROMPT-WORDS-12345"
    sha = _make(tmp_path, {"a": secret})
    (tmp_path / "a.txt").write_text(secret + " tampered")
    with pytest.raises(P.PromptUnavailable) as e:
        P.load("a", root=tmp_path, pin=_pin(sha))
    assert secret not in str(e.value)


def test_directory_comes_from_the_environment(tmp_path, monkeypatch):
    sha = _make(tmp_path, {"a": "x"})
    monkeypatch.setenv(P.ENV_DIR, str(tmp_path))
    assert P.prompts_dir() == tmp_path
    assert P.load("a", pin=_pin(sha)) == "x"
    monkeypatch.delenv(P.ENV_DIR)
    assert P.prompts_dir().name == "prompts" and P.prompts_dir().parent == P.DEFAULT_BANK


def test_the_committed_pin_holds_hashes_only():
    pin = P.read_pin()
    assert set(pin) == {"version", "kb_commit", "manifest_sha256", "names"}
    assert pin["manifest_sha256"] is None or len(pin["manifest_sha256"]) == 64
    assert all(P.NAME_RE.match(n) for n in pin["names"])


def test_every_pinned_prompt_loads():
    """Once prompts have moved: the private repository must be readable and match the pin. CI on a fork pull request
    has no token and sets FDA_PROMPTS_SKIP_NOTICE=1 (the workflow prints a notice); anywhere else a missing prompt fails."""
    pin = P.read_pin()
    assert bool(pin["names"]) == bool(pin["kb_commit"]) == bool(pin["manifest_sha256"]), "pin must be all set or all empty"
    if not pin["names"]:
        pytest.skip("stage 0: no prompt has moved yet")
    if os.environ.get("FDA_PROMPTS_SKIP_NOTICE") == "1":
        pytest.skip("fork pull request: private prompts are not available here (notice printed by the workflow)")
    for n in pin["names"]:
        assert P.load(n)
    assert set(P.names()) >= set(pin["names"])


def test_a_partial_pin_refuses(tmp_path):
    _make(tmp_path, {"a": "x"})
    with pytest.raises(P.PromptUnavailable, match="incomplete"):
        P.load("a", root=tmp_path, pin={"version": 1, "kb_commit": "0" * 40, "manifest_sha256": None, "names": []})


def test_malformed_entries_raise_promptunavailable(tmp_path):
    (tmp_path / "MANIFEST.json").write_text(json.dumps({"version": 1, "prompts": {"a": {"file": "a.txt"}, "b": 3}}))
    for n in ("a", "b"):
        with pytest.raises(P.PromptUnavailable, match="not valid"):
            P.load(n, root=tmp_path, pin=_pin(None))
    raw = b"\xff\xfe"
    (tmp_path / "c.txt").write_bytes(raw)
    (tmp_path / "MANIFEST.json").write_text(json.dumps({"version": 1, "prompts": {"c": {"file": "c.txt", "sha256": hashlib.sha256(raw).hexdigest(), "bytes": 2}}}))
    with pytest.raises(P.PromptUnavailable, match="UTF-8"):
        P.load("c", root=tmp_path, pin=_pin(None))


def live_prompt_texts() -> dict[str, str]:
    """Every prompt the agent sends a model, by name, read from wherever it now lives (module constants, or the private repository
    after the move), so the check below holds before and after a slice moves."""
    from agent.graph import closure, closure_playbook, contract, document, interview, plan_arm, router, spectest
    from agent.graph import run as gr
    t = {f"run.PROMPTS.{k}": v for k, v in gr.PROMPTS.items()}
    for mod, names in ((gr, ("CONVENTIONS", "HW_FORMAT", "FRESH_TESTS", "NO_SHELL_BULLET")), (contract, ("MODEL_CONTRACT",)),
                       (document, ("DOC_SYSTEM",)), (spectest, ("ROLE_SYSTEM", "TRIAGE_SYSTEM")), (router, ("ROUTER_SYSTEM",)),
                       (plan_arm, ("SYSTEM",)), (closure, ("SYSTEM",))):
        for n in names:
            t[f"{mod.__name__}.{n}"] = getattr(mod, n)
    t["interview.SpecOracle.SYSTEM"] = interview.SpecOracle.SYSTEM
    for s in closure_playbook.ALL:
        t[f"closure_playbook.{s.id}"] = s.instructions
    return t


def test_a_whole_episode_leaves_no_prompt_text_in_its_records(tmp_path, monkeypatch):
    """Brief 99 step 1: a scripted episode on T1 (interview, review, rewind, hardware approval) writes run records, review pages,
    summaries and transcripts; none holds a 12-word window of any prompt the agent sends. Records name prompts by hash
    (``agent.core.prompts.record``) where they used to carry the text."""
    import shutil
    import uuid

    pytest.importorskip("langgraph")
    pytest.importorskip("deepagents")
    from agent.core.session import ROOT
    from agent.graph import run as gr
    from agent.tests import test_episode as te
    from flow import hw
    from tools.prompts import leak_scan
    texts = live_prompt_texts()
    assert len(texts) > 40
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(gr, "RUNS", runs)
    monkeypatch.setattr(hw, "load_board", lambda b: {"cable_serial": "TEST0000"})
    monkeypatch.setattr(hw, "power_ok", lambda d, b: {"pass": True, "total_w": 0.15, "junction_c": 42.7, "source": "wall"})
    try:
        te._episode(tmp_path, runs)
        files = [p for p in runs.rglob("*") if p.is_file()]
        assert len(files) > 20
        hits = leak_scan.scan(None, leak_scan.DEFAULT_WORDS, files, texts=texts)
        assert not hits, [(Path(h[0]).name, h[1], h[2]) for h in hits]      # names only, never text
        # the scan can see a dump: the same files plus one that holds a prompt are caught
        dump = tmp_path / "dump.txt"
        dump.write_text(next(iter(texts.values())))
        assert leak_scan.scan(None, leak_scan.DEFAULT_WORDS, [dump], texts=texts)
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_record_keeps_hashes_not_text():
    r = P.record(task="some rendered text")
    assert r["task"] == {"sha256": hashlib.sha256(b"some rendered text").hexdigest(), "chars": 18}
    assert "some rendered text" not in json.dumps(r) and "prompts_pin" in r


def test_the_closure_task_record_is_a_hash_file():
    src = (Path(__file__).resolve().parents[1] / "graph" / "ip_closure_task.py").read_text()
    assert '"task.txt"' not in src and '"task.json"' in src
