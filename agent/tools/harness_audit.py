"""H0 harness audit (brief 42 addendum): what the Deep Agents role agents are built with, no model spend.

Builds ``create_deep_agent`` as ``agent/graph/run.py:_run_subagent`` does, over a stub client that records the request,
and prints the tools offered, the system prompt size, and the middleware stack handed to ``langchain.agents.create_agent``.

    PYTHONPATH=. python agent/tools/harness_audit.py

Correction to the first audit (2026-11-11): graph nodes do not list ``SummarizationMiddleware`` or
``FilesystemMiddleware`` because they only wrap model and tool calls. The middleware list below is read from the
``create_agent`` call, which is the real stack.
"""
import json

import deepagents.graph as dg
from deepagents import HarnessProfile, create_deep_agent, register_harness_profile
from deepagents.profiles.harness.harness_profiles import GeneralPurposeSubagentProfile

from agent.graph.llm import chat_model

seen: dict = {}
stack: dict = {}
_orig = dg.create_agent


def _spy(*a, **k):
    stack["middleware"] = [type(m).__name__ for m in k.get("middleware", [])]
    return _orig(*a, **k)


dg.create_agent = _spy


class R:
    text = "done"
    tool_calls: list = []
    prompt_tokens = 1
    completion_tokens = 1
    cost = 0.0


class Client:
    def __call__(self, msgs, tools=None):
        seen["tools"] = sorted(t["function"]["name"] for t in (tools or []))
        seen["system_chars"] = sum(len(m["content"]) for m in msgs if m["role"] == "system")
        seen["system_head"] = [m["content"][:4000] for m in msgs if m["role"] == "system"][0]
        return R()


class Meter:
    run = {"turns": 0}

    def check(self):
        pass

    def add(self, r):
        self.run["turns"] += 1


if __name__ == "__main__":
    for label, reg in (("without_fda_profile", False), ("with_fda_profile", True)):
        if reg:
            register_harness_profile("fda", HarnessProfile(general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)))
        seen.clear()
        m = chat_model(Client(), Meter(), [])
        a = create_deep_agent(model=m, tools=[], system_prompt="ROLE PROMPT")
        a.invoke({"messages": [{"role": "user", "content": "hi"}]})
        print(label, json.dumps({"tools": seen["tools"], "system_chars": seen["system_chars"], "middleware": stack["middleware"]}))
    print("MODEL PROFILE:", m.profile, "(None: summarisation trigger is the fixed 170,000 tokens, keep 6 messages)")
    print("SYSTEM PROMPT HEAD:\n", seen["system_head"][:1500])
