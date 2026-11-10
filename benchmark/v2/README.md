# Benchmark v2 split ledger

`ledger.jsonl` is the append-only record of which v2 tasks are development and which are held out
(`benchmark/tools/split.py`, brief 10 B0). Each line carries `prev` and `hash`, so no line can change or move after
it is written; `python3 benchmark/tools/split.py verify` checks the chain and that every draw is the published draw.

## How a task is assigned

- The cell is **(domain, tier)**: domains A-T (coverage survey), tiers `drill`, `T1`-`T4`. The board is a field of each entry, not part of the cell.
  Per-domain thirds are therefore exact for every complete block. Seeds: `seeds.yaml`, one integer per domain and tier.
- A frozen task is **submitted**: `split.py submit --domain D --tier T --board B --manifest FILE --task ID --private-dir DIR`. The ledger stores the SHA-256 of
  its manifest, never its id; id and manifest go to a private file outside this repo. The task is now **pending**.
- When a cell holds three pending tasks, the block is **drawn**: the held-out one is `sorted(manifests)[Random(f"<seed>:<domain>:<tier>:<block>:" + "".join(sorted(manifests))).randrange(3)]`.
  The slot depends on all three frozen manifests, so nobody can know before the third is frozen which task will be held out.
  The draw entry names the two development tasks (id, manifest) and only the manifest of the held-out one.
- The five tasks whose eval-1 counts were seen are `move` entries (held-out to development). The v1 split files are not edited;
  `split.py effective` shows them with the moves, the v2 draws and the pending manifests.

## Shell freeze and amendments

Two more entry kinds, both appended with `split.py` and both part of the hash chain:

- `shell_freeze`: the SHA-256 of everything a grader imports from `shell/` (`shell/rtl/*.sv`, `shell/host/protocol.py`, `shell/tests/uart_bfm.py` and the
  packages' `__init__.py`), with the file list. `split.py verify` fails if the current shell differs from the latest entry, unless
  `--grader-shell DIR` names a checked-out frozen copy (how a scored run uses one: [../FROZEN.md](../FROZEN.md)). Record: `split.py shell-freeze --reason TEXT`.
- `amend`: a dated change to a **development** task (task id, the manifest hash it had, the new manifest hash, new unit digest, date, reason). Record:
  `split.py amend --task ID --manifest FILE --reason TEXT` after regenerating the task's manifest with `freeze_v2.py make`. `verify` checks that each
  amendment starts from the task's current manifest hash (the draw's, or the previous amendment's), and
  `tests/test_task_quality.py` accepts a task's files and manifest only if the manifest's SHA-256 is that current hash. The draw is not redone and held-out
  tasks are never amended. Each amendment is also written up in [../AMENDMENTS.md](../AMENDMENTS.md).

## Pending tasks

A pending task is **neither development nor held-out**. `verify` and `effective` list pending manifests per cell; **the agent must not run, read or tune on a pending task**
until its block is drawn and it is listed as development.

## Residual risk

An author could grind manifests (change harmless bytes until the draw puts a hard task in the held-out slot). Task writers are told not to; the freeze commit of each
manifest precedes its submit and the draw in git history, so a reviewer can compare the order. Nothing in the tool prevents grinding.

## Checks that keep a drawn task fixed

- `split.py verify` checks the hash chain; a ledger rewritten end to end with recomputed hashes still passes it, so
  `benchmark/tests/test_task_quality.py::test_ledger_only_grows_against_the_base_commit` compares the ledger with the pull-request base
  (`PR_BASE_SHA`, else `origin/main`): every earlier line must be unchanged.
- The same file checks that each public v2 task still hashes to its committed manifest, that the manifest's SHA-256 is the one the ledger
  recorded in the draw entry, and that `benchmark/v2/tasks` holds exactly the development tasks the ledger names.
- CI runs every v2 development task through `check_task.py` (reference passes, mutants killed, trap fires); a pull request runs the tasks it
  touches plus the smoke task, and all of them when it touches shared grader code (`tools/ci_select.py`).
- `split.py submit` refuses a block-completing submit whose private directory lacks the earlier task ids (nothing is written);
  `split.py move-dev` refuses a task no v1 or course split file holds out unless `--unlisted` is given.
