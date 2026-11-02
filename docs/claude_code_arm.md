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

## First real runs (2026-11-02)

- Two real-stream findings fixed in `parse_stream`: one API message arrives as several `assistant` events with the same id and usage (counted once now), and the streamed output-token counts are partial, so the `result` event's usage is the run total. Test: `test_real_recorded_stream_is_parsed_once_per_message` (redacted recorded stream in `agent/tests/fixtures/cc_real_stream_haiku_clarify.jsonl`).
- The run summary now names the Claude Code model (the luna model is the spec oracle only) and the plan estimate.
- Review pages are written by the graph (`node_review`), not by an MCP tool, for both harnesses; the role jail refuses sub-agent writes to `build/review`. With `--review on` the graph pauses with a LangGraph interrupt and the reviewer answers with `python -m agent resume`; Claude Code never asks.
- Init event of both runs: tools = our three MCP tools, MCP server `fda` connected, no skills or slash commands, `apiKeySource: none`. It also lists two built-in plugins (`cc-plugin-agents-md`, `cc-plugin-plugin-authoring`, source `builtin`) and Claude Code's built-in sub-agent names; none is a user config.
