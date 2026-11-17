# What makes the agent valuable, and moving it into private repositories over time (brief 94)

Status 2026-11-16: a plan; one safe move is listed but not made. Nothing here names a secret. The repository is
all-rights-reserved ([LICENSE](../LICENSE)) and gated by an access key ([agent/access/README.md](../agent/access/README.md)),
but a public repository's source can still be read, so the valuable parts below are ranked for moving out.

How CI fetches a private repository: a token secret with read access (a fine-grained token on one repository), used by
`actions/checkout` with `repository:` and `token:`. **Fork pull requests do not receive secrets**, so a job that needs a
private part cannot run on a fork; it has to skip with a notice. GitHub's free tier gives private repositories 2,000 CI
minutes a month, which this project's CI uses up in days, so CI stays in a public repository and private parts are
fetched into it, not the other way round.

| Part | Size, where | Imported by | CI needs it | Cost of moving | Order |
| --- | --- | --- | --- | --- | --- |
| Knowledge bank (skills, claims, family matrix, vendor summaries) | about 55 MB, 1,400+ files, `FPGA_Design_Agent_Knowledge` (already private) | `agent/core/bank.py`; the public repo names packs by SHA-256 only | no: tests use fixtures | done | 0 |
| Held-out benchmark material | `benchmark_private/` (4 MB, 629 files) and `eval1/` in the KB repo (already private) | scoring tools only | no | done; the freeze and leak-guard rules govern it, unchanged | 0 |
| Run records and the improvement ledger | `results/` is 61 MB in the public repo; the ledger and journal live in the planner's private folder | site builds (numbers), doccheck | yes for numbers shown on the site | moderate: the site builds read `results/`; move only raw run records (`runs/`, agent transcripts), keep summaries | 3 |
| Prompts and role configurations | about 140 KB of Python strings: `agent/graph/roles.py`, `closure_playbook.py` (25 KB), `document.py` (68 KB, mostly code), `review.py`, `interview.py`, prompt strings inside `run.py` (122 KB), `plan_arm.py`, `closure.py`, `spectest.py` | the whole agent graph; tests assert prompt text and `agent/tests/fixtures/tool_schemas.json` | tests do | high: prompts are woven into code and checked by snapshot tests (golden rule); needs a loader with the current text as fallback | 1 (the first real move) |
| Skill and procedure text the agent loads | inside the KB (private) | `load_skill` | no | done | 0 |
| Benchmark tasks and their hidden tests (development split) | `benchmark/tasks`, `pool`, `course/tasks`, `v2`: about 5.7 MB | CI (task tests) and the site's problem pages | yes (CI runs them) and the site shows them | high and costly: CI would need the token, forks would lose these jobs, and the site publishes them by design | last, or never for the displayed ones |
| Improvement ledger fixes (the code and prompt changes themselves) | spread through the repo | the agent | yes | not separable from the code | follows prompts |

## Suggested order

1. **Prompts and role text** first, as data files in the private KB repo, loaded by a small loader
   (`agent.core.prompts.load(name)`) that falls back to the committed text **only while the gate is unarmed**. Once
   armed, a missing private prompt is a refusal. Needs: the CI token secret, snapshot tests re-pointed at the loader,
   and a fork-PR skip notice. Not done in this brief: the strings sit inside 20+ modules guarded by snapshot tests, so the
   move deserves its own brief and its own before and after.
2. Raw run records and transcripts to a private results repo; keep committed summaries (`results.md`) so site numbers
   stay traceable ("every number from a committed file" stays true).
3. Review the development benchmark split once the site decides what it publishes.

Do not move held-out material in this programme step: the freeze and leak-guard rules govern it.
