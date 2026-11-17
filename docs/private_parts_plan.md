# What makes the agent valuable, and moving it into private repositories over time (brief 94)

Status 2026-11-17 (brief 99): stage 0 of the prompts move is done (the loader `agent/core/prompts.py`, its tests, the pin file, the CI fetch step, the manifest builder in the private repository); **no prompt text has moved yet**, waiting for the CI read token (see below). Nothing here names a secret. The repository is
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

## Prompts move: design and status (brief 99, 2026-11-17)

**Loader.** `agent.core.prompts.load(name)` returns the text of `prompts/<name>.txt` from the private knowledge repository,
byte for byte. The directory is `$FDA_PROMPTS_DIR`, else `<knowledge checkout>/prompts` (the checkout the knowledge packs use).
The private repository's `prompts/MANIFEST.json` lists each name, file, SHA-256 and size (`tools/build_prompt_manifest.py`
writes and checks it). This repository's `agent/core/prompts_pin.json` records the private commit and the manifest's SHA-256
only; `load` refuses a manifest that is not the pinned one and a file that is not the manifest's. `FDA_PROMPTS_UNPINNED=1`
skips only the pin comparison (development); `provenance()` reports whether the pin was enforced, for run records.
There is **no committed fallback**: a missing or altered prompt raises `PromptUnavailable` and the run stops. (The first
plan said "fall back while the gate is unarmed"; the gate is armed now, and a fallback would mean prompt text stays public.)

**CI.** Secret `FDA_KB_READ_TOKEN`: a fine-grained, read-only (Contents: read) token for `FPGA_Design_Agent_Knowledge` only.
The `python` job fetches `prompts/` of the pinned commit (`actions/checkout`, sparse) when the pin is set. A fork pull request
has no secrets: the step prints a notice, sets `FDA_PROMPTS_SKIP_NOTICE=1`, and only the test that needs prompts skips. Any other
run (pull request from this repository, push, schedule) **fails** if the pin is set and the secret is missing. While nothing is
pinned the step is a no-op.

**Slices, smallest first.** (1) `interview.py`, (2) `review.py`, (3) `roles.py`, (4) `closure_playbook.py`, (5) prompt strings
in `run.py` (and `plan_arm.py`, `closure.py`, `spectest.py`). Each slice: text to `prompts/` in the private repository (manifest
rebuilt), the public module calls `load(...)`, the pin updated, snapshot tests compare the loaded text's SHA-256 against the
hash recorded before the move (so a prompt change is still caught without the text being in the repository), the tool-schema
fixture and a before and after prompt hash match.

Review (one Sonnet pass, 2026-11-17) found and this PR fixed: a partial pin failed open, the read token persisted in the `_kb` checkout, and malformed manifest entries raised raw errors. **Open for slice work:** a shared skip marker for tests that import prompt-using modules on forks, and tests must compare prompt hashes, never text (a failing `assert text == ...` would print it into a public log).

| Slice | State |
| --- | --- |
| Stage 0: loader, tests, pin, CI step, manifest builder | done (2026-11-17) |
| 1 interview.py, 2 review.py, 3 roles.py, 4 closure playbook, 5 run.py and the rest | not started: waiting for `FDA_KB_READ_TOKEN` |

## Records keep hashes, not prompts (brief 99, step 1, 2026-11-17)

A moved prompt must not reappear in a run record. The writers that stored rendered prompt text now store its SHA-256, length and the prompt
pin instead (`agent.core.prompts.record`): the Claude Code arm writes `claude_code/<tag>.prompt.json` where it wrote `<tag>.system.txt` and
`<tag>.user.txt`, and the closure task driver writes `task.json` where it wrote `task.txt`. Other records (summaries, review pages, the
interview record, `doc_calls.jsonl`) never held the rendered prompt; a scripted T1 episode proves it
(`test_a_whole_episode_leaves_no_prompt_text_in_its_records`: no 12-word window of any prompt in any file the run wrote).
`tools/prompts/leak_scan.py` is the same check over tracked files. It uses 12-word windows: the harness's own questions and gate messages are
recorded by design and a model's replies reuse the prompts' vocabulary, so 8 words matched in about 100 files that held no dump. Records written
before this change still carry prompt text; step 2 moves them out.
