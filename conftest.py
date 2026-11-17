"""Repo-wide pytest options: on-board tests are marked ``hw`` and skipped unless asked for.

    python -m pytest -m hw --hw-port /dev/serial/by-id/... --hw-stamp dfd4624e designs/t1_dimmer_counter
(flow/bringup.py runs them this way, after programming the board.) Without ``--hw-port``
every ``hw`` test is skipped, so CI and a plain ``pytest`` never touch a serial port.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))      # importlib import mode does not add the root
from tools.git_guard import describe_change, repo_state

_GIT_BEFORE = {}


def pytest_addoption(parser: pytest.Parser) -> None:
    g = parser.getgroup("hw", "tests on the attached board")
    g.addoption("--hw-port", default=None, help="the board's UART device; enables the hw tests")
    g.addoption("--hw-stamp", default=None, help="build stamp (8 hex digits) the bitstream must report")
    g.addoption("--hw-seed", type=int, default=20261030, help="seed for the random loopback values")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "access_gate: tests of the access gate itself (agent/access); they run with the test bypass off")
    config.addinivalue_line("markers", "hw: needs the programmed board on --hw-port (skipped otherwise)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--hw-port"):
        return
    skip = pytest.mark.skip(reason="hw test: needs the board (--hw-port)")
    for item in items:
        if "hw" in item.keywords:
            item.add_marker(skip)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    """Brief 99: a fork pull request has no token for the private prompts (the workflow sets FDA_PROMPTS_SKIP_NOTICE=1 and prints a
    notice), so a test that needs a prompt skips there. Anywhere else a missing prompt is a failure, never a skip."""
    try:
        return (yield)
    except Exception as e:
        if type(e).__name__ == "PromptUnavailable" and os.environ.get("FDA_PROMPTS_SKIP_NOTICE") == "1":
            pytest.skip("private prompts are not available here (fork pull request)")
        raise


@pytest.fixture(autouse=True)
def _private_heavy_lock(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """07a2 fix 4: the suite never waits on, or writes, the owner's shared ``_handoff/heavy_slot.lock``. Tests of the
    mutation and coverage tools take a lock; with ``$FDA_HEAVY_LOCK`` unset they would use the shared one and hang while
    a real job holds it. A test that needs its own path sets the variable again."""
    monkeypatch.setenv("FDA_HEAVY_LOCK", str(tmp_path_factory.mktemp("heavy") / "heavy_slot.lock"))


def pytest_sessionstart(session: pytest.Session) -> None:
    _GIT_BEFORE["state"] = repo_state()          # the checkout the tests run from: branch and HEAD (tools/git_guard.py)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    msg = describe_change(_GIT_BEFORE.get("state"), repo_state())
    if msg:
        print(f"\nERROR: {msg}")
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


#: tool names whose absence makes a formal test skip; with FDA_REQUIRE_FORMAL=1 (set on the CI jobs that run formal tests) such
#: a skip is a failure, so a formal step can never pass by skipping because a tool was not on the PATH (brief 81)
FORMAL_SKIP = ("sby", "yosys", "boolector", "z3")


def formal_skip_is_failure(reason: str, env: dict) -> bool:
    return env.get("FDA_REQUIRE_FORMAL") == "1" and any(t in reason.lower() for t in FORMAL_SKIP)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    import os
    out = yield
    rep = out.get_result()
    if rep.skipped and isinstance(rep.longrepr, tuple):
        reason = str(rep.longrepr[2])
        if formal_skip_is_failure(reason, os.environ):
            rep.outcome = "failed"
            rep.longrepr = f"formal test skipped with FDA_REQUIRE_FORMAL=1: {reason}"


@pytest.fixture(autouse=True)
def _access_gate_bypass(request: pytest.FixtureRequest):
    """Brief 94: in-process tests of entry points (replays, fake clients) run without the access key, so a fork's CI
    does not fail when the secret is absent. The gate's own tests are marked ``access_gate`` and run it for real."""
    from agent import access
    old = access._TEST_BYPASS
    access.CURRENT = None                       # a gate test's admitted name must not leak into later tests' audit logs
    access._TEST_BYPASS = request.node.get_closest_marker("access_gate") is None
    yield
    access._TEST_BYPASS = old
    access.CURRENT = None
