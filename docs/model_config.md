# One model configuration for every model call (brief 108)

Every model call of the agent, the flow and the tools names a **purpose** (why it calls a model). A table maps each purpose to an
**endpoint** (where), a **model** and **call options**. Moving a purpose to another model, another provider or a local server is a
change to that table, not to the code. Code: `agent/models/` (`config.py` the table and its guardrails, `resolver.py` the one object
every call goes through, `endpoints.py` the clients, `claude_cli.py` the one place that builds a `claude -p` argv,
`inventory.py` the list of call sites). Tests: `agent/tests/test_108_model_config.py`. Report: `reports/108_model_config_report.md`.

```
python -m agent models show [--json] [--models-file F] [--model-config JSON]   # the resolved table, and where each value came from
python -m agent models check [--probe]                                         # validate; --probe makes one minimal call per endpoint (spends tokens)
```

## Purposes

| purpose | what it is | call sites need | built-in (today's behaviour) |
|---|---|---|---|
| `interpret` | NL request and spec interpretation: the Clarifier role, the project spec drafter, the plain-English debug parser | agent, chat | OpenRouter, `openai/gpt-6-luna` |
| `oracle` | the user simulator in evals | text, chat | OpenRouter, `openai/gpt-6-luna` |
| `model` | the Modeller role (blind golden model) | agent | OpenRouter, `openai/gpt-6-luna` |
| `tests` | the Verifier role | agent | OpenRouter, `openai/gpt-6-luna` |
| `spectest` | the independent spec-only bench writer and its triage | text | `claude_code`, `claude-sonnet-5-5`, effort medium |
| `rtl` | the Designer role and the single-shot RTL writers | agent, chat | OpenRouter, `openai/gpt-6-luna` |
| `constraints` | the Designer in the constraints stage | agent | inherits `rtl` |
| `closure` | the closure loop's writer (reads STA, area and power reports) | chat | OpenRouter, `openai/gpt-6-luna` |
| `latency` | the latency loop's writer | tool calls (chat endpoint only) | OpenRouter, `openai/gpt-6-luna` |
| `review` | the review judge | text | `claude_code`, `claude-sonnet-5-5`, effort medium |
| `doc` | the DOC step (handover, README, AGENT.md) | text | inherits `rtl` |
| `route` | the cheap skill-section classifier | chat | off (no model) |
| `options` | the strategy generator of `agent improve` (brief 104): two to four ways to improve a loaded design, checked by code | text | Claude Code, `claude-sonnet-5-5`, effort medium (a `default:` does not move it; name it explicitly) |
| `proof` | the Lean proof writer (brief 125, `formal/lean/tools/prove.py`): writes a proof for a theorem statement a human approved, with `lake build` feedback; the kernel is the checker | text | Claude Code, `claude-sonnet-5-5`, effort medium, 1500 s timeout (a `default:` does not move it; name it explicitly) |
| `doc_crossread` | the blind document reader (brief 114): sees only a vendor-document excerpt, writes the facts code depends on with citations; code does the comparison, never a model | text, chat | Claude Code, `claude-sonnet-5-5`, effort medium (opt-in like `options`: a `default:` does not move it; name it explicitly) |
| `embed` | reserved: embeddings | chat | off; the only embedder is fastembed's local model in `agent/core/skill_index.py` (in-process, tied to the bank's stored vectors), not routed |

A key is a purpose, or `purpose@stage` for one stage of the machine (`rtl@timing-closure`; stage names as in `agent/graph/stages.py`).
Stage keys beat plain keys. The legacy role names are purposes: `clarify` is `interpret`; the Designer in the `constraints` stage is the
`constraints` purpose (the legacy key `rtl@constraints` still works). **Call sites needing "agent"** run a tool-using turn: the Claude Code
arm (a `claude_code` endpoint) or Deep Agents over a chat endpoint (the other kinds).

## Endpoint kinds

