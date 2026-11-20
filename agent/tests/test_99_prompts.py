"""Brief 99: the private prompt loader. Fixtures are made up here (no real prompt text is ever in this repository)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
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


def test_a_manifest_that_is_not_the_pinned_one_is_refused(tmp_path, monkeypatch):
    monkeypatch.delenv(P.ENV_UNPINNED, raising=False)
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


def _drive_hook(exc):
    import conftest
    g = conftest.pytest_runtest_call(None)
    next(g)
    try:
        g.throw(exc)
    except StopIteration:
        return None


def test_a_missing_prompt_skips_only_where_the_workflow_says_it_is_a_fork(monkeypatch):
    monkeypatch.setenv("FDA_PROMPTS_SKIP_NOTICE", "1")
    with pytest.raises(pytest.skip.Exception):
        _drive_hook(P.PromptUnavailable("x"))
    with pytest.raises(ValueError):                                         # other errors are never skipped
        _drive_hook(ValueError("x"))
    monkeypatch.delenv("FDA_PROMPTS_SKIP_NOTICE")
    with pytest.raises(P.PromptUnavailable):                                # a trusted run fails
        _drive_hook(P.PromptUnavailable("x"))


def test_no_prompt_text_in_the_tracked_files():
    """Brief 99 step 2, the CI gate: no tracked file holds 12 consecutive words of a private prompt, except the entries of
    tools/prompts/leak_allow.txt (each with a reason). Where the prompts are not available (a fork pull request) the loader raises and
    the conftest hook skips this test with the workflow's notice; on any other run a missing prompt fails it."""
    from tools.prompts import leak_scan
    allow = leak_scan.read_allow(leak_scan.ROOT / "tools" / "prompts" / "leak_allow.txt")
    assert allow and all((leak_scan.ROOT / a).exists() for a in allow), "an allow-list entry names a path that does not exist"
    hits = leak_scan.scan(P.prompts_dir(), leak_scan.DEFAULT_WORDS)           # one scan; the allow-list is applied below

    def covered(path, a):
        if "!" in path:                                                      # an archive member: never allow-listed
            return False
        return path == a or (a.endswith("/") and path.startswith(a))
    loose = [(h[0], h[1], h[2]) for h in hits if not any(covered(h[0], a) for a in allow)]
    assert not loose, loose                                                  # path, line and prompt name; never text
    # archives are opened by the scan (.tar.gz, .gz, .zip members); one that carries prompt text, or cannot be read, fails
    files = [leak_scan.ROOT / p for p in subprocess.run(["git", "ls-files", "-z"], cwd=leak_scan.ROOT, capture_output=True, check=True)
             .stdout.decode().split("\0") if p]
    assert not leak_scan.unreadable_archives(files), leak_scan.unreadable_archives(files)
    stale = [a for a in allow if not any(covered(h[0], a) for h in hits)]
    assert not stale, f"allow-list entries that no longer cover anything: {stale}"


def test_every_moved_prompt_still_has_its_recorded_hash():
    """The snapshot of the moved prompts: each prompt's SHA-256 as committed at the move (``fixtures/b99_prompt_hashes.json``). A prompt
    change shows here by name, without the text, and has to be re-pinned on purpose."""
    snap = json.loads((Path(__file__).parent / "fixtures" / "b99_prompt_hashes.json").read_text())
    assert sorted(snap) == sorted(P.read_pin()["names"])
    changed = [n for n, sha in snap.items() if hashlib.sha256(P.load(n).encode("utf-8")).hexdigest() != sha]
    assert not changed, changed


def _fp_texts():
    return {"demo": "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar"}


def test_leak_scan_looks_inside_archives(tmp_path):
    """Brief 99 step 2: a .tar.gz, a .gz, a .zip and an archive nested in an archive are opened; the hit names the member, never text."""
    import gzip
    import io
    import tarfile
    import zipfile

    from tools.prompts import leak_scan
    dump = _fp_texts()["demo"].encode()
    clean = b"nothing to see here, just a few unrelated words in a record"
    tgz = tmp_path / "run_dir.tar.gz"
    with tarfile.open(tgz, "w:gz") as t:
        for name, data in (("r/clean.txt", clean), ("r/claude_code/001.system.txt", dump)):
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            t.addfile(ti, io.BytesIO(data))
    gz = tmp_path / "stdout.txt.gz"
    gz.write_bytes(gzip.compress(dump))
    zp = tmp_path / "x.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("a/b.txt", dump)
    inner = io.BytesIO()
    with tarfile.open(fileobj=inner, mode="w:gz") as t:
        ti = tarfile.TarInfo("deep.txt")
        ti.size = len(dump)
        t.addfile(ti, io.BytesIO(dump))
    with zipfile.ZipFile(tmp_path / "wrap.zip", "w") as z:
        z.writestr("inner.tar.gz", inner.getvalue())
    ok_gz = tmp_path / "clean.txt.gz"
    ok_gz.write_bytes(gzip.compress(clean))
    texts = _fp_texts()
    for f, member in ((tgz, "claude_code/001.system.txt"), (gz, "stdout.txt"), (zp, "a/b.txt"), (tmp_path / "wrap.zip", "deep.txt")):
        hits = leak_scan.scan(None, 12, [f], allow=[str(f)], texts=texts)                # an allow entry does not cover an archive
        assert len(hits) == 1 and "!" in hits[0][0] and hits[0][0].endswith(member), (f.name, hits)
        assert dump.decode() not in repr(hits)
    assert not leak_scan.scan(None, 12, [ok_gz], texts=texts)
    assert leak_scan.unreadable_archives([tgz, gz, zp, ok_gz]) == []
    bad = tmp_path / "broken.tar.gz"
    bad.write_bytes(b"not an archive at all")
    assert leak_scan.unreadable_archives([bad])
    corrupt = tmp_path / "corrupt.zip"                                      # a bad member CRC / truncated zip is reported, not passed
    corrupt.write_bytes((tmp_path / "x.zip").read_bytes()[:-30])
    assert leak_scan.unreadable_archives([corrupt])


def test_archives_moved_to_the_private_repository_leave_a_pointer_with_the_hash():
    """Every b82p2/b82p3/b82p4 ``run_dir.tar.gz`` is private; the public tree holds ``run_dir.tar.gz.pointer.json`` with the SHA-256, which is the
    one the run's record already carries."""
    root = Path(__file__).resolve().parents[2] / "benchmark" / "v2" / "runs"
    ptrs = sorted(root.glob("b82p*/artifacts/*/run_dir.tar.gz.pointer.json"))
    assert len(ptrs) == 27
    assert not list(root.glob("b82p*/artifacts/*/run_dir.tar.gz")), "a rendered-prompt archive is tracked again"
    for p in ptrs:
        d = json.loads(p.read_text())
        assert set(d) == {"moved_to", "sha256", "bytes", "why"} and len(d["sha256"]) == 64
        recs = (p.parents[2] / "records").glob("*.json")
        assert any(d["sha256"] in r.read_text() for r in recs), p
        kb = os.environ.get("FDA_KB_CHECKOUT") or str(P.prompts_dir().parent)                # the private checkout, where there is one
        priv = Path(kb) / d["moved_to"].split("/", 1)[1]
        if priv.is_file():
            assert hashlib.sha256(priv.read_bytes()).hexdigest() == d["sha256"], p


def test_runs_archives_stay_untracked():
    gi = (Path(__file__).resolve().parents[2] / ".gitignore").read_text()
    assert "benchmark/v2/runs/*/artifacts/*/run_dir.tar.gz" in gi
