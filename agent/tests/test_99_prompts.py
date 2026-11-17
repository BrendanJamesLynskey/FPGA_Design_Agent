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
    return {"version": 1, "kb_commit": "0" * 40, "manifest_sha256": sha, "names": []}


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


@pytest.mark.parametrize("bad", ["", "../x", "/abs", "A", "a//b", "a/b/", "a b", "a.txt"])
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
    if not pin["names"]:
        pytest.skip("stage 0: no prompt has moved yet")
    if os.environ.get("FDA_PROMPTS_SKIP_NOTICE") == "1":
        pytest.skip("fork pull request: private prompts are not available here (notice printed by the workflow)")
    for n in pin["names"]:
        assert P.load(n)
    assert set(P.names()) >= set(pin["names"])
