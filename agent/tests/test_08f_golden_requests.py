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
  brief 50A golden's.
- ``b54b_request_golden.json`` (2026-11-12): the test shell's protocol 1.1 adds the BUILD_ID register at 0x05 (recorded in
  benchmark/AMENDMENTS.md). The tests role reads the shell's PROTOCOL.md and host driver, so its plan and Claude Code argv
  hashes (``plan_tests_*``, ``cli_argv_tests_*``) differ from the brief 59A golden; nothing else does.
- ``b56a_request_golden.json`` (brief 56A, 2026-11-13): the registry gained ``gt_plan`` (the transceiver link planner). No stage or role
  is offered it yet (exposing it to the Designer is a follow-up that needs its own golden), so every hash other than ``tool_registry``
  equals the brief 54B golden's.
- ``b68_request_golden.json`` (brief 68 C, 2026-11-13, one deliberate re-pin; benchmark/AMENDMENTS.md): the text sent to models
  names the roles as the site and docs do since brief 67 (the Modeller, the Verifier, the Designer, the Clarifier; "reference
  model" for "blind model"; never "implementer"), in PROMPTS, CONVENTIONS ("Tests (Verifier)"), HW_FORMAT, MODEL_CONTRACT, the
  ``bringup`` tool description (schema 1.11.1) and the spec-test prompts (not hashed). The DOC step's prompt is new
  (``doc_system``). Eval-1 was stopped with no score, so no comparison is lost; runs before this belong to the earlier goldens.
- ``b68f_request_golden.json`` (brief 68F, 2026-11-13, one deliberate re-pin; benchmark/AMENDMENTS.md): only the DOC step's prompt
  changed (``doc_system``: answer from the files before asking, count latencies from the RTL, say when covers and bins disagree,
  re-measure first after an earlier-release build, say each fact once). Every other hash equals the brief 68 golden's.
- ``b71_request_golden.json`` (brief 71, 2026-11-14, one deliberate re-pin; benchmark/AMENDMENTS.md): the registry gained ``check``
  (the check suite, schema 1.12.0); the Designer is offered ``check`` at stages 1-9 and ``gt_plan`` (brief 56A) at stages 1-3, and
  the rtl prompt has a few lines on ``check``. Hence ``prompts`` (rtl only), the formatted prompts, ``tool_registry``,
  ``tools_rtl_1..9``, the rtl plans, Claude Code argv and MCP arguments. ``tools_clarify_1..9`` and the clarify plan, argv and MCP
  hashes move too: the golden hashes the clarify role at stages it never runs at (it runs only at stage 0, whose tools are
  unchanged), where role_allowed hands it the stage's tools. The Modeller's and the Verifier's requests are unchanged."""

from __future__ import annotations

import json
from pathlib import Path

from agent.tests.request_golden import collect

FIXTURES = Path(__file__).parent / "fixtures"
EVAL1 = FIXTURES / "eval1_request_golden.json"
GOLDEN = FIXTURES / "b70_request_golden.json"           # the newest golden
#: the hashes that differ from eval-1's, and the brief that changed each (an intended change is listed here, with why)
CHANGED_SINCE_EVAL1 = {"tool_registry": "brief 36: skill_index, skill_excerpt, load_skill(name=); brief 42 H9: report_digest; "
                                        "brief 50A: debug_plan, debug_capture, debug_query; brief 59A: axi_program_check, axi_simulate, axi_board_run; brief 56A: gt_plan; "
                                        "brief 68: bringup description (reference model); brief 71: check; brief 73: check name axi_profile",
                       "prompts": "brief 53: requirement quality (clarify) and requirement tags (tests); brief 68: role names; "
                                  "brief 71: the check tool (rtl); brief 73: the interface profile (clarify, rtl); "
                                  "brief 70: the Designer's reset paragraph (rtl)",
                       "conventions": "brief 68: role names (Tests (Verifier))",
                       "conventions_text_noshell_False": "brief 68: as conventions",
                       "conventions_text_noshell_True": "brief 68: as conventions",
                       "tests_conventions_text_noshell_False": "brief 68: as conventions",
                       "tests_conventions_text_noshell_True": "brief 68: as conventions",
                       "hw_format": "brief 68: reference model for blind model",
                       "model_contract": "brief 68: the Modeller and the Verifier",
                       "prompts_formatted_noshell_False": "brief 53: as prompts; brief 73: as prompts; brief 70: as prompts",
                       "prompts_formatted_noshell_True": "brief 53: as prompts; brief 73: as prompts; brief 70: as prompts",
                       "plan_tests_False": "shell 1.1 (BUILD_ID at 0x05): the tests role reads the shell's protocol and driver",
                       "plan_tests_True": "shell 1.1: as plan_tests_False",
                       "cli_argv_tests_False": "shell 1.1: as plan_tests_False",
                       "cli_argv_tests_True": "shell 1.1: as plan_tests_False",
                       "cli_argv_clarify_False": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "cli_argv_clarify_True": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "cli_argv_rtl_False": "brief 71: check and gt_plan offered to the Designer",
                       "cli_argv_rtl_True": "brief 71: check and gt_plan offered to the Designer",
                       "mcp_args_clarify_False": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "mcp_args_clarify_True": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "mcp_args_rtl_False": "brief 71: check and gt_plan offered to the Designer",
                       "mcp_args_rtl_True": "brief 71: check and gt_plan offered to the Designer",
                       "plan_clarify_False": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "plan_clarify_True": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "plan_rtl_False": "brief 71: check and gt_plan offered to the Designer",
                       "plan_rtl_True": "brief 71: check and gt_plan offered to the Designer",
                       "tools_clarify_1": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "tools_clarify_2": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "tools_clarify_3": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "tools_clarify_4": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "tools_clarify_5": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "tools_clarify_6": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "tools_clarify_7": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "tools_clarify_8": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "tools_clarify_9": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "tools_rtl_1": "brief 71: check and gt_plan offered to the Designer",
                       "tools_rtl_2": "brief 71: check and gt_plan offered to the Designer",
                       "tools_rtl_3": "brief 71: check and gt_plan offered to the Designer",
                       "tools_rtl_4": "brief 71: check and gt_plan offered to the Designer",
                       "tools_rtl_5": "brief 71: check and gt_plan offered to the Designer",
                       "tools_rtl_6": "brief 71: check and gt_plan offered to the Designer",
                       "tools_rtl_7": "brief 71: check and gt_plan offered to the Designer",
                       "tools_rtl_8": "brief 71: check and gt_plan offered to the Designer",
                       "tools_rtl_9": "brief 71: check and gt_plan offered to the Designer"}
#: request paths added since eval-1 (absent from its golden), and the brief that added each
NEW_SINCE_EVAL1 = {"doc_system": "brief 68 C: the DOC step at the end of a run (agent.graph.document)"}


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
    assert set(now) - set(old["hashes"]) == set(NEW_SINCE_EVAL1)


def test_spec_tests_are_off_by_default() -> None:
    from agent.graph.run import Config
    from agent.tests.request_golden import T1
    assert Config(spec_md=T1 / "spec.md", name="t").spec_tests is False
