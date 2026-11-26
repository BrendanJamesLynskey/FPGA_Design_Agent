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
  unchanged), where role_allowed hands it the stage's tools. The Modeller's and the Verifier's requests are unchanged.
- ``b97_request_golden.json`` (brief 97, 2026-11-17): the registry gained ``latency_path`` and ``latency_budget`` (schema 1.13.0). No stage or role of
  the agent graph is offered them (the latency loop, ``agent/graph/latency_loop.py``, offers them to its own arm), so every hash other than
  ``tool_registry`` equals the brief 80 golden's.
- ``b101_request_golden.json`` (brief 101, 2026-11-18): the registry gained ``oss_synth`` and ``eqy_check`` (schema 1.14.0). No stage or role of
  the agent graph is offered them, so every hash other than ``tool_registry`` equals the brief 97 golden's.
- ``b96d_request_golden.json`` (brief 96D, 2026-11-19): the registry gained ``eye_scan`` (schema 1.15.0; reads an eye-scan capture, never runs the board). No stage or role of
  the agent graph is offered it, so every hash other than ``tool_registry`` equals the brief 101 golden's.
- ``b104_request_golden.json`` (brief 104, 2026-11-19): the registry gained ``design_analysis`` (schema 1.16.0; the read-only analysis behind ``agent improve``). No stage or role of
  the agent graph is offered it, so every hash other than ``tool_registry`` equals the brief 96D golden's.
- ``b106_request_golden.json`` (brief 106, 2026-11-19): the ``check`` tool's name list gained ``constants`` and ``stale`` (schema 1.17.0). No stage or role
  is offered a new tool, so every hash other than ``tool_registry`` equals the brief 104 golden's.
- ``b105a_request_golden.json`` (brief 105A, 2026-11-19): the ``check`` tool's name list gained ``constraint_scope`` and ``xpm_sim`` (schema 1.18.0). No stage or role
  is offered a new tool, so every hash other than ``tool_registry`` equals the brief 106 golden's.
- ``b114_request_golden.json`` (brief 114, 2026-11-20): the registry gained ``doc_crossread`` (schema 1.19.0; the optional blind document cross-read, read-only). No stage or role
  is offered it, so every hash other than ``tool_registry`` equals the brief 105A golden's.
- ``b150_request_golden.json`` (brief 150, 2026-11-21): the registry gained ``ip_lookup`` (schema 1.20.0; the read-only IP-library query) and it is offered at
  stage 1 (the board-and-device-planning stage), so ``tool_registry``, ``tools_rtl_1`` and ``tools_clarify_1`` (the stage-1 tool lists) differ from the brief 114
  golden's and nothing else does. The stage-1 conventions bullet that tells the Designer about it is appended in ``agent/graph/run.py`` (like the design-plan
  bullet), not in the hashed prompts.
- ``b205_request_golden.json`` (brief 205, 2026-11-24, owner decision 38): the Designer's conventions list the design-standards rules
  (``agent/graph/run.py`` ``_standards_summary`` from ``flow/standards_check.py`` ``RULES``), and the STD-INIT-01 text changed from "no initial blocks" to
  "initial values follow the setting rtl.initial_values (default allow)". Only ``conventions_text_noshell_False`` and ``conventions_text_noshell_True``
  differ from the brief 150 golden. Runs before this change belong to the earlier goldens.
- ``b206_request_golden.json`` (brief 206, 2026-11-24): the ``check`` tool's name list gained ``init_values`` (schema 1.21.0). No stage or role is offered
  a new tool, so every hash other than ``tool_registry`` equals the brief 205 golden's.
- ``b207_request_golden.json`` (brief 207, 2026-11-25): the ``check`` tool's name list gained ``cdc_margin`` (schema 1.22.0). No stage or role is offered a
  new tool, so every hash other than ``tool_registry`` equals the brief 206 golden's.
- ``b208_request_golden.json`` (brief 208, 2026-11-24): the ``check`` tool's name list gained ``clock_mux`` (schema 1.23.0). No stage or role
  is offered a new tool, so every hash other than ``tool_registry`` equals the brief 207 golden's.
- ``b190_request_golden.json`` (brief 190, 2026-11-23): the ``check`` tool's name list gained ``fastpath`` (schema 1.24.0; an advisory source check). No stage or role
  is offered a new tool, so every hash other than ``tool_registry`` equals the brief 208 golden's.
- ``b224_request_golden.json`` (brief 224, 2026-11-25): the stage-2 Designer's request gained the file-by-file instruction (``agent/graph/run.py``
  ``FILE_BY_FILE_NOTE``, appended after the conventions, like the JTAG note) and, after a reply cut off at the output limit, the note of the files on disk and
  the blocks still missing (``files_status_note``). Both are new request paths (``file_by_file_note``, ``files_status_note``); every other hash equals the brief 190
  golden's. Runs before this change belong to the earlier goldens.
