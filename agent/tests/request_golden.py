"""Everything that decides what any model is asked in a run, collected as text and hashed (brief 08f, CVDP practice).

``collect()`` returns {name: sha256}. The committed ``fixtures/eval1_request_golden.json`` was produced by this same module run
on the ``eval-1`` tag (132b784); ``test_08f_golden_requests.py`` regenerates it on the current tree and fails if any request path
other than the new spec-test step changed. It imports only names that exist at ``eval-1``, so it can be run there::

    python3 -c "from agent.tests.request_golden import collect; import json; print(json.dumps(collect(), indent=1, sort_keys=True))"
"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
T1 = ROOT / "designs" / "t1_dimmer_counter"


def _h(x) -> str:
    t = x if isinstance(x, str) else json.dumps(x, sort_keys=True, default=str)
    return hashlib.sha256(t.encode()).hexdigest()[:16]


class _Ok:
    def run(self, kind, argv, cwd, env=None, timeout=600):
        from agent.core.runner import RunResult
        return RunResult(0, f"{kind}: ok", "", 0.0)


def collect() -> dict[str, str]:
    import agent.core.tools  # noqa: F401  (registers the tools)
    from agent.core import tool_list
    from agent.core.registry import TOOLS
    from agent.graph import interview, repair, role_models, roles
    from agent.graph import run as gr
    from agent.claude_code_arm import arm
    out: dict[str, str] = {}
    out["prompts"] = _h(gr.PROMPTS)
    out["conventions"] = _h(gr.CONVENTIONS)
    out["hw_format"] = _h(gr.HW_FORMAT)
    out["fresh_tests"] = _h(gr.FRESH_TESTS)
    out["no_shell_bullet"] = _h(gr.NO_SHELL_BULLET)
    out["model_contract"] = _h(gr.MODEL_CONTRACT)
    out["floors_text"] = _h(gr.floors_text())
    out["repair_note"] = _h(gr.repair_note("tests", ["a failure", "another"]))
    out["oracle_system"] = _h(interview.SpecOracle.SYSTEM)
    out["roles_rules"] = _h(roles.ROLES)
    out["roles_tools"] = _h({k: sorted(v) if v else v for k, v in roles.ROLE_TOOLS.items()})
    out["role_models_profiles"] = _h(role_models.PROFILES)
    out["tool_registry"] = _h({k: [v.description, getattr(v, "input_schema", None)] for k, v in sorted(TOOLS.items())})
    for stage in range(10):
        for role in ("clarify", "model", "tests", "rtl"):
            out[f"tools_{role}_{stage}"] = _h(gr.effective_tools(role, stage, "V3"))
    for shell in (False, True):
        fmt = {"board": "nexys_a7_100t", "name": "d", "stage": 2, "stage_name": "rtl-design-creation", "allowed": "x",
               "fails": "none", "note": "none", "design_rel": "runs/r/d", "no_shell": shell}
        out[f"conventions_text_noshell_{shell}"] = _h(gr.conventions_text(fmt))
        out[f"tests_conventions_text_noshell_{shell}"] = _h(gr.tests_conventions_text(fmt))
        out[f"prompts_formatted_noshell_{shell}"] = _h({k: v.format(**fmt) for k, v in gr.PROMPTS.items()
                                                       if k in ("clarify", "rtl")})
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    old = gr.RUNS
    gr.RUNS = runs
    try:
        cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", interview="off")
        rt = gr.new_runtime(cfg, lambda *a, **k: None, runner=_Ok())
        for stage_n in (2, 9):
            from agent.graph.stages import MACHINE
            rt.session.stage = MACHINE[stage_n].name
            for repair_ in (False, True):
                out[f"tests_checklist_{stage_n}_{repair_}"] = _h(gr.tests_checklist(rt, stage_n, repair_))
        rt.session.stage = "rtl-design-creation"
        for role in ("clarify", "model", "tests", "rtl"):
            for repair_ in (False, True):
                plan = gr.subagent_plan(rt, role, "PROMPT " + role, gr.role_allowed(role, 2), repair_)
                out[f"plan_{role}_{repair_}"] = _h({k: v for k, v in plan.items() if k != "limits"})
                out[f"plan_limits_{role}_{repair_}"] = _h(plan["limits"])
                if role == "tests":
                    pass
                argv = arm.cli_argv(rt, plan, Path("/x/mcp.json"), "claude-sonnet-5-5", "medium", 30)
                out[f"cli_argv_{role}_{repair_}"] = _h(argv)
                cfgm = arm.mcp_config(rt, plan)
                srv = cfgm["mcpServers"][arm.MCP_NAME]
                args = list(srv["args"])
                args[args.index("--design") + 1] = "<design>"
                out[f"mcp_args_{role}_{repair_}"] = _h(args)
        out["role_usage_resolve"] = _h(gr.Config(spec_md=T1 / "spec.md", name="t").role_models())
        out["oracle_cc_argv"] = _h(__import__("agent.claude_code_arm.oracle", fromlist=["x"])._argv("S", "U", "claude-haiku-5-5"))
        out["arm_constants"] = _h([arm.ACCEPTED_CLI, arm.MCP_NAME])
    finally:
        gr.RUNS = old
        shutil.rmtree(runs, ignore_errors=True)
    return out
