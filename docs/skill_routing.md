# Skill routing and retrieval (brief 36)

Off by default. `python -m agent run ... --skill-routing router` turns it on; `--router-model <openrouter id>` adds the
cheap classifier, `--router-k` sets the shortlist length (8). With it off, the graph, the prompts, the per-role tool lists
and `load_skill(sections)` are what they were at `eval-1` (tests in `agent/tests/test_36_skill_routing.py`; the golden
request change is below).

## What changes when it is on

| Piece | Where | What it does |
|---|---|---|
| Router node | `agent/graph/router.py`, `node_route_skills` in `agent/graph/run.py` | Runs before every stage's work. Rules pick bank sections: the spec's words (`SPEC_RULES`) and the stage's areas (`STAGE_SECTIONS`); the part picks the family layers (the bank's `select --part`). An optional cheap model adds section ids (validated against `SECTIONS.yaml`; anything else is ignored). The skill index ranks the board's and part's skills; the top k go to every role that may load skills, as names, sections and one-line descriptions, never bodies. Written to `runs/<id>/skill_routing.jsonl`. |
| `skill_index(query, k)` | `agent/core/tools.py` | Ranked names and descriptions for any query. |
| `load_skill(name=...)` | same | One body. `load_skill(sections)` still works (old runs replay); with routing on, its 6-skill cap keeps the most relevant skills for the task text instead of the first six in unit-name order, and the result lists the ones left out. |
| `skill_excerpt(name, heading)` | same | One section of one skill (exact heading or unique prefix; a miss lists the headings). |
| Context hygiene | `router.stage_notes`, `State.skill_notes` | Bodies are never kept in the graph state (a body lives only inside the role turn that loaded it). After each stage the audit log's loads become `{stage, skill, heading}` citations; the next shortlist lists them as already used. |

The optional "KB sub-agent that returns cited facts" was not built.

## The index

`agent/core/skill_index.py`: BM25 over each skill's name, description, sections, headings and the start of its body,
fused by reciprocal rank (k = 60) with cosine similarity against `BAAI/bge-small-en-v1.5` vectors (MIT; through fastembed,
Apache-2.0, an optional dependency: `pip install .[retrieval]`). A section the caller names counts as half a first-place
vote. The vectors live in the private bank (`indexes/skill_vectors.*`, hashes in `knowledge/PACKS.md`), built with
`python -m agent.core.skill_index build --bank <bank>` on the owner's PC only (never a work machine; the builder refuses
when `FDA_WORK_MACHINE=1`). Each skill's SHA-256 is in the manifest: a changed skill is searched by BM25 alone until the
vectors are rebuilt. Without fastembed or without vectors (CI) the index is BM25 only and says so (`mode`).

Three ways to run it: in process (BM25, or hybrid when fastembed is installed); or the container,
`agent/skill_service/` (stdlib HTTP, the same code, model baked in at build time, bank mounted read-only):

```bash
docker build -f agent/skill_service/Dockerfile -t fda-skill-index:1 .
docker run --rm -p 127.0.0.1:8088:8088 --read-only --tmpfs /tmp --cap-drop ALL -v <bank>:/bank:ro fda-skill-index:1
FDA_SKILL_INDEX_URL=http://127.0.0.1:8088 python -m agent run ... --skill-routing router
```

`agent/skill_service/k8s/` has a kind cluster file and a Deployment and Service (non-root, read-only root file system, no
service-account token). If the service does not answer, the agent falls back to the in-process index.

## Measured (development split only)

[results/36_skill_routing](../results/36_skill_routing/): labels for 12 dev tasks from their public specs (`labels.yaml`,
committed before measuring), the pre-registration (`PREREG.md`), recall@k and MRR (`retrieval.md`), and the small end-to-end
run (`e2e.md`). In short: no ranked arm beat today's section-filtered `load_skill` on recall; the pre-registered router design
ranked worst, and a second design (the default now, measured post hoc on the same tasks) came close. The shortlist is about
1,750 characters, against one `load_skill(sections)` call that returns 20,000 (the registry's output clip; the six bodies
average 23,900).

## Golden requests

The registry changed (two tools, and `load_skill` gained `name`, so `sections` is no longer required). Against `eval-1`
(132b784) only the `tool_registry` hash differs; every prompt, plan, per-role tool list, Claude Code argv and MCP argument is
unchanged with routing off. `agent/tests/fixtures/b36_request_golden.json` is the new golden; the eval-1 file is kept
unedited, and the test checks that exactly the listed hashes differ from it. Eval-1's recorded hashes therefore no longer
cover a whole run (a role sees the new `load_skill` schema), and the brief-34 baseline re-records against the new file.
