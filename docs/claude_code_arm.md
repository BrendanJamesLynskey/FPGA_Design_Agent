# The Claude Code arm (brief 05c, F2 part 3)

The Deep Agents agent (05b) and this arm share one graph: stages, gates, interview, review pages, rewind, limits.
Only the call that runs a sub-agent turn differs: `python -m agent run <spec.md> --harness claude_code
--cc-model claude-haiku-5-5 [--cc-effort medium]` runs each turn as one headless `claude -p` call.
Anthropic models only, on a Claude subscription, through the documented CLI (not the Agent SDK, never OpenRouter).
Code: `agent/claude_code_arm/arm.py`.

## What one turn looks like

```
claude -p <user message> --output-format stream-json --verbose --system-prompt <stage prompt> --tools ""
  --mcp-config <our server only> --strict-mcp-config --allowedTools mcp__fda__<tool> ...
  --permission-mode dontAsk --setting-sources "" --disable-slash-commands --no-session-persistence
  --model <id> --effort <level> --max-turns <stage turn limit>
```

with an empty temporary `HOME` and `CLAUDE_CONFIG_DIR`, a temporary working directory outside the repo (so no CLAUDE.md
is found by walking up), only `PATH`, `LANG` and `CLAUDE_CODE_OAUTH_TOKEN` in the environment, and the wall cap as the
subprocess timeout. The flags are explained, with the reference they come from, in the module docstring.

- **Prompt.** `--system-prompt` replaces Claude Code's default; the text is the one Deep Agents gets
  (`run.subagent_plan`), including the model API contract.
- **Tools.** Built-in tools are all off (`--tools ""`): Bash, file tools, web and sub-agents are not needed, because
  the stage machine's tools (lint, simulate, build, gates, docs, files) are our MCP server's, which carries the
  role jail and the audit log. The server runs per turn with `--role`, `--stage` and `--tools`, so a sub-agent sees
  exactly the tools Deep Agents gives it for that stage (plus `read_file`/`write_file`/`list_files` for what Deep Agents
  has built in). `program`, `bringup` and `stage_note` are never exposed.
- **Trace.** The stream is converted to the shared trace format (`runs/<id>/trace.jsonl`, harness `claude_code`);
  `cost_usd` is `"unreported"` (the plan has no per-call cost) and Claude Code's own figure is kept as
  `plan_cost_estimate_usd` in `claude_code_calls.jsonl`, with the CLI version, requested and served model ids, and the
  init event (tools, MCP servers, skills: evidence of what loaded).
- **Review and rewind.** Unchanged, in the graph. With `--review on` the graph pauses (a LangGraph interrupt) and the
  reviewer answers with `python -m agent resume`; Claude Code itself never asks a question (headless, `dontAsk`).
  Off, every review is `auto`. The stage 9 hardware pause always applies.
- **Login.** `claude setup-token` (documented, needs a subscription) prints a long-lived token. Save it as
  `CLAUDE_CODE_OAUTH_TOKEN=...` in `~/.config/fpga_design_agent/claude_code_oauth.env` (mode 600) or export it.
  `--bare` is not used: it ignores OAuth.

## Residual differences from the Deep Agents run

Context compaction (Claude Code compacts on its own; no switch to turn it off); effort defaults and extended thinking
(Claude Code's `--effort`, none in Deep Agents); no temperature control (Deep Agents uses 0.2); tool-call formatting
(Anthropic native tool use vs OpenAI-style tool calls); no `edit_file`, `grep` or `glob` (Deep Agents built-ins); turns
are counted by Claude Code, not by us; the system-prompt snapshot feature records the prompt once per conversation.
The equivalence test (`agent/tests/test_claude_code_arm.py`) fixes the rest: same prompt, same core tools, same turn
limit, no built-ins, no other MCP server.
