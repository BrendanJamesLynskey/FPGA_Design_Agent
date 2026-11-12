"""Brief 08f golden request test (CVDP practice): every request path other than the new spec-test step is byte-for-byte what it
was at the last recorded golden. ``request_golden.collect()`` hashes the prompts, conventions, checklists, per-role plans (system
prompt, first user message, tool lists, limits), the Claude Code argv and MCP arguments, the interview oracle's prompt, the role
map and the tool registry.

Goldens, oldest first:

- ``eval1_request_golden.json``: taken at the ``eval-1`` tag (132b784). Kept, never edited: eval-1's recorded runs belong to it.
- ``b36_request_golden.json`` (brief 36, 2026-11-10): the registry gained ``skill_index`` and ``skill_excerpt`` and
  ``load_skill`` gained an optional ``name`` (``sections`` no longer required). With ``--skill-routing off`` (the default)
  every other hash still equals eval-1's: the prompts, plans, per-role tool lists, Claude Code argv and MCP arguments are
  unchanged, and no role is offered the new tools. The tool registry hash differs, and the ``load_skill`` schema a role sees
  differs with it, so eval-1's hashes no longer cover a whole run: a new baseline (brief 34) re-records against this file.
- ``b42_request_golden.json`` (brief 42 H9, 2026-11-11): the registry gained ``report_digest`` (schema 1.8.0). No role is offered
  it unless ``--harness-arm H9`` is on, so every hash other than ``tool_registry`` still equals the brief 36 golden's.
- ``b53_request_golden.json`` (brief 53, 2026-11-11): the clarify prompt asks for one checkable statement per requirement and
  no vague words; the tests prompt asks for requirement tags on every test, property and formal job. An intended change to what
  the clarify and tests roles are asked: ``prompts`` and the two formatted-prompt hashes differ from the brief 42 golden, nothing
  else. Runs before this change belong to the earlier goldens.
- ``b50a_request_golden.json`` (brief 50A, 2026-11-12): the registry gained ``debug_plan``, ``debug_capture`` and
  ``debug_query`` (schema 1.9.0). No role is offered them (they are not flow tools of any stage), so every hash other than
  ``tool_registry`` equals the brief 53 golden's.
- ``b59a_request_golden.json`` (brief 59A, 2026-11-12): the registry gained ``axi_program_check``, ``axi_simulate`` and
  ``axi_board_run`` (schema 1.10.0). No stage or role is offered them, so every hash other than ``tool_registry`` equals the
  brief 50A golden's."""

from __future__ import annotations

import json
from pathlib import Path

from agent.tests.request_golden import collect

FIXTURES = Path(__file__).parent / "fixtures"
EVAL1 = FIXTURES / "eval1_request_golden.json"
GOLDEN = FIXTURES / "b59a_request_golden.json"          # the newest golden
#: the hashes that differ from eval-1's, and the brief that changed each (an intended change is listed here, with why)
CHANGED_SINCE_EVAL1 = {"tool_registry": "brief 36: skill_index, skill_excerpt, load_skill(name=); brief 42 H9: report_digest; "
                                        "brief 50A: debug_plan, debug_capture, debug_query; brief 59A: axi_program_check, axi_simulate, axi_board_run",
                       "prompts": "brief 53: requirement quality (clarify) and requirement tags (tests)",
                       "prompts_formatted_noshell_False": "brief 53: as prompts",
                       "prompts_formatted_noshell_True": "brief 53: as prompts"}


def test_every_request_path_is_unchanged_from_the_golden() -> None:
    gold = json.loads(GOLDEN.read_text())
    now = collect()
    changed = sorted(k for k in gold["hashes"] if now.get(k) != gold["hashes"][k])
    extra = sorted(set(now) - set(gold["hashes"]))
    assert not changed and not extra, (
        f"request paths changed since {GOLDEN.name}: {changed}; new: {extra}. Only the spec-test step (agent/graph/spectest.py) "
        "may add requests; if a change is intended, it is a new evaluation (record why and write a new golden).")


def test_only_the_listed_hashes_differ_from_eval_1() -> None:
    old = json.loads(EVAL1.read_text())
    assert "132b784" in old["generated_on"]
    now = collect()
    changed = {k for k in old["hashes"] if now.get(k) != old["hashes"][k]}
    assert changed == set(CHANGED_SINCE_EVAL1), f"differs from eval-1: {sorted(changed)}"
    assert not set(now) - set(old["hashes"])


def test_spec_tests_are_off_by_default() -> None:
    from agent.graph.run import Config
    from agent.tests.request_golden import T1
    assert Config(spec_md=T1 / "spec.md", name="t").spec_tests is False
