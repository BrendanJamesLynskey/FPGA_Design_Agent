"""The inventory of model call sites (brief 108): every place the repository calls a model, the purpose it serves, the prompt it
uses (the private knowledge repository's brief 99 manifest name; ``public`` where the prompt is still in code) and how it
picked its model before the table. ``agent/tests/test_108_model_config.py`` checks that every file and purpose named here exists,
and that no model call is made outside these sites (the gate), so the list cannot silently go stale.
"""

from __future__ import annotations

#: (file, function, purpose(s), needs, prompt names, how the model was picked before brief 108)
SITES: list[dict[str, object]] = [
    {"file": "agent/graph/run.py", "fn": "_run_subagent (Deep Agents branch)", "purposes": ["interpret", "model", "tests", "rtl", "constraints"],
     "needs": "agent", "prompts": ["graph/run/prompt_clarify", "graph/run/prompt_model", "graph/run/prompt_tests", "graph/run/prompt_hwtests",
                                   "graph/run/prompt_rtl"], "before": "role_models.resolve: --harness/--model/--profile/--roles (cfg.model, role@stage)"},
    {"file": "agent/claude_code_arm/arm.py", "fn": "run_subagent_cc", "purposes": ["interpret", "model", "tests", "rtl", "constraints"],
     "needs": "agent", "prompts": ["graph/run/prompt_clarify", "graph/run/prompt_model", "graph/run/prompt_tests", "graph/run/prompt_hwtests",
                                   "graph/run/prompt_rtl"], "before": "role_models.resolve: cc_model/cc_effort, profile, roles"},
    {"file": "agent/graph/run.py", "fn": "node_interview (resolver.oracle)", "purposes": ["oracle"], "needs": "text",
     "prompts": ["graph/interview/oracle_system"], "before": "--oracle, --oracle-cc-model, else --model"},
    {"file": "agent/claude_code_arm/oracle.py", "fn": "cc_oracle", "purposes": ["oracle"], "needs": "text",
     "prompts": ["graph/interview/oracle_system"], "before": "--oracle-cc-model"},
    {"file": "agent/graph/run.py", "fn": "spec_test_gate", "purposes": ["spectest"], "needs": "text",
     "prompts": ["graph/spectest/role_system", "graph/spectest/triage_system"], "before": "--spectest-model, --spectest-effort (triage effort low)"},
    {"file": "agent/graph/run.py", "fn": "node_route_skills", "purposes": ["route"], "needs": "chat", "prompts": ["graph/router/router_system"],
     "before": "--router-model (OpenRouter; none = rules only)"},
    {"file": "agent/graph/document.py", "fn": "designer_llm", "purposes": ["doc"], "needs": "text", "prompts": ["graph/document/doc_system"],
     "before": "the rtl role's harness, model and effort"},
    {"file": "agent/__main__.py", "fn": "document_cmd", "purposes": ["doc"], "needs": "text", "prompts": ["graph/document/doc_system"],
     "before": "--cc-model/--cc-effort (Claude Code)"},
    {"file": "agent/graph/closure.py", "fn": "run_closure", "purposes": ["closure"], "needs": "chat",
     "prompts": ["graph/closure/system", "graph/closure/edit_prompt_1"], "before": "rt.client (the run's --model on OpenRouter)"},
    {"file": "agent/graph/closure_task.py", "fn": "main", "purposes": ["closure"], "needs": "chat", "prompts": ["graph/closure/system"],
     "before": "--model (OpenRouter)"},
    {"file": "agent/graph/ip_closure_task.py", "fn": "main", "purposes": ["closure"], "needs": "chat", "prompts": ["graph/closure/system"],
     "before": "--model (OpenRouter)"},
    {"file": "agent/graph/latency_loop.py", "fn": "latency_cmd", "purposes": ["latency"], "needs": "tools", "prompts": ["public: agent/graph/latency_loop.py"],
     "before": "--model (OpenRouter)"},
    {"file": "agent/graph/plan_arm.py", "fn": "main", "purposes": ["rtl"], "needs": "chat", "prompts": ["graph/plan_arm/system", "graph/plan_arm/write_core_1"],
     "before": "--model (OpenRouter)"},
    {"file": "flow/review/judge.py", "fn": "make_runner / call_claude", "purposes": ["review"], "needs": "text", "prompts": ["public: flow/review/judge.py SYSTEM"],
     "before": "--model/--effort (Claude Code, Sonnet by default)"},
    {"file": "flow/review/__init__.py", "fn": "review (improvement plan)", "purposes": ["review"], "needs": "text", "prompts": ["public: flow/review/improve.py"],
     "before": "--model/--effort (Claude Code)"},
    {"file": "project/cli.py", "fn": "_spec", "purposes": ["interpret", "oracle"], "needs": "chat", "prompts": ["public: project/phase0.py"],
     "before": "--model (OpenRouter, one client for both)"},
    {"file": "debug_core/request.py", "fn": "parse", "purposes": ["interpret"], "needs": "chat", "prompts": ["public: debug_core/request.py SYSTEM"],
     "before": "--model (OpenRouter)"},
    {"file": "debug_core/demo_t1.py", "fn": "main", "purposes": ["interpret"], "needs": "chat", "prompts": ["public: debug_core/request.py SYSTEM"],
     "before": "OpenRouterClient()"},
    {"file": "designs/b58a_trigger/host/nl_rule.py", "fn": "record", "purposes": ["interpret"], "needs": "chat", "prompts": ["public: nl_rule.py SYSTEM"],
     "before": "MODEL constant (OpenRouter)"},
    {"file": "tools/vhdl_translate.py", "fn": "main", "purposes": ["rtl"], "needs": "chat", "prompts": ["public: tools/vhdl_translate.py SYSTEM"],
     "before": "--model (OpenRouter)"},
    {"file": "results/36_skill_routing/measure.py", "fn": "main", "purposes": ["route"], "needs": "chat", "prompts": ["graph/router/router_system"],
     "before": "--router-model (OpenRouter)"},
    {"file": "tools/spectest_replay.py", "fn": "replay", "purposes": ["spectest"], "needs": "text", "prompts": ["graph/spectest/role_system"],
     "before": "--model (Claude Code)"},
    {"file": "designs/b100_rapidwright/agent_run/run_arm.py", "fn": "main", "purposes": ["rtl"], "needs": "agent", "prompts": ["public: run_arm.py SYSTEM"],
     "before": "the script's MODEL constant (Claude Code arm); a recorded experiment"},
    {"file": "flow/options/generate.py", "fn": "improve (agent improve)", "purposes": ["options"], "needs": "text",
     "prompts": ["graph/options/system", "graph/options/user", "graph/options/repair"], "before": "new in brief 104"},
    {"file": "formal/lean/tools/llm_prove.py", "fn": "main", "purposes": ["rtl"], "needs": "text", "prompts": ["public: formal/lean/tools/llm_prove.py SYSTEM"],
     "before": "new in brief 124 (a Lean proof writer; run on claude_code through an override of the rtl purpose)"},
    {"file": "flow/doc_crossread.py", "fn": "UsageMeter (the blind reader)", "purposes": ["doc_crossread"], "needs": "text",
     "prompts": ["graph/doc_crossread/system", "graph/doc_crossread/user", "graph/doc_crossread/repair"], "before": "new in brief 114"},
    {"file": "formal/lean/tools/prove.py", "fn": "main", "purposes": ["proof"], "needs": "text", "prompts": ["public: formal/lean/tools/prove.py SYSTEM"],
     "before": "new in brief 125 (the general proof driver; brief 124's llm_prove.py overrode the rtl purpose)"},
    {"file": "agent/models/resolver.py", "fn": "Resolver.probe (agent models check --probe)", "purposes": ["*"], "needs": "chat", "prompts": [],
     "before": "new in brief 108"},
]

#: purposes with no call site today, and why
RESERVED = {
    "embed": "the only embeddings are fastembed's local BAAI/bge-small-en-v1.5 in agent/core/skill_index.py (in-process, tied to the bank's stored "
             "vectors; a different embedder needs the bank's vectors rebuilt), so it is not routed through the resolver",
}

#: the files allowed to name a model client, a model host or the claude argv flags (everything else must go through the resolver)
RESOLVER_FILES = ("agent/models/",)
#: an in-process library, not an endpoint (see RESERVED["embed"])
LOCAL_EMBEDDER = ("agent/core/skill_index.py", "agent/skill_service/server.py")
