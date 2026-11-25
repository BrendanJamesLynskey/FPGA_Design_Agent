"""Brief 209a: the Anthropic key file route of agent/models/endpoints.py. Every test uses a temporary HOME; the real file is never read."""
from __future__ import annotations

import pytest

from agent.models import endpoints as E


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    d = tmp_path / ".config" / "fpga_design_agent"
    d.mkdir(parents=True)
    return d


def test_key_file_is_used_when_the_variable_is_unset(home):
    f = home / "anthropic.env"
    f.write_text("ANTHROPIC_API_KEY=sk-test-file\n")
    f.chmod(0o600)
    assert E.anthropic_key_file() == f
    assert E.read_key("ANTHROPIC_API_KEY") == "sk-test-file"


def test_the_environment_wins_over_the_file(home, monkeypatch):
    f = home / "anthropic.env"
    f.write_text("ANTHROPIC_API_KEY=sk-test-file\n")
    f.chmod(0o600)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-env")
    assert E.read_key("ANTHROPIC_API_KEY") == "sk-test-env"


def test_a_file_readable_by_others_is_refused(home):
    f = home / "anthropic.env"
    f.write_text("ANTHROPIC_API_KEY=sk-test-file\n")
    f.chmod(0o644)
    with pytest.raises(ValueError, match="chmod 600"):
        E.read_key("ANTHROPIC_API_KEY")


def test_no_file_no_key_and_the_client_says_where_it_looked(home):
    assert E.read_key("ANTHROPIC_API_KEY") is None
    with pytest.raises(ValueError, match="anthropic.env"):
        E.AnthropicClient("claude-sonnet-5-5", key_env="ANTHROPIC_API_KEY")


def test_the_anthropic_file_does_not_serve_other_variables(home):
    f = home / "anthropic.env"
    f.write_text("ANTHROPIC_API_KEY=sk-test-file\n")
    f.chmod(0o600)
    assert E.read_key("SOMETHING_ELSE") is None


def test_opus_and_fable_stay_blocked_on_anthropic_api():
    from agent.models.config import FORBIDDEN_VIA_NETWORK
    assert FORBIDDEN_VIA_NETWORK == ("anthropic/", "fable", "opus")
