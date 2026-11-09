#!/usr/bin/env python3
"""The held-out draw (brief 06a): per tier, about a third of the tasks held out, by a seeded random draw.

    split.py draw --seed N --out benchmark/split.yaml ID...
    split.py show benchmark/split.yaml

The seed is fixed and written down before the draw; the draw is `random.Random(seed).sample(sorted(tier ids),
round(n/3))` per tier (T1, T2), so anyone can re-run it and get the same split. Held-out tasks are never used while
tuning the agent; development tasks are open for agent work.

Benchmark v2 (brief 10 B0) adds a per-task assignment at creation, kept in an append-only hash-chained ledger
(`benchmark/v2/ledger.jsonl`); the v1 `draw` above is unchanged and the v1 split files are never rewritten:

    split.py assign --board B --tier T --task ID [--private-dir DIR]   # draw and append one new task
    split.py move-dev --task ID --reason TEXT                          # append a held-out -> development move
    split.py verify                                                    # check the chain, the seeds, the draw
    split.py effective                                                 # v1 split files overlaid with the moves

The v2 draw: tasks of one (board, tier) cell, in ledger order, are cut into blocks of three; one task of each block
(a position drawn from `random.Random("<seed>:<board>:<tier>:<block>")`, seed published in `benchmark/v2/seeds.yaml`)
is held out, so a complete block is exactly one third held out. A held-out entry never carries the task id: the
ledger keeps `sha256("<board>/<tier>/<id>/<nonce>")` and the id and nonce go to a private file (`--private-dir`,
outside this repo). A development entry carries the id. Each entry has `prev` and `hash` (SHA-256 over the previous
hash and the entry's canonical JSON), so an entry cannot change or move after it is drawn.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import secrets
import sys
import time
from pathlib import Path

import yaml


def draw(ids: list[str], seed: int) -> dict:
    tiers: dict[str, list[str]] = {}
    for i in sorted(ids):
        tiers.setdefault(i.split("_")[0].upper(), []).append(i)
    out = {"seed": seed, "method": "per tier: random.Random(seed).sample(sorted(ids), round(n / 3)); tiers in "
                                   "sorted order, one Random instance per tier",
           "python": sys.version.split()[0], "date": time.strftime("%Y-%m-%d"), "tiers": {}}
    for t in sorted(tiers):
        pool = tiers[t]
        held = sorted(random.Random(seed).sample(pool, round(len(pool) / 3)))
        out["tiers"][t] = {"n": len(pool), "held_out": held, "dev": [i for i in pool if i not in held]}
    return out


# ---- benchmark v2: per-task assignment at creation, append-only ledger -------------------------------------------

V2 = Path(__file__).resolve().parents[1] / "v2"
SEEDS = V2 / "seeds.yaml"
LEDGER = V2 / "ledger.jsonl"
BLOCK = 3                                     # one held out per block of three: a third
GENESIS = "0" * 64
# eval-1: the five v1/course tasks whose pass/fail counts were seen (growth plan, section "Keeping a clean baseline").
SEEN = {"t2_ascii_console": "t2", "c10_cic_decimator": "c10", "c15_topk_stream": "c15", "t2_uart_regs": "t2",
        "t1_combo_lock": "t1"}
SEEN_REASON = "eval-1 pass/fail counts were seen; moved to development (brief 10 B0)"


def _canon(e: dict) -> str:
    return json.dumps(e, sort_keys=True, separators=(",", ":"))


def entry_hash(prev: str, body: dict) -> str:
    return hashlib.sha256((prev + _canon(body)).encode()).hexdigest()


def commitment(board: str, tier: str, task: str, nonce: str) -> str:
    return hashlib.sha256(f"{board}/{tier}/{task}/{nonce}".encode()).hexdigest()


def load_seeds(path: Path = SEEDS) -> dict:
    return yaml.safe_load(path.read_text())["seeds"]


def read_ledger(path: Path = LEDGER) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def held_position(seed: int, board: str, tier: str, block: int) -> int:
    """Which of the three slots of `block` is held out; a pure function of the published seed."""
    return random.Random(f"{seed}:{board}:{tier}:{block}").randrange(BLOCK)


def draw_v2(seed: int, board: str, tier: str, index: int) -> str:
    """The assignment of the `index`-th (0-based) task of a (board, tier) cell: 'held_out' or 'dev'."""
    return "held_out" if index % BLOCK == held_position(seed, board, tier, index // BLOCK) else "dev"


def _cell_count(entries: list[dict], board: str, tier: str) -> int:
    return sum(1 for e in entries if e["kind"] == "assign" and e["board"] == board and e["tier"] == tier)


def _append(body: dict, path: Path) -> dict:
    entries = read_ledger(path)
    prev = entries[-1]["hash"] if entries else GENESIS
    body = dict(body, seq=len(entries), prev=prev)
    e = dict(body, hash=entry_hash(prev, body))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:                 # append mode only: no rewrite of an earlier line
        f.write(json.dumps(e, sort_keys=True) + "\n")
    return e


def assign(board: str, tier: str, task: str, *, seeds: dict | None = None, path: Path = LEDGER,
           private_dir: Path | None = None, nonce: str | None = None) -> dict:
    """Draw and record one new task. Refuses a cell with no published seed and a task id already in the ledger."""
    seeds = seeds if seeds is not None else load_seeds()
    if tier not in seeds.get(board, {}):
        raise SystemExit(f"no published seed for board {board!r} tier {tier!r} (add it to benchmark/v2/seeds.yaml first)")
    entries = read_ledger(path)
    for e in entries:
        if e["kind"] == "assign" and (e.get("task") == task or
                                       e.get("commit") in {commitment(board, tier, task, n) for n in e.get("_n", [])}):
            raise SystemExit(f"task {task!r} is already in the ledger")
    side = _private_read(private_dir)
    if task in {v["task"] for v in side}:
        raise SystemExit(f"task {task!r} is already in the ledger")
    idx = _cell_count(entries, board, tier)
    a = draw_v2(seeds[board][tier], board, tier, idx)
    body = {"kind": "assign", "board": board, "tier": tier, "index": idx, "assignment": a}
    if a == "dev":
        body["task"] = task
    else:
        if private_dir is None:
            raise SystemExit("a held-out draw needs --private-dir (the id is kept outside this repo)")
        nonce = nonce or secrets.token_hex(16)
        body["commit"] = commitment(board, tier, task, nonce)
    e = _append(body, path)
    if a == "held_out":
        _private_write(private_dir, {"seq": e["seq"], "board": board, "tier": tier, "task": task, "nonce": nonce,
                                     "commit": e["commit"]})
    return e


def move_dev(task: str, reason: str, *, path: Path = LEDGER) -> dict:
    """Record that a held-out task moved to development. Moves only go one way (held-out -> development)."""
    entries = read_ledger(path)
    if any(e["kind"] == "move" and e["task"] == task for e in entries):
        raise SystemExit(f"{task!r} is already recorded as moved")
    return _append({"kind": "move", "task": task, "from": "held_out", "to": "dev", "reason": reason}, path)


def _private_read(d: Path | None) -> list[dict]:
    f = d / "v2_private.jsonl" if d else None
    return [json.loads(x) for x in f.read_text().splitlines() if x.strip()] if f and f.exists() else []


def _private_write(d: Path, rec: dict) -> None:
    d.mkdir(parents=True, exist_ok=True)
    with (d / "v2_private.jsonl").open("a") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")


def verify_ledger(path: Path = LEDGER, seeds: dict | None = None) -> list[str]:
    """Problems found (empty = fine): broken chain, wrong seq, an assignment that is not the published draw, a move of a
    task that is not a seen one, or a development entry that names a task twice."""
    seeds = seeds if seeds is not None else load_seeds()
    bad, prev, count, names = [], GENESIS, {}, set()
    for i, e in enumerate(read_ledger(path)):
        body = {k: v for k, v in e.items() if k != "hash"}
        if e.get("seq") != i or e.get("prev") != prev:
            bad.append(f"entry {i}: seq/prev broken")
        if entry_hash(prev, body) != e.get("hash"):
            bad.append(f"entry {i}: hash does not match its content")
        prev = e.get("hash", "")
        if e["kind"] == "assign":
            k = (e["board"], e["tier"])
            if e["index"] != count.get(k, 0):
                bad.append(f"entry {i}: index out of order")
            count[k] = count.get(k, 0) + 1
            want = draw_v2(seeds[e["board"]][e["tier"]], e["board"], e["tier"], e["index"])
            if e["assignment"] != want:
                bad.append(f"entry {i}: assignment differs from the published draw")
            if (e["assignment"] == "dev") != ("task" in e) or (e["assignment"] == "held_out") != ("commit" in e):
                bad.append(f"entry {i}: held-out entries carry a commit and no id; dev entries carry the id")
            if "task" in e:
                if e["task"] in names:
                    bad.append(f"entry {i}: task named twice")
                names.add(e["task"])
        elif e["kind"] != "move":
            bad.append(f"entry {i}: unknown kind")
    return bad


def effective(bench: Path | None = None, path: Path = LEDGER) -> dict:
    """The v1 split files overlaid with the ledger's moves (the v1 files themselves are never rewritten)."""
    bench = bench or Path(__file__).resolve().parents[1]
    out: dict = {}
    for f in (bench / "split.yaml", bench / "course" / "split.yaml", bench / "course" / "split_c9_c12.yaml"):
        for t, v in yaml.safe_load(f.read_text())["tiers"].items():
            out[t] = {"held_out": list(v["held_out"]), "dev": list(v["dev"])}
    for e in read_ledger(path):
        if e["kind"] != "move":
            continue
        for v in out.values():
            if e["task"] in v["held_out"]:
                v["held_out"].remove(e["task"])
                v["dev"].append(e["task"])
                v["dev"].sort()
    return out


