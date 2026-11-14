"""Fuzzer for the UDP endpoint: valid and damaged packets in a seeded random order, checked against an independent oracle.

    python3 -m showcase.udp_endpoint.host.fuzz --dry-run --seed 1 --n 2000 [--out records/fuzz_dry_run.json]

The oracle (``classify``) is written from the protocol text, not from the model's code, and the endpoint is read only through its own
interface (a reply, or the STATUS counters), so the same fuzzer runs against the board. Checked on every run:
  1. a packet earns a reply exactly when the oracle says so, and the reply carries the oracle's status;
  2. the counters moved by exactly the classes the oracle named (STATUS read every ``check_every`` packets and after every
     truncated or oversize one, as differences);
  3. a rejected packet moves no sequence state: the next in-order command is accepted (the oracle's next packets depend on it);
  4. the endpoint answers after every truncated or oversize packet (the STATUS probe): it never hangs.
"""

from __future__ import annotations

import argparse
import json
import random

from showcase.udp_endpoint.host.client import Client, CommandError, SimTransport, Transport
from showcase.udp_endpoint.model import udp_ref as u

NEED = {1: 2, 2: 6, 3: 0, 4: 2, 5: 0}
READ_ONLY_ADDRS = (0, 4, 5, 6, 7)


def classify(pkt: bytes, last_seq: int) -> tuple[str, int | None]:
    """(the counter that must move, the reply status or None for no reply), from the protocol text."""
    if len(pkt) >= 4 and pkt[1] > 8:
        return "oversize", None
    if len(pkt) < 4 or len(pkt) < 8 + pkt[1]:
        return "truncated", None
    if len(pkt) > 8 + pkt[1]:
        return "oversize", None
    if int.from_bytes(pkt[-4:], "little") != u.crc32(pkt[:-4]):
        return "bad_crc", None
    typ, ln, seq = pkt[0], pkt[1], pkt[2] << 8 | pkt[3]
    if typ not in NEED:
        return "protocol", u.BAD_TYPE
    if ln != NEED[typ]:
        return "protocol", u.BAD_LEN
    d = (seq - last_seq) % 65536
    if d == 0:
        return "replay", u.BAD_SEQ
    if d >= 0x8000:
        return "out_of_order", u.BAD_SEQ
    if typ in (1, 2):
        addr = pkt[4] << 8 | pkt[5]
        if addr > 7:
            return "protocol", u.BAD_ADDR
        if typ == 2 and addr in READ_ONLY_ADDRS:
            return "protocol", u.READ_ONLY
    return "ok", u.OK


def damage(rng: random.Random, good: bytes, last_seq: int) -> bytes:
    k = rng.randrange(8)
    b = bytearray(good)
    if k == 0:
        b[rng.randrange(len(b))] ^= 1 << rng.randrange(8)
    elif k == 1:
        return bytes(b[:rng.randrange(len(b))])                    # truncated, including empty
    elif k == 2:
        return bytes(b) + bytes(rng.randrange(256) for _ in range(rng.randrange(1, 12)))
    elif k == 3:
        b[1] = rng.choice([9, 64, 255])                            # LEN above the maximum
    elif k == 4:
        return u.build_command(good[0], last_seq, bytes(good[4:-4]))
    elif k == 5:
        return u.build_command(good[0], (last_seq - rng.randrange(1, 0x7FFF)) & 0xFFFF, bytes(good[4:-4]))
    elif k == 6:
        return bytes(rng.randrange(256) for _ in range(rng.randrange(0, 40)))
    else:
        return u.build_command(rng.choice([0, 6, 0x7F, 0xFF]), (last_seq + 1) & 0xFFFF, bytes(rng.randrange(256) for _ in range(rng.randrange(0, 9))))
    return bytes(b)


def run(t: Transport, seed: int, n: int, check_every: int = 25) -> dict:
    rng = random.Random(seed)
    c = Client(t)
    base = c.status()
    last = (c.seq - 1) & 0xFFFF
    moved = {k: 0 for k in u.COUNTERS}
    log = {"seed": seed, "packets": 0, "replies": 0, "classes": {k: 0 for k in u.COUNTERS}, "violations": []}

    def violation(msg: str) -> None:
        if len(log["violations"]) < 20:
            log["violations"].append(f"packet {log['packets']}: {msg}")

    for i in range(n):
        seq = (last + rng.choice([1, 1, 1, 2, 5])) & 0xFFFF
        typ = rng.choice([1, 2, 3, 4, 5])
        pl = {1: rng.randrange(0, 10).to_bytes(2, "big"), 2: rng.randrange(0, 10).to_bytes(2, "big") + rng.getrandbits(32).to_bytes(4, "big"),
              3: b"", 4: rng.choice([0, 4, 50]).to_bytes(2, "big"), 5: b""}[typ]
        good = u.build_command(typ, seq, pl)
        pkt = good if rng.random() < 0.4 else damage(rng, good, last)
        cls, status = classify(pkt, last)
        got = t.exchange(pkt)
        log["packets"] += 1
        log["classes"][cls] += 1
        moved[cls] += 1
        if status is None:
            if got:
                violation(f"reply to a packet that must be dropped ({cls})")
        elif not got:
            violation(f"no reply to a {cls} packet")
        else:
            log["replies"] += 1
            try:
                r = u.parse_response(got[0])
                if r["status"] != status:
                    violation(f"status {r['status']}, expected {status} ({cls})")
            except ValueError as e:
                violation(f"bad reply ({e})")
        if cls == "ok" or (cls == "protocol" and status in (u.BAD_ADDR, u.READ_ONLY)):
            last = int.from_bytes(pkt[2:4], "big")      # authentic and in order: the number is consumed
        c.seq = (last + 1) & 0xFFFF
        if (i + 1) % check_every == 0 or cls in ("truncated", "oversize"):
            try:
                seen = c.status()                     # also the liveness probe
            except (TimeoutError, ValueError, AssertionError, CommandError) as e:
                violation(f"no answer after the packet ({e})")
                break
            last = (c.seq - 1) & 0xFFFF
            moved["ok"] += 1
            for k in u.COUNTERS:
                if (seen[k] - base[k]) & 0xFFFF != moved[k] & 0xFFFF:
                    violation(f"counter {k}: moved {(seen[k] - base[k]) & 0xFFFF}, expected {moved[k] & 0xFFFF}")
                    moved[k] = (seen[k] - base[k]) & 0xFFFF
    log["ok"] = not log["violations"]
    return log


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--host")
    ap.add_argument("--port", type=int, default=5005)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.dry_run:
        t: Transport = SimTransport()
    elif a.host:
        from showcase.udp_endpoint.host.client import UdpTransport
        t = UdpTransport(a.host, a.port)
    else:
        ap.error("give --host or --dry-run")
    log = run(t, a.seed, a.n)
    log["dry_run"] = a.dry_run
    text = json.dumps(log, indent=1)
    if a.out:
        open(a.out, "w").write(text + "\n")
    print(text)
    raise SystemExit(0 if log["ok"] else 1)


if __name__ == "__main__":
    main()
