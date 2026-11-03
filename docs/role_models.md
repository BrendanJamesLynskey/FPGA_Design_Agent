# Per-role model routing (brief 05f, F2 part 6)

Which harness, model and effort runs each sub-agent role. Code: `agent/graph/role_models.py`; dispatch and accounting in
`agent/graph/run.py` (`run_subagent`).

## Roles, orchestration and the oracle

- Roles: `clarify`, `model` (blind golden model), `tests` (test writer, including the stage-9 bring-up files) and `rtl`
  (RTL writer and every repair it owns).
- The **stage machine is plain code** (the "orchestration"): which role runs when, the gates, routing of failures to an
  owner role, review pages, rewind. No model drives it, so there is no orchestrator role to route.
- The interview **oracle** (user simulator) is not a role. It always runs on `--model` (luna by default), whatever the
  profile, so runs stay comparable with every earlier F2 run.

## Profiles

```
python -m agent run <spec.md> --profile single|cvdp [--roles '<json>']
```

| Profile | Map |
|---|---|
| `single` (default) | One harness and model for every role: today's behaviour (`--harness`, `--model`, `--cc-model`, `--cc-effort`). Existing runs and replays are unchanged. |
| `cvdp` | `rtl`: Claude Code + `claude-opus-5-5`, CLI-default effort (the `--effort` flag is omitted); `model`, `tests`, `clarify`: Claude Code + `claude-sonnet-5-5`, effort medium. The blind model is a different model from the RTL writer on purpose: CVDP found same-model self-tests share the writer's misreadings. Claude Code runs the lean profile the arm already uses (our role prompt as `--system-prompt`, only our MCP tools, no settings, no slash commands). |

Mixed harnesses work in one run: the role's harness is chosen at dispatch, so a luna (Deep Agents, OpenRouter) role can sit
beside Claude Code roles. A Deep Agents role on a model other than `--model` gets its own OpenRouter client; models
containing `anthropic/`, `fable` or `opus` are refused through OpenRouter (owner rule). Opus and Fable run only through
Claude Code on the plan.

## Per-stage overrides

The routing key is the role, or `role@stage` for one stage of the machine (stage names: `clarify`,
`board-and-device-planning`, `rtl-design-creation`, `constraints`, `synthesis`, `implementation`, `timing-closure`,
`power-closure`, `drc-closure`, `configuration-and-debug`). Use it where another model may read STA, CDC or methodology
reports better than the same role elsewhere (stages 6 to 8), or constraints (stage 3):

```
--roles '{"rtl@timing-closure": {"model": "claude-fable-5-1", "effort": "high"},
          "rtl@constraints": {"harness": "deepagents", "model": "openai/gpt-6-luna"}}'
```

Each layer is partial (only the keys it names change). Precedence, lowest to highest: single base, profile `role`,
explicit `role`, profile `role@stage`, explicit `role@stage`. The profile `cvdp` sets no stage override. To make one
permanent, add the `role@stage` key to a profile in `PROFILES`. `config.json` stores `profile`, `roles` (the explicit
overrides, verbatim), and the resolved `role_models`; `resume` rebuilds the map from `profile` and `roles` (an older
`config.json` resumes as `single`).

## Accounting and records

- `runs/<id>/role_usage.jsonl`: one row per sub-agent call: stage, role, harness, model actually requested, effort,
  whether a stage override applied, turns, tokens, wall time, provider-reported USD (Deep Agents) or Claude Code's plan
  estimate. `summary.json` adds `per_role`, `per_stage`, `role_models`, `stage_overrides`, `profile` and `oracle_model`.
- Review pages carry a "Models by role" table (with that stage's use); the review index carries the map; `BUILD_NOTE.md`
  starts with it.
- `summary.json` `knowledge_use`: per role and stage, the calls to `load_skill`, `search_docs` and `board_constraints`,
  and for `load_skill` the section names and skill files returned (from `build/audit.jsonl`, whose records now carry
  the role), so you can see whether the RTL writer uses the family and device layers.

## What this deliberately does not copy from CVDP

CVDP's nulls (see `cvdp_rtl_recommendation.md`): no lessons memory, no self-check or verify-before-submit loop, no spec
vectors, no knowledge-pack injection into prompts, no skills beyond what the agent already loads by tool. None is added
here.

**Device know-how stays on.** The CVDP null was for generic RTL problems. The knowledge tools (`load_skill`,
`search_docs`, `board_constraints`) and the family (`artix7`) and device (`xc7a100tcsg324-1`) layers behind them are
unchanged for every role and profile (tested: the tool lists and prompts are identical under `single` and `cvdp`).
Primitives, MMCM/PLL configuration, LUT6-aware design and DSP48E1 inference matter to our Vivado gates, which CVDP never
measured.
