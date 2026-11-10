#!/usr/bin/env python3
"""The held-out draw (brief 06a): per tier, about a third of the tasks held out, by a seeded random draw.

    split.py draw --seed N --out benchmark/split.yaml ID...
    split.py show benchmark/split.yaml

The seed is fixed and written down before the draw; the draw is `random.Random(seed).sample(sorted(tier ids),
round(n/3))` per tier (T1, T2), so anyone can re-run it and get the same split. Held-out tasks are never used while
tuning the agent; development tasks are open for agent work.

Benchmark v2 (brief 10 B0) assigns tasks in blocks of three per (domain, tier) cell, in an append-only hash-chained
ledger (`benchmark/v2/ledger.jsonl`); the v1 `draw` above is unchanged and the v1 split files are never rewritten:

    split.py submit --board B --domain D --tier T --manifest FILE --task ID --private-dir DIR   # a frozen task waits as pending
    split.py move-dev --task ID --reason TEXT                                    # append a held-out -> development move
    split.py verify                                                              # chain, seeds, draws, pending list
    split.py effective                                                           # v1 split files + moves + pending count
    split.py shell-freeze --reason TEXT                                          # append the grader-dependency hash of shell/ (brief 15)
    split.py amend --task ID --manifest FILE --reason TEXT                       # append a dated amendment of a development task

A submitted task is **pending**: the ledger holds its cell, board and the SHA-256 of its manifest, never its id. When a cell has three pending tasks the block is
drawn: the held-out one is `sorted(manifests)[Random(f"<seed>:<domain>:<tier>:<block>:" + "".join(sorted(manifests))).randrange(3)]`, with the seed published in
`benchmark/v2/seeds.yaml`. The draw entry names the two development tasks (id and manifest) and only the manifest of the held-out one. Pending tasks are neither
development nor held-out and must not be run. The id and manifest of every pending task live in a private file outside this repo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
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


# ---- benchmark v2: blocks of three per (domain, tier), drawn when complete -----------------------------------------

V2 = Path(__file__).resolve().parents[1] / "v2"
SEEDS = V2 / "seeds.yaml"
LEDGER = V2 / "ledger.jsonl"
BLOCK = 3                                     # one held out per complete block of three: a third
GENESIS = "0" * 64
# eval-1: the five v1/course tasks whose pass/fail counts were seen (growth plan, section "Keeping a clean baseline").
SEEN = {"t2_ascii_console": "t2", "c10_cic_decimator": "c10", "c15_topk_stream": "c15", "t2_uart_regs": "t2",
        "t1_combo_lock": "t1"}
SEEN_REASON = "eval-1 pass/fail counts were seen; moved to development (brief 10 B0)"


def _canon(e: dict) -> str:
    return json.dumps(e, sort_keys=True, separators=(",", ":"))


def entry_hash(prev: str, body: dict) -> str:
    return hashlib.sha256((prev + _canon(body)).encode()).hexdigest()


def manifest_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_seeds(path: Path = SEEDS) -> dict:
    return yaml.safe_load(path.read_text())["seeds"]


def read_ledger(path: Path = LEDGER) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def held_index(seed: int, domain: str, tier: str, block: int, manifests: list[str]) -> int:
    """Index into sorted(manifests) of the held-out task. Depends on the three frozen manifests, so the slot cannot be
    known before all three are written."""
    ms = sorted(manifests)
    assert len(ms) == BLOCK
    return random.Random(f"{seed}:{domain}:{tier}:{block}:" + "".join(ms)).randrange(BLOCK)


def pending(entries: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """Submitted entries of each cell that no draw has taken yet, in ledger order."""
    out: dict[tuple[str, str], list[dict]] = {}
    for e in entries:
        k = (e.get("domain"), e.get("tier"))
        if e["kind"] == "submit":
            out.setdefault(k, []).append(e)
        elif e["kind"] == "draw":
            taken = set(e["manifests"])
            out[k] = [x for x in out.get(k, []) if x["manifest"] not in taken]
    return {k: v for k, v in out.items() if v}


def _append(body: dict, path: Path) -> dict:
    entries = read_ledger(path)
    prev = entries[-1]["hash"] if entries else GENESIS
    body = dict(body, seq=len(entries), prev=prev)
    e = dict(body, hash=entry_hash(prev, body))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:                 # append mode only: no rewrite of an earlier line
        f.write(json.dumps(e, sort_keys=True) + "\n")
    return e


def _private_read(d: Path | None) -> list[dict]:
    f = d / "v2_private.jsonl" if d else None
    return [json.loads(x) for x in f.read_text().splitlines() if x.strip()] if f and f.exists() else []


def _private_write(d: Path, rec: dict) -> None:
    d.mkdir(parents=True, exist_ok=True)
    with (d / "v2_private.jsonl").open("a") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")


def submit(board: str, domain: str, tier: str, manifest: str, task: str, *, private_dir: Path, seeds: dict | None = None,
           path: Path = LEDGER) -> tuple[dict, dict | None]:
    """Record a frozen task as pending (its id goes only to the private file). When this is the third pending task of the
    cell, the block is drawn in the same call and the draw entry is returned second."""
    seeds = seeds if seeds is not None else load_seeds()
    if tier not in seeds.get(domain, {}):
        raise SystemExit(f"no published seed for domain {domain!r} tier {tier!r} (add it to benchmark/v2/seeds.yaml first)")
    entries = read_ledger(path)
    seen = {m for e in entries if e["kind"] == "submit" for m in [e["manifest"]]}
    if manifest in seen:
        raise SystemExit("this manifest is already in the ledger")
    if any(r["task"] == task for r in _private_read(private_dir)) or \
            any(e["kind"] == "draw" and task in [d.get("task") for d in e["dev"]] for e in entries):
        raise SystemExit(f"task {task!r} is already in the ledger")
    # Everything the draw needs must be known before the ledger is touched: a draw that fails after the third submit has
    # been appended would leave three pending entries and a private file with no way to complete the block.
    would_be = [x["manifest"] for x in pending(entries).get((domain, tier), [])] + [manifest]
    if len(would_be) >= BLOCK:
        known = {r["manifest"] for r in _private_read(private_dir)}
        missing = [m for m in would_be[:BLOCK] if m != manifest and m not in known]
        if missing:
            raise SystemExit(f"this submit completes a block, but {private_dir} does not hold the task ids of {len(missing)} "
                             f"of its pending manifests; use the private directory of the earlier submits (nothing was written)")
    e = _append({"kind": "submit", "board": board, "domain": domain, "tier": tier, "manifest": manifest}, path)
    _private_write(private_dir, {"seq": e["seq"], "task": task, "manifest": manifest, "board": board, "domain": domain, "tier": tier})
    cell = pending(read_ledger(path)).get((domain, tier), [])
    if len(cell) < BLOCK:
        return e, None
    block = sum(1 for x in read_ledger(path) if x["kind"] == "draw" and x["domain"] == domain and x["tier"] == tier)
    ms = sorted(x["manifest"] for x in cell[:BLOCK])
    h = ms[held_index(seeds[domain][tier], domain, tier, block, ms)]
    ids = {r["manifest"]: r["task"] for r in _private_read(private_dir)}
    boards = {x["manifest"]: x["board"] for x in cell[:BLOCK]}
    dev = [{"manifest": m, "task": ids[m], "board": boards[m]} for m in ms if m != h]
    d = _append({"kind": "draw", "domain": domain, "tier": tier, "block": block, "manifests": ms,
                 "held_out": {"manifest": h, "board": boards[h]}, "dev": dev}, path)
    return e, d


def listed_held_out(bench: Path | None = None) -> set[str]:
    """Held-out task ids named in the v1 and course split files."""
    bench = bench or Path(__file__).resolve().parents[1]
    out: set[str] = set()
    for f in (bench / "split.yaml", bench / "course" / "split.yaml", bench / "course" / "split_c9_c12.yaml"):
        for v in yaml.safe_load(f.read_text())["tiers"].values():
            out |= set(v["held_out"])
    return out


def move_dev(task: str, reason: str, *, path: Path = LEDGER, check: bool = True) -> dict:
    """Record that a held-out task moved to development. Moves only go one way (held-out -> development). With
    ``check`` (the CLI default) the task must be a held-out id in a v1 or course split file: a v2 held-out task is named
    nowhere public, so moving one needs ``--unlisted`` and the id is then written to the ledger on purpose."""
    entries = read_ledger(path)
    if any(e["kind"] == "move" and e["task"] == task for e in entries):
        raise SystemExit(f"{task!r} is already recorded as moved")
    if check and task not in listed_held_out():
        raise SystemExit(f"{task!r} is not a held-out task in any split file (pass --unlisted to move a v2 held-out task)")
    return _append({"kind": "move", "task": task, "from": "held_out", "to": "dev", "reason": reason}, path)


def verify_ledger(path: Path = LEDGER, seeds: dict | None = None) -> list[str]:
    """Problems found (empty = fine): broken chain, a submit that names its task, a draw that is not the published draw of
    the cell's first three pending manifests, a held-out entry that names its task, a manifest or task named twice."""
    seeds = seeds if seeds is not None else load_seeds()
    bad, prev, names, mans = [], GENESIS, set(), set()
    entries = read_ledger(path)
    for i, e in enumerate(entries):
        body = {k: v for k, v in e.items() if k != "hash"}
        if e.get("seq") != i or e.get("prev") != prev:
            bad.append(f"entry {i}: seq/prev broken")
        if entry_hash(prev, body) != e.get("hash"):
            bad.append(f"entry {i}: hash does not match its content")
        prev = e.get("hash", "")
        if e["kind"] == "submit":
            if "task" in e:
                bad.append(f"entry {i}: a pending entry must not name its task")
            if e["manifest"] in mans:
                bad.append(f"entry {i}: manifest named twice")
            mans.add(e["manifest"])
        elif e["kind"] == "draw":
            cell = [x["manifest"] for x in pending(entries[:i]).get((e["domain"], e["tier"]), [])][:BLOCK]
            if sorted(cell) != e["manifests"] or len(cell) != BLOCK:
                bad.append(f"entry {i}: draw is not the cell's first three pending manifests")
                continue
            nblock = sum(1 for x in entries[:i] if x["kind"] == "draw" and x["domain"] == e["domain"] and x["tier"] == e["tier"])
            if e["tier"] not in seeds.get(e["domain"], {}):
                bad.append(f"entry {i}: no published seed for domain {e['domain']!r} tier {e['tier']!r}")
                continue
            want = e["manifests"][held_index(seeds[e["domain"]][e["tier"]], e["domain"], e["tier"], nblock, cell)]
            if e["block"] != nblock or e["held_out"]["manifest"] != want:
                bad.append(f"entry {i}: held-out choice differs from the published draw")
            if "task" in e["held_out"] or sorted(d["manifest"] for d in e["dev"]) != [m for m in e["manifests"] if m != want]:
                bad.append(f"entry {i}: held-out entry names its task, or dev set is wrong")
            for d in e["dev"]:
                if d["task"] in names:
                    bad.append(f"entry {i}: task named twice")
                names.add(d["task"])
        elif e["kind"] == "amend":
            now = current_manifests(entries[:i])
            if e.get("task") not in now:
                bad.append(f"entry {i}: amendment of a task that is not a development task")
            elif e.get("old_manifest") != now[e["task"]] or e.get("new_manifest") == e.get("old_manifest"):
                bad.append(f"entry {i}: amendment does not start from the task's current manifest hash")
            if not str(e.get("reason", "")).strip() or not e.get("dated"):
                bad.append(f"entry {i}: amendment without a date or a reason")
        elif e["kind"] == "shell_freeze":
            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
            from benchmark.tools.freeze import digest as _digest
            if _digest(e.get("files", {})) != e.get("shell_sha256") or not e.get("files"):
                bad.append(f"entry {i}: shell_freeze hash does not match its file list")
        elif e["kind"] != "move":
            bad.append(f"entry {i}: unknown kind")
    return bad


