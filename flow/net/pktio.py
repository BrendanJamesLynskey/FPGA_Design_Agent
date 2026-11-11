"""Stimulus and response files for the packet benches (brief 40). The gap schedules are the brief-19 harness's
(`flow/ipgen/harness.py`: seeded valid/ready lists, the same file format)."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from flow.ipgen import harness


def write_stream(path: Path, packets, users=None, extra=None) -> None:
    """One beat a line: '<tdata hex> <tlast> <tuser>' (+ ' <extra hex>' on every beat when `extra` gives a value per
    packet: the port or queue of that packet)."""
    with open(path, "w") as f:
        for j, p in enumerate(packets):
            u = users[j] if users else 0
            for i, b in enumerate(p):
                last = int(i == len(p) - 1)
                x = f" {extra[j]:x}" if extra is not None else ""
                f.write(f"{b:02x} {last} {u if last else 0}{x}\n")


def write_sched(path: Path, kind: str = "random", n: int = 4096, seed: int = 1, p_valid: float = 0.7,
                p_ready: float = 0.6) -> int:
    s = harness.schedule(kind, n=n, seed=seed, p_valid=p_valid, p_ready=p_ready)
    harness.write_schedule(path, s)
    return len(s)


def read_resp(path: Path) -> dict:
    """Parse a response file: 'D[port] <cycle> <tdata> <tlast> <tuser> [extra]' beats are grouped into packets per
    tag; 'H <cycle> <hex>' header words and other tagged words are listed; '# k v' lines go to meta."""
    out = {"pkts": defaultdict(list), "first": defaultdict(list), "words": defaultdict(list), "meta": {}}
    cur = defaultdict(list)
    for ln in Path(path).read_text().splitlines():
        t = ln.split()
        if not t:
            continue
        if t[0] == "#":
            out["meta"][t[1]] = int(t[2])
        elif t[0].startswith("D"):
            tag = t[0]
            c, d, last, user = int(t[1]), int(t[2], 16), int(t[3]), int(t[4])
            if not cur[tag]:
                out["first"][tag].append(c)
            cur[tag].append(d)
            if last:
                ex = int(t[5], 16) if len(t) > 5 else None
                out["pkts"][tag].append((bytes(cur[tag]), user, ex))
                cur[tag] = []
        else:
            out["words"][t[0]].append((int(t[1]), [int(x, 16) for x in t[2:]]))
    return out
