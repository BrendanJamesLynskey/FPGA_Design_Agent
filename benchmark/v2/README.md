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

## Pending tasks

A pending task is **neither development nor held-out**. `verify` and `effective` list pending manifests per cell; **the agent must not run, read or tune on a pending task**
until its block is drawn and it is listed as development.

## Residual risk

An author could grind manifests (change harmless bytes until the draw puts a hard task in the held-out slot). Task writers are told not to; the freeze commit of each
manifest precedes its submit and the draw in git history, so a reviewer can compare the order. Nothing in the tool prevents grinding.
