# Brief 36: pre-registration (written 2026-11-10, before any measurement)

Development split only. Labels: `labels.yaml` (12 tasks, from public specs, committed before this file's measurements).
Bank: FPGA_Design_Agent_Knowledge a598197 plus the brief-36 vectors (`indexes/skill_vectors.*`, BAAI/bge-small-en-v1.5,
computed on the owner's PC). Board nexys_a7_100t, part xc7a100tcsg324-1 (157 skills in the catalogue).

## 1. Retrieval (no model calls except arm R2; deterministic otherwise)

One ranked list of skill names per task and arm. Metrics over the 12 tasks: mean recall@3, @6, @10 (labelled skills in the
top k / labelled skills) and MRR (1 / rank of the first labelled skill, 0 if none in the top 20).

| Arm | What it is |
|---|---|
| T0 today | `load_skill(sections)` as on main: `LocalBank.skills(primary_only=True)` for the sections, procedures fallback, cut at 6 in unit/section/name order. Sections: the spec-word rule sections of `agent/graph/router.py` (`rule_sections(spec, stage=None)`), first 4 (the tool's `maxItems`), standing in for the sections a role would ask for. Lists stop at 6, so recall@10 = recall@6. |
| T1 today, ranked | the same candidates (all of them, not cut), ranked by the skill index's hybrid score on the task text; cut at 6 (the in-cap fix the run order asks for), and uncut for @10. |
| R1 router, rules | `router.shortlist(stage=2)`: stage-2 areas + spec-word sections as votes (half a first-place vote each, `SECTION_VOTE = 0.5`, fixed before measuring), hybrid index, k = 10. |
| R2 router, rules + model | R1 plus the cheap-model classifier's sections (`openai/gpt-6-luna`, one call per task, `data_collection: deny`). |
| I-bm25 / I-vec / I-hybrid | `skill_index(query = spec text, k)` with BM25 only, vectors only, and the fusion. |

Comparisons stated in advance: T1 against T0 (does ranking inside the cap recover lost skills); R1 and I-hybrid against
T0; I-hybrid against I-bm25 (do embeddings add anything). With 12 tasks no difference is called significant; per-task
rows are given and nulls are stated first.

## 2. Context (characters, static)

Per task, the characters a stage-2 role receives from the knowledge tools: T0 = the six bodies of one `load_skill(sections)`
call; new path = the shortlist block plus the bodies of the shortlisted skills that are labelled (an upper bound on what a
role that loads only what it needs reads; the model may load more or fewer). Characters, not tokens; token counts come only
from the end-to-end runs' provider-reported usage.

## 3. End to end (small)

- Tasks: t1_debounce_bank, t2_spi_master_modes, c11_nco_mixer (development split). 3 runs ("seeds" 1-3) per task and arm.
- Arms: `--skill-routing off` (today) against `--skill-routing router` (shortlist + new tools, ranked `load_skill`; rules
  only, no classifier model, `--router-k 8`).
- Harness deepagents, every role on `openai/gpt-6-luna` (OpenRouter, `data_collection: deny`), interview off, review off,
  `--stop-after 2`, `--verif-level V1`, `--max-usd 0.60` per run. No Vivado (stage 2 ends before synthesis).
- Order: paired and interleaved (task, seed, off then router), one run at a time, under one heavy slot.
- Score: pass = every test of the task's hidden bench passes (`benchmark/tools/run_task.py <task> --rtl <run>/rtl`),
  scored after the run, one at a time; also whether stage 2's gates passed. No LLM produces a score.
- Tokens and cost: provider-reported only, per stage and run, from each run's `summary.json`.
- Spend cap for the brief: USD 5.00 by key usage; stop and report a partial table if reached. Expected: no difference is
  detectable with 9 pairs; the result is a smoke test of the path, and brief 42 arm A1 is the real comparison.
- Claude Code is not used, so the CLI pin of the eval checklist does not apply; the venv, Icarus and the sim image are the
  ones on the machine on 2026-11-10 and are recorded in the results.

## Amendment (2026-11-10, after section 1 was measured, before any end-to-end run)

The pre-registered router (R1, `shortlist(version=1)`) ranked worst (recall@6 0.100 against T0's 0.394): the stage-2
areas voted the generic procedures and coding skills above the task's own. A second design (`version=2`, arm R3* in
`retrieval.md`: the spec's sections first in relevance order, then the stage's areas, procedures left out) was written
and measured post hoc on the same 12 tasks (recall@6 0.361). The end-to-end router arm uses `version=2` (the default in
`agent/graph/router.py`); everything else in section 3 is unchanged.
