# Brief 217 report: evidence-keyed repair memory, the R1 fix, and the check suite over MCP

Executor: Sonnet 5.5, 2026-11-26 (stamped from `date`: started 20:55 GMT, finished about 22:30 GMT). Branch `b217-repair-memory` (PR #359 in FPGA_Design_Agent), knowledge-bank branch `b217-repair-records` (PR #109). Records: `results/217_repair_memory/` (README, prereg.md, replay files, item0_run3_digest.txt). Weekly usage at start 73%, at the end 75%; no agent run was made.

## Done
Nulls first: **no live effect is measured.** The live A/B was skipped by the pre-registered rule (replay ceiling below the smallest detectable effect) and the one demonstration run was not made (heavy-slot queue). What exists is the mechanism, its tests and a replay.

0. **R1 first-failing-check fix (item 0).** Cause of "Simulator shut down prematurely" in 213's run 3: the bench started the clock inside its first test only; cocotb cancels a test's tasks when it ends, so test 2 waited for an edge that never came and the simulator ended 20 ns in. Found by checking out the run's per-gate snapshots (`snap.git`): the RTL was identical at the failing and the passing gate, the bench differed (clock restarted per test). Not a bug in the snapshot hook for assertion failures (those are captured: a seeded file error is caught with its bench line). The hook had nothing to say for a simulator stop. Now (`flow/model_record.py`, `flow/divergence.py`, `agent/graph/feedback.py`): the digest says the simulator ended and no assertion failed, when the test began and ended, whether the clock had a rising edge after the test began (the sampler is restarted for each test), any `$finish`/`$fatal`/`$stop` in the RTL, and WARNING-or-above log lines during the test. The ledger line and the evidence key carry the fact (`no-clock-edge`), not the cocotb phrase. Shown on run 3 (`item0_run3_digest.txt`, state 58a7243 of agent run 20261126-045447-291e) and on the seeded fixture `agent/tests/data/b213_counter/bad_clock`. Cost: the sampler adds simulation time only in the diagnostic re-run, as before.
1. **Repair records.** `agent/graph/repair_memory.py`: `step()` is called at every stage-2 gate evaluation under arm `R4`; a key that failed at the previous evaluation and no longer fails, with a changed file, writes a record to `<run>/repair_memory/records/<id>.json` (trigger gate/finding id/signature class/first line, mechanism from evidence, files and bounded diff, gates passed, design family, run id, `provenance: agent-repair`, `produced_by: agent`, `reviewed: false`). The loader refuses `produced_by: human` or no provenance. Reviewed batches go to the knowledge bank by PR: `repairs/` (README, INDEX, 95 seeded records), outside every hashed unit.
2. **Retrieval by exact evidence.** Keys come from tool output only: lint (Verilator code plus whether the finding is in a source the design was handed or its own, rule ids such as `FDA-CON-8`), standards, constants, report gates, contract, simulate (exception class, or `SIM-STOP` with the clock class), verification check. At most 3 records whose `(gate, finding_id, signature_class)` equals a current key; same family first, then newest, one per distinct fix; never text similarity. Retrieval (keys, pool size, offered ids) goes to `repair_memory/retrievals.jsonl` and a routing event, also when nothing matched. The Modeller never receives a record that holds RTL (role filter). No prompt text changed (no golden, no pin change).
3. **MCP export, read-only.** `python -m agent.mcp_server.checks --design <folder>`: `check`, `lint`, `check_constraints`, `report_digest`, `list_files`, `read_file`, `list_checks` (what each check stands for); works on a copy of the folder; no write tool; `--skills <bank>` adds `skills_markdown` (index or one skill as Markdown; private content, off by default).
4. **Tests** (`agent/tests/test_217_*.py`, 16): record creation, exact-match retrieval, no match on a different signature or similar text, human-marked records refused, retrieval order and hold-out, text goes to the owning role, the arm through `stage2_plan` and through the real `node_gate`, MCP tool listing, one call, a refused write, copy of the folder; the simulator-stop digest on a real Icarus fixture and on a synthetic snapshot.

## Measure it: replay first (brief 226 proposal 4); prereg.md written 21:21 GMT before any run
107 recorded runs (209 pilot 18, 209a 9, 213 18, 224 7, 215 55), 389 stage-2 evaluations, 324 failing (228 with at least one evidence key; 96 unkeyed: a failed simulate needs the simulator output, which the snapshots lack, 199 components; 54 lint evaluations could not be re-run, mostly 215). Records are made only from the pilots' own runs (95 records, 17 keys, 34 runs); 215 benchmark runs are evaluated on, never recorded from. Leave-one-run-out (files `replay_analysis_run.txt`; leave-one-design-out in `replay_analysis_design.txt`):
- reach: 158 of 228 keyed failing evaluations have an exact-match record from another run (69%; 64% leaving the design out);
- recurring (key still failing at the next evaluation, or the run ended on it): 140; matched: 77 (55%; 48%); by gate: lint 72 of 72, standards 20 of 136, verification 14 of 15;
- ceiling (every matched recurring evaluation saved, nothing else changes): **0.72 visits per run over all 107 runs; 1.25 on the pilot designs (52 runs); 1.06 leaving the design out**. Rule (stated in advance): skip the A/B if the ceiling on the primary outcome (stage-2 visits to pass, pilot designs) is below the smallest detectable effect, about 1.7 visits (213's 9 pairs). It is, so the A/B was **skipped**. Not clear-cut everywhere: the 213 series alone gives 1.67 and 209a 1.89; the pilot runs' pass-rate ceiling is 19 of 52 runs (37 points, an upper bound counting every rescued run as a pass) against 23 to 26 points detectable (226 section 4), but pass rate is secondary.
- fix agreement: where the files a matching record changed can be compared with the files the run's next repair changed, they overlap in 33 of 69 cases (21 of 62 leaving the design out): the real ceiling is lower than the upper bound.
- the 213 lint loops (runs 2, 4, 15 of the 213 series; agent runs 20261126-043641-85a7, -052002-71da, -141421-12ad): all 18 failing evaluations had a matching record from another run. The matching records for `FDA-CON-8` hold the fix those loops never found in 5 to 6 visits (declare the spec's internal register ports on the top and mirror them to the bus instance; 209 runs 20261125-064524-4d2a and -113542-9fdc, 224 run 20261125-233045-dfe1). So the memory has the answer there; whether the agent would use it is the untested question (n = 0 live).
- AMD Ross comparison on shared specs: plan only, needs the owner's approval to install anything: run the same specs (p1 to p3 in `results/213_repair_feedback/designs`) through Ross, score with the same own gates and the board visit's independent check, 3 runs each, paired by design, graded outcomes first. Nothing installed.

## How it was verified
- `pytest agent/tests/test_217_*.py agent/tests/test_213_repair_feedback.py`: 29 passed. The 74 test files that touch the graph, the MCP server, the model hook or the divergence code: 1246 passed, 5 skipped, 1 failed (the access-gate scan, which flagged the two new `tools/repair_memory` scripts; fixed by calling `require_or_exit`, test_94 now 15 passed). The full agent suite was not run locally (it runs hours of simulations); CI is the gate.
- `FDA_PROMPTS_DIR=~/Claude_sandbox/_worktrees/230-kb-pin/prompts pytest agent/tests/test_99_prompts.py`: 30 passed, chained before each push. `flow/doccheck.py --check --strict`: 0 problems. Knowledge repo: `tools/test_sections.py`, `tools/test_prompt_manifest.py` 312 passed; `hash_layers.py` unchanged.
- CI on the first head aa619f7a: run 45899212424, completed/success. The head after the last commit: see the hand-back.

## What is illustrative
The digest on run 3 is rebuilt from the run's snapshot, not from the live gate. The replay's keys for lint were re-run on snapshots with the agent's own lint tool and OSS Verilator; standards, constants and verification keys come from the committed gate messages. Records seeded for the bank are `reviewed: false`.

## Known gaps
- No live run of arm R4 (demonstration run queued 21:28 to 22:18 GMT for a heavy slot, cancelled; `run_live.sh` is ready). The integration is covered by tests through the real `node_gate`, not by a live agent run.
- A failed simulate is keyed only when R1 produced a digest; the replay cannot key it.
- A record's diff is the whole visit's change; with several keys cleared in one visit it is not attributed to one.
- The ceiling is an upper bound; the replay mixes sources (215 benchmark designs have few failures) and counts a run that ended on a failing key as recurring.
- Records come from the same pilot family (jtag_bus register cores, KR260) as the runs they would help; a different design family has no records yet.
- The 213 R1 regrade (R3) and the ledger are unchanged; run 3's failure was a bench bug, not an RTL fault, so even the R1 fix would only have pointed at the clock.

## Gotchas
- cocotb 2.0.1 cancels tasks started in a test when it ends: a sampler or clock started in test 1 is gone in test 2.
- `Session` needs the access key even in an analysis script (the replay uses it for lint): the `.env` copy is the house-rule step, deleted at the end.
- `tools/**/*.py` scripts that import `agent` must call `require_or_exit` (test_94 scans for it).
- Fixtures: `agent/tests/conftest.py` ignores `data/b213_counter/*/tests/*.py` (the new `bad_clock` variant is covered by that glob).

## Follow-ups for the planner
1. Decide whether to run a live R4 test on the 213 lint-loop designs (p1, p3: seeds from other runs); the replay says memory has the answer for all 18 loop evaluations, the open question is use. Cost: about 1% weekly per run.
2. Review and merge the knowledge batch (PR #109) or ask for a smaller reviewed set; the records are `reviewed: false`.
3. Key a failed simulate in the replay by re-running the simulator on snapshots (needs a slot).
4. Brief 234 (stage-2 lint failures bounce to stage 1): R4 helps only if the repair visit is a stage-2 visit.

## Course impact
None.

## How to explain this in an interview
Repair memory is a lookup keyed on exact evidence (gate, finding id, signature class), not a similarity search, so a wrong fix cannot be pulled in by a similar-looking error; I measured its ceiling by replay on 107 recorded runs before spending agent runs, and the ceiling was below what an A/B could detect. The R1 fix is a debugging story: a digest that said only "Simulator shut down prematurely" turned out to be a bench that started its clock in the first test.