def verify_shell(entries: list[dict] | None = None, grader_shell: Path | None = None) -> list[str]:
    """The current shell (or ``grader_shell``, a checked-out frozen copy) against the latest ``shell_freeze`` entry; a ledger
    with no such entry is a problem too, so a v2 score cannot be tied to nothing."""
    entries = read_ledger() if entries is None else entries
    e = latest_shell_freeze(entries)
    if e is None:
        return ["no shell_freeze entry in the ledger"]
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from benchmark.tools import shell_freeze as SF
    return SF.verify_record(e, grader_shell, label="shell (v2 ledger)")


def current_manifests(entries: list[dict]) -> dict[str, str]:
    """Development task -> the SHA-256 of the manifest it is frozen at now: the draw's, or the latest ``amend`` entry's."""
    out = {d["task"]: d["manifest"] for e in entries if e["kind"] == "draw" for d in e["dev"]}
    for e in entries:
        if e["kind"] == "amend":
            out[e["task"]] = e["new_manifest"]
    return out


def latest_shell_freeze(entries: list[dict]) -> dict | None:
    return next((e for e in reversed(entries) if e["kind"] == "shell_freeze"), None)


def shell_freeze(reason: str, *, path: Path = LEDGER, date: str | None = None) -> dict:
    """Append the SHA-256 of everything a grader imports from shell/ (benchmark/tools/shell_freeze.py), with the file list.
    A later entry supersedes an earlier one; the earlier stays in the chain."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from benchmark.tools import shell_freeze as SF
    rec = SF.record(reason)
    return _append({"kind": "shell_freeze", "dated": date or rec["dated"], "reason": reason, "shell_sha256": rec["shell_sha256"],
                    "files": rec["files"]}, path)


def amend(task: str, manifest: str, reason: str, *, digest: str, old_digest: str | None = None, path: Path = LEDGER,
          date: str | None = None) -> dict:
    """Append a dated amendment of a development task: its manifest hash changed from the one on record to ``manifest``.
    Only a task a draw names as development can be amended (a held-out task has no public name and is never touched)."""
    entries = read_ledger(path)
    now = current_manifests(entries)
    if task not in now:
        raise SystemExit(f"{task!r} is not a development task in the ledger")
    if now[task] == manifest:
        raise SystemExit(f"{task!r} is already frozen at this manifest")
    if not reason.strip():
        raise SystemExit("an amendment needs a reason")
    return _append({"kind": "amend", "task": task, "dated": date or time.strftime("%Y-%m-%d"), "reason": reason,
                    "old_manifest": now[task], "new_manifest": manifest, "new_digest": digest}, path)


def effective(bench: Path | None = None, path: Path = LEDGER) -> dict:
    """The v1 split files overlaid with the ledger: moves, v2 draws (key `v2:<domain>/<tier>`; held-out are manifests) and
    `pending` (manifest hashes per cell: neither development nor held-out, never to be run)."""
    bench = bench or Path(__file__).resolve().parents[1]
    out: dict = {}
    for f in (bench / "split.yaml", bench / "course" / "split.yaml", bench / "course" / "split_c9_c12.yaml"):
        for t, v in yaml.safe_load(f.read_text())["tiers"].items():
            out[t] = {"held_out": list(v["held_out"]), "dev": list(v["dev"])}
    entries = read_ledger(path)
    for e in entries:
        if e["kind"] == "move":
            for v in out.values():
                if e["task"] in v["held_out"]:
                    v["held_out"].remove(e["task"])
                    v["dev"].append(e["task"])
                    v["dev"].sort()
        elif e["kind"] == "draw":
            v = out.setdefault(f"v2:{e['domain']}/{e['tier']}", {"held_out": [], "dev": []})
            v["held_out"].append(e["held_out"]["manifest"])
            v["dev"] += [d["task"] for d in e["dev"]]
    out["pending"] = {f"{d}/{t}": [x["manifest"] for x in v] for (d, t), v in pending(entries).items()}
    return out


def main_v2(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="split.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("submit")
    for k in ("board", "domain", "tier", "task"):
        a.add_argument(f"--{k}", required=True)
    a.add_argument("--manifest", type=Path, required=True)
    a.add_argument("--private-dir", type=Path, required=True)
    m = sub.add_parser("move-dev")
    m.add_argument("--task", required=True)
    m.add_argument("--reason", required=True)
    m.add_argument("--unlisted", action="store_true", help="allow a task that no split file lists as held out")
    v = sub.add_parser("verify")
    v.add_argument("--grader-shell", type=Path, default=None, help="a checked-out frozen copy of the repository to check instead of this tree's shell/")
    sub.add_parser("effective")
    sf = sub.add_parser("shell-freeze")
    sf.add_argument("--reason", required=True)
    am = sub.add_parser("amend")
    am.add_argument("--task", required=True)
    am.add_argument("--manifest", type=Path, required=True)
    am.add_argument("--reason", required=True)
    r = ap.parse_args(argv)
    if r.cmd == "submit":
        e, d = submit(r.board, r.domain, r.tier, manifest_hash(r.manifest), r.task, private_dir=r.private_dir)
        print(f"{r.domain}/{r.tier}: pending" + (f", block {d['block']} drawn" if d else ""))
    elif r.cmd == "move-dev":
        move_dev(r.task, r.reason, check=not r.unlisted)
        print(f"{r.task}: recorded as moved to development")
    elif r.cmd == "shell-freeze":
        e = shell_freeze(r.reason)
        print(f"shell_freeze recorded: {e['shell_sha256']} ({len(e['files'])} files)")
    elif r.cmd == "amend":
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        m = json.loads(r.manifest.read_text())["units"][0]
        if r.task != m["id"]:
            raise SystemExit(f"manifest is for {m['id']!r}, not {r.task!r}")
        e = amend(r.task, manifest_hash(r.manifest), r.reason, digest=m["digest"])
        print(f"{r.task}: amended, manifest {e['old_manifest'][:16]} -> {e['new_manifest'][:16]}")
    elif r.cmd == "verify":
        bad = verify_ledger() + verify_shell(grader_shell=r.grader_shell)
        pend = {k: len(v) for k, v in pending(read_ledger()).items()}
        print("\n".join(bad) or f"ledger ok: {len(read_ledger())} entries; pending {pend or 'none'}")
        return 1 if bad else 0
    else:
        for t, v in effective().items():
            print(f"{t}: {v}" if t == "pending" else f"{t}: held out {len(v['held_out'])}, dev {len(v['dev'])}")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in {"submit", "move-dev", "verify", "effective", "shell-freeze", "amend"}:
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