- ``b231_request_golden.json`` (brief 231, 2026-11-26, owner decision on initial values and resets): the Designer's conventions list the design-standards rules
  (``_standards_summary`` from ``flow/standards_check.py`` ``RULES``) and ``STD-INIT-02`` is new. Only ``conventions_text_noshell_False`` and
  ``conventions_text_noshell_True`` differ from the brief 224 golden. Runs before this change belong to the earlier goldens.
- ``b225_request_golden.json`` (brief 225, 2026-11-26, on the tree with briefs 224 and 231): the registry gained ``drive_instrument`` (schema 1.25.0; the lab tool: it checks a
  drive request against the lab file's limits and records it, and enables nothing). No stage or role is offered it, so every hash other than ``tool_registry`` equals the
  brief 231 golden's.
- ``b239_request_golden.json`` (brief 239, 2026-11-26): the stage-2 Designer's request gained the list of what the stage-2 gates check (``agent/graph/run.py``
  ``stage2_rules_note``, built from ``flow/hdl_rules.yaml``, appended after the conventions like ``FILE_BY_FILE_NOTE``). One new request path
  (``stage2_rules_note``); every other hash equals the brief 225 golden's. Runs before this change belong to the earlier goldens."""

from __future__ import annotations

import json
from pathlib import Path

from agent.tests.request_golden import collect

FIXTURES = Path(__file__).parent / "fixtures"
EVAL1 = FIXTURES / "eval1_request_golden.json"
GOLDEN = FIXTURES / "b239_request_golden.json"          # the newest golden
#: the hashes that differ from eval-1's, and the brief that changed each (an intended change is listed here, with why)
CHANGED_SINCE_EVAL1 = {"arm_constants": "brief 80: Claude Code 2.1.321 accepted (ACCEPTED_CLI; the tool-text check passed)",
                       "tool_registry": "brief 36: skill_index, skill_excerpt, load_skill(name=); brief 42 H9: report_digest; "
                                        "brief 50A: debug_plan, debug_capture, debug_query; brief 59A: axi_program_check, axi_simulate, axi_board_run; brief 56A: gt_plan; "
                                        "brief 68: bringup description (reference model); brief 71: check; brief 73: check name axi_profile; brief 97: latency_path, latency_budget; "
                                        "brief 101: oss_synth, eqy_check (no role is offered them); brief 96D: eye_scan (no role is offered it); brief 104: design_analysis (no role is offered it); brief 106: check names constants and stale; brief 105A: check names constraint_scope and xpm_sim; brief 114: doc_crossread (no role is offered it); brief 150: ip_lookup (offered to the Designer at stage 1); brief 206: check name init_values; brief 207: check name cdc_margin; brief 208: check name clock_mux; brief 190: check name fastpath; brief 225: drive_instrument (no role is offered it)",
                       "prompts": "brief 53: requirement quality (clarify) and requirement tags (tests); brief 68: role names; "
                                  "brief 71: the check tool (rtl); brief 73: the interface profile (clarify, rtl); "
                                  "brief 70: the Designer's reset paragraph (rtl)",
                       "conventions": "brief 68: role names (Tests (Verifier))",
                       "conventions_text_noshell_False": "brief 68: as conventions; brief 205: the STD-INIT-01 rule text (rtl.initial_values); brief 231: STD-INIT-02",
                       "conventions_text_noshell_True": "brief 68: as conventions; brief 205: the STD-INIT-01 rule text (rtl.initial_values); brief 231: STD-INIT-02",
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
                       "tools_clarify_1": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at); brief 150: ip_lookup at stage 1",
                       "tools_clarify_2": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "tools_clarify_3": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "tools_clarify_4": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "tools_clarify_5": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "tools_clarify_6": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "tools_clarify_7": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "tools_clarify_8": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "tools_clarify_9": "brief 71: check and gt_plan offered to the Designer (clarify: at stages it never runs at)",
                       "tools_rtl_1": "brief 71: check and gt_plan offered to the Designer; brief 150: ip_lookup at stage 1",
                       "tools_rtl_2": "brief 71: check and gt_plan offered to the Designer",
                       "tools_rtl_3": "brief 71: check and gt_plan offered to the Designer",
                       "tools_rtl_4": "brief 71: check and gt_plan offered to the Designer",
                       "tools_rtl_5": "brief 71: check and gt_plan offered to the Designer",
                       "tools_rtl_6": "brief 71: check and gt_plan offered to the Designer",
                       "tools_rtl_7": "brief 71: check and gt_plan offered to the Designer",
                       "tools_rtl_8": "brief 71: check and gt_plan offered to the Designer",
                       "tools_rtl_9": "brief 71: check and gt_plan offered to the Designer"}
#: request paths added since eval-1 (absent from its golden), and the brief that added each
NEW_SINCE_EVAL1 = {"doc_system": "brief 68 C: the DOC step at the end of a run (agent.graph.document)",
                   "file_by_file_note": "brief 224: the stage-2 Designer writes one file per call", "files_status_note": "brief 224: files on disk and blocks missing after a cut-off reply",
                   "stage2_rules_note": "brief 239: what the stage-2 gates check, shown to the Designer before it writes RTL"}


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