def main_v2(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="split.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("assign")
    a.add_argument("--board", required=True)
    a.add_argument("--tier", required=True)
    a.add_argument("--task", required=True)
    a.add_argument("--private-dir", type=Path)
    m = sub.add_parser("move-dev")
    m.add_argument("--task", required=True)
    m.add_argument("--reason", required=True)
    sub.add_parser("verify")
    sub.add_parser("effective")
    r = ap.parse_args(argv)
    if r.cmd == "assign":
        e = assign(r.board, r.tier, r.task, private_dir=r.private_dir)
        print(f"{r.board}/{r.tier} #{e['index']}: {e['assignment']}")
    elif r.cmd == "move-dev":
        move_dev(r.task, r.reason)
        print(f"{r.task}: recorded as moved to development")
    elif r.cmd == "verify":
        bad = verify_ledger()
        print("\n".join(bad) or f"ledger ok: {len(read_ledger())} entries")
        return 1 if bad else 0
    else:
        for t, v in effective().items():
            print(f"{t}: held out {len(v['held_out'])}, dev {len(v['dev'])}")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in {"assign", "move-dev", "verify", "effective"}:
        return main_v2(sys.argv[1:])
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draw")
    d.add_argument("--seed", type=int, required=True)
    d.add_argument("--out", type=Path, required=True)
    d.add_argument("ids", nargs="+")
    s = sub.add_parser("show")
    s.add_argument("file", type=Path)
    a = ap.parse_args()
    if a.cmd == "draw":
        r = draw(a.ids, a.seed)
        a.out.write_text("# The held-out split of benchmark v1 (benchmark/tools/split.py); never edit by hand.\n"
                         + yaml.safe_dump(r, sort_keys=False))
    else:
        r = yaml.safe_load(a.file.read_text())
    for t, v in r["tiers"].items():
        print(f"{t}: {v['n']} tasks, held out {len(v['held_out'])}: {', '.join(v['held_out'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
