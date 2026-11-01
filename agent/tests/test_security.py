"""The security layer: path jail, argument validation, redaction, hardware budget, audit log."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agent.core import dispatch
from agent.core.security import HardwarePolicy, PathJail, SecurityError, redact, validate_args


def test_jail_confines_reads_and_writes(tmp_path: Path) -> None:
    root = tmp_path / "d"
    root.mkdir()
    (tmp_path / "secret.txt").write_text("x")
    j = PathJail(root)
    assert j.resolve("a/b.sv", write=True) == root.resolve() / "a" / "b.sv"
    for bad in ("../secret.txt", "/etc/passwd", "~/.ssh/id_rsa", "a/../../secret.txt", "", "a\x00b", str(tmp_path / "secret.txt")):
        with pytest.raises(SecurityError) as e:
            j.resolve(bad)
        assert e.value.rule == "path-jail"


def test_jail_resolves_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "d"
    root.mkdir()
    (tmp_path / "outside").mkdir()
    os.symlink(tmp_path / "outside", root / "link")
    os.symlink(tmp_path / "secret", root / "flink")
    j = PathJail(root)
    for bad in ("link/x", "link", "flink"):
        with pytest.raises(SecurityError):
            j.resolve(bad)
    with pytest.raises(SecurityError):
        j.resolve("link/new.txt", write=True)


def test_jail_write_deny(tmp_path: Path) -> None:
    j = PathJail(tmp_path)
    for bad in ("build/gates.json", "build/base/x", ".git/config", ".env"):
        with pytest.raises(SecurityError):
            j.resolve(bad, write=True)
    j.resolve("build/base/power.rpt")                   # reading build outputs is fine


def test_schema_validation_is_strict() -> None:
    schema = {"type": "object", "properties": {"variant": {"type": "string", "enum": ["base", "ila"]}},
              "additionalProperties": False}
    validate_args(schema, {"variant": "base"})
    for bad in ({"variant": "flash"}, {"variant": "base", "tcl": "exec rm -rf /"}, {"variant": 3}):
        with pytest.raises(SecurityError) as e:
            validate_args(schema, bad)
        assert e.value.rule == "arguments"


def test_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_API_KEY", "supersecretvalue123")
    text = ("key supersecretvalue123 and sk-or-v1-abcdef0123456789 and ghp_abcdefghijklmnopqrstuv and "
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123 -----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n"
            "-----END OPENSSH PRIVATE KEY-----")
    out = redact(text)
    for leak in ("supersecretvalue123", "sk-or-v1-abcdef", "ghp_abcdef", "abcdefghijklmnopqrstuvwxyz0123", "AAAA"):
        assert leak not in out
    assert "[REDACTED" in out


def test_hardware_budget() -> None:
    hw = HardwarePolicy(budget=3)
    hw.charge("program")
    hw.charge("bringup")
    with pytest.raises(SecurityError) as e:
        hw.charge("program")
    assert e.value.rule == "hardware-budget"


def test_secrets_never_reach_audit_or_trace(session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from agent.core.trace import Trace
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-0123456789abcdef0123456789abcdef")
    session.trace = Trace(tmp_path / "trace.jsonl")
    (session.design / "notes.txt").write_text("the key is sk-or-v1-0123456789abcdef0123456789abcdef")
    r = dispatch(session, "read_file", {"path": "notes.txt"})
    dispatch(session, "write_file", {"path": "k.txt", "content": "sk-or-v1-0123456789abcdef0123456789abcdef"})
    assert "0123456789abcdef" not in json.dumps(r)
    assert "0123456789abcdef" not in (session.design / "build" / "audit.jsonl").read_text()
    assert "0123456789abcdef" not in (tmp_path / "trace.jsonl").read_text()


def test_audit_log_records_every_call_and_refusal(session) -> None:
    dispatch(session, "list_files", {})
    dispatch(session, "read_file", {"path": "../../flow/gates.py"})
    dispatch(session, "nonexistent", {})
    recs = [json.loads(l) for l in (session.design / "build" / "audit.jsonl").read_text().splitlines()]
    assert [r["tool"] for r in recs] == ["list_files", "read_file", "nonexistent"]
    assert [r["refused"] for r in recs] == [False, True, True]
    assert recs[1]["rule"] == "path-jail" and recs[1]["stage"] == "clarify" and "t" in recs[1]
