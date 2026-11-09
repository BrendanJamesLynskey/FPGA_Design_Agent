# Benchmark v2 split ledger

`ledger.jsonl` is the append-only record of which v2 tasks are development and which are held out
(`benchmark/tools/split.py`, brief 10 B0). Each line carries `prev` and `hash`, so no line can change or move after
it is written; `python3 benchmark/tools/split.py verify` checks the chain and that every assignment is the published
draw for its cell (`seeds.yaml`).

- A task is drawn when it is created: `split.py assign --board B --tier T --task ID --private-dir DIR`. In each cell
  the tasks, in ledger order, form blocks of three, and one of each block is held out.
- A held-out entry holds only `sha256("<board>/<tier>/<id>/<nonce>")`; the id and nonce are written to a private file
  outside this repo. A development entry names its task.
- The five tasks whose eval-1 counts were seen are recorded as `move` entries (held-out to development). The v1 split
  files are not edited; `split.py effective` shows them with the moves applied.
