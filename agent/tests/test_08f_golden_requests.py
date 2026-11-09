"""Brief 08f golden request test (CVDP practice): every request path other than the new spec-test step is byte-for-byte what it
was at the ``eval-1`` tag. ``request_golden.collect()`` hashes the prompts, conventions, checklists, per-role plans (system
prompt, first user message, tool lists, limits), the Claude Code argv and MCP arguments, the interview oracle's prompt, the role
map and the tool registry; the committed golden file is that collection taken at ``eval-1`` (132b784)."""

from __future__ import annotations

import json
from pathlib import Path

from agent.tests.request_golden import collect

GOLDEN = Path(__file__).parent / "fixtures" / "eval1_request_golden.json"


def test_every_request_path_is_unchanged_from_eval_1() -> None:
    gold = json.loads(GOLDEN.read_text())
    assert "132b784" in gold["generated_on"]
    now = collect()
    changed = sorted(k for k in gold["hashes"] if now.get(k) != gold["hashes"][k])
    extra = sorted(set(now) - set(gold["hashes"]))
    assert not changed and not extra, (
        f"request paths changed since eval-1: {changed}; new: {extra}. Only the spec-test step (agent/graph/spectest.py) may "
        "add requests; if a change is intended, it is a new evaluation (record why and regenerate on the new tag).")


def test_spec_tests_are_off_by_default() -> None:
    from agent.graph.run import Config
    from agent.tests.request_golden import T1
    assert Config(spec_md=T1 / "spec.md", name="t").spec_tests is False