| kind | what | options it accepts | key |
|---|---|---|---|
| `claude_code` | the Max subscription, headless `claude -p` ("API-like mode"); no dollars are reported, only the plan's estimate | `effort`, `timeout_s` | the plan's token (`CLAUDE_CODE_OAUTH_TOKEN`, or the mode-600 file) |
| `anthropic_api` | the Messages API; reports tokens, not dollars (cost is counted at the per-call ceiling against the run's cap) | `temperature`, `max_tokens`, `stop`, `thinking_budget`, `timeout_s`, `retries` | `key_env` (default `ANTHROPIC_API_KEY`) |
| `openrouter` | OpenRouter chat completions, data collection denied, provider cost reported | `temperature`, `seed`, `max_tokens`, `stop`, `effort`, `timeout_s`, `retries` | `key_env` (default `OPENROUTER_API_KEY`, or the owner's mode-600 file) |
| `openai_compatible` | any base URL: vLLM, a local model, a specialist fine-tune (brief 107's hook). OpenRouter's extra fields are sent only when the host is `openrouter.ai` | as `openrouter` | `key_env`; none needed on `localhost` |
| `replay` | recorded replies in order (`path:` of a fixture) | none | none |

The endpoint table has four built-in names (`openrouter`, `claude_code`, `anthropic_api`, `replay`); add your own under `endpoints:`.

## The file

`~/.config/fpga_design_agent/models.yaml` (the user file; `FDA_MODELS_FILE` overrides the path) and the project file (`models.yaml` next
to the spec, or `--models-file`) use one format. Both are optional.

```yaml
version: 1
endpoints:
  vllm:
    kind: openai_compatible
    base_url: http://localhost:8000/v1
    note: "vLLM 0.x, batch-invariant, greedy"        # free text; recorded, never interpreted; one line, 240 characters at most
  spark:                                             # user file only:
    kind: openai_compatible
    base_url: http://spark.lan:8000/v1
    key_env: SPARK_KEY                               # the NAME of the variable; never the key
    host_class: work_hardware                        # refused for live runs; batch replay only
work_hardware_hosts: [other.lan]                     # user file only
default: {endpoint: claude_code, model: claude-haiku-5-5}   # every purpose the kind can serve; skips the opt-in ones and `latency`
purposes:
  rtl: {endpoint: vllm, model: my-fine-tune, options: {temperature: 0, seed: 7}}
  rtl@timing-closure: {endpoint: claude_code, model: claude-sonnet-5-5}
```

`--model-config '<JSON in the same format>'` is the command-line layer.

## Layers

Lowest to highest: **built in**, **command defaults** (a few commands), **user file**, **project file**, **command line**. A layer
changes only the fields it names; `options` merge key by key. Naming a new `endpoint` in a layer drops the options that lower layers
set explicitly (they belonged to the old endpoint). A stage key (`rtl@stage`) applies on top of the plain key of every layer.

**The flags that existed before are aliases into the same table**, in the command-line layer, and keep working:
`--harness claude_code --cc-model M --cc-effort E` sets `interpret`, `model`, `tests`, `rtl`; `--model M` sets those on OpenRouter when the
harness is not `claude_code`, and the `oracle`, `closure` and `latency` purposes always; `--oracle claude_code --oracle-cc-model M`;
`--spectest-model`, `--spectest-effort`; `--router-model` (turns `route` on); `--profile` and `--roles`. **A flag overrides the user and
project files only when it is given on the command line** (or, in the library, differs from the `Config` default): a flag left at its
default does not hide the file.

## What you could guess wrong

- **An option an endpoint does not support is an error when the table is built**, naming the option, the layer it came from and what the
  kind supports. The one exception is the built-in soft defaults (`temperature 0.2`, `timeout_s 180`, `retries 1` on chat kinds, `effort
  medium` on `claude_code`): they are dropped when the kind cannot take them, so switching a purpose from one kind to another is a one-line change.
- **`effort: null` means unset** (the CLI default), not "medium".
- **`default:` skips** the opt-in purposes (`route`, `embed` stay off; `options` and `doc_crossread` keep their own entries, Claude Code on the plan) and any purpose the kind cannot serve (`latency` needs
  tool calls through a chat endpoint). Naming such a purpose explicitly on `claude_code` is an error at load.
- **`doc` and `constraints` inherit `rtl`** until a layer sets them. A `default:` sets them explicitly.
- **`anthropic_api` and `claude_code` calls are counted differently:** the run's USD cap counts provider-reported dollars (OpenRouter); an
  `anthropic_api` call reports none, so each is charged at the per-call ceiling (0.05 USD); `claude_code` calls are counted in turns and tokens,
  with the plan's estimate beside them.
- **A resume rebuilds the table from the run's `config.json`** and refuses if the table's hash differs from the run's (`--allow-model-change`
  overrides it); the user file is part of the table, so editing it between a run and its resume is a change.
- **The review benchmark scripts pin their model and effort as aliases**; if the user file moves `review` off `claude_code`, a pinned scored run
  is no longer the pinned CLI. Scored evals use `--model-config` on the command line, never the user file.
- **`--replay`** serves every chat-style call from the fixture in order, whatever the table says; `claude_code` purposes still call the CLI.
- **Embeddings are not routed** (see `embed` above).

## Guardrails (code, applied to the final table whatever layer a value came from)

- Never Fable or Opus through OpenRouter, through an `openai_compatible` endpoint on the OpenRouter host, or through the Anthropic API; never
  an Anthropic model (`anthropic/...`) through OpenRouter.
- `claude_code` runs `claude-*` models only. **Fable needs the owner's `--allow-fable` flag**, which no file can carry (a file with `allow_fable`
  is an error).
- Keys are named by environment variable (`key_env`, upper case). A key-like value anywhere in a file is an error; a field called `api_key`,
  `token`, `secret` or `password` is an error. A record that would contain a key-like string, or the value of a configured key variable,
  is refused.
- An endpoint marked work hardware (`host_class: work_hardware`, or its host listed in `work_hardware_hosts`) is refused for live calls and
  allowed for batch replay. **A project file cannot set `host_class` or `work_hardware_hosts`, cannot unmark an endpoint (it can re-point one;
  the mark stays by name and by host), and cannot grant Fable.**
- Notes are one line; prompt text never belongs in a configuration (prompts stay in the private knowledge repository, brief 99).

## The run record

`config.json` holds the file layers (path and SHA-256), the fully resolved table (endpoint, kind, model, options, deployment note, per
purpose and stage) and its hash. `model_calls.jsonl` has one row per chat-style call: purpose, stage, endpoint, kind, model, the hash of the
resolved entry and of the table, tokens, provider-reported cost, seconds. `summary.json` carries `model_table_hash`. No key, prompt or
reply is in any of them. Calls on a `claude_code` endpoint are also in the existing `claude_code_calls.jsonl` and `role_usage.jsonl`.

## The gate

`test_gate_no_model_client_or_claude_argv_outside_the_resolver` scans every tracked and untracked Python file outside `agent/models/` and
the tests and fails on: constructing a model client, importing an LLM SDK, looking up the `claude` binary, a `claude -p` argv, or any of the
`claude` isolation flags. A new call has to go through `Resolver` (`chat`, `text`, `oracle`, or `agent_spec` for a role) and be added to
`agent/models/inventory.py`, which another test checks against the files and the purpose list.
