"""Tests never move the checkout they run from (brief fu-0112).

``conftest.py`` records the branch and HEAD at session start and fails the session if they differ at the end; these tests cover the
guard itself and the one tool that runs ``git checkout`` (the agent's rewind) against a design that sits inside a git checkout.
"""

import os
import subprocess

from agent.graph.snapshot import Snapshots
from tools.git_guard import ROOT, describe_change, repo_state


def _git(cwd, *a, env=None):
    e = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x", **(env or {})}
    return subprocess.run(["git", "-C", str(cwd), *a], check=True, capture_output=True, text=True, env=e).stdout.strip()


def _repo(path):
    path.mkdir()
    _git(path, "init", "-q", "-b", "work")
    (path / "a.txt").write_text("one\n")
    _git(path, "add", "a.txt")
    _git(path, "commit", "-q", "-m", "first")
    return path


def test_describe_change_names_what_moved():
    a = {"branch": "main", "head": "a" * 40}
    assert describe_change(a, dict(a)) is None
    assert describe_change(None, a) is None                                   # not a git checkout: nothing to compare
    assert "branch main -> (detached)" in describe_change(a, {"branch": None, "head": "a" * 40})
    assert "HEAD aaaaaaaaaaaa -> bbbbbbbbbbbb" in describe_change(a, {"branch": "main", "head": "b" * 40})


def test_repo_state_sees_a_detach(tmp_path):
    r = _repo(tmp_path / "r")
    before = repo_state(r)
    assert before["branch"] == "work"
    _git(r, "checkout", "-q", "--detach")
    after = repo_state(r)
    assert after["head"] == before["head"] and after["branch"] is None
    assert "(detached)" in describe_change(before, after)


def test_rewind_inside_a_checkout_leaves_that_checkout_alone(tmp_path, monkeypatch):
    """The design directory is a sub-directory of a git checkout (as a project is), and the caller's environment points at that checkout."""
    r = _repo(tmp_path / "r")
    design = r / "design"
    (design / "rtl").mkdir(parents=True)
    (design / "rtl" / "top.sv").write_text("module top; endmodule\n")
    before = repo_state(r)
    status = _git(r, "status", "--porcelain")
    monkeypatch.setenv("GIT_DIR", str(r / ".git"))                            # what a git hook or a wrapper script leaves in the environment
    monkeypatch.setenv("GIT_WORK_TREE", str(r))
    monkeypatch.setenv("GIT_INDEX_FILE", str(r / ".git" / "index"))
    snaps = Snapshots(tmp_path / "run", design)
    snaps.take(0, "clarify")
    (design / "rtl" / "top.sv").write_text("module top(input a); endmodule\n")
    snaps.take(2, "rtl")
    assert snaps.rewind(0)["verified"]
    assert repo_state(r) == before
    assert _git(r, "status", "--porcelain") == status                        # the caller's index is untouched too
    assert _git(r, "log", "--format=%s") == "first"


def test_the_checkout_this_suite_runs_from_is_as_it_was_at_the_start():
    """The session-level guard in conftest.py covers the whole run; this is the same check at one point, for a quick failure."""
    from conftest import _GIT_BEFORE
    assert describe_change(_GIT_BEFORE.get("state"), repo_state(ROOT)) is None
