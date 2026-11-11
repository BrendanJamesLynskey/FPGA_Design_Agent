#!/usr/bin/env python3
"""Hash a build's placement and routing (brief 33), to tell whether two builds gave the same result.

    python3 flow/result_hash.py <build dir>/result_dump.txt [--json out.json]

Reads the dump written by flow/result_hash.tcl (``C <cell> <LOC> <BEL>`` and ``N <net> <ROUTE>`` lines) one line at a
time and prints an order-independent hash of the placement lines and of the routing lines, with their counts. Two
builds with the same two hashes placed every primitive on the same site and BEL and routed every net through the
same wires. The timing (WNS) is compared separately, from the gates' parse of timing_summary.rpt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def result_hash(dump: Path) -> dict:
    """Order-independent hashes, read line by line (the CDC rig's dump is too large to hold in memory): each group's
    hash is the sum, modulo 2**256, of the SHA-256 of each of its lines (a multiset hash: the same lines in any order
    give the same value; any changed, added or removed line changes it)."""
    acc = {"C": 0, "N": 0}
    count = {"C": 0, "N": 0}
    with dump.open("rb") as f:
        for line in f:
            kind = line[:2]
            if kind in (b"C ", b"N "):
                k = kind[:1].decode()
                acc[k] = (acc[k] + int.from_bytes(hashlib.sha256(line.rstrip(b"\n")).digest(), "big")) % (1 << 256)
                count[k] += 1
    return {"placement_sha256": f"{acc['C']:064x}", "routing_sha256": f"{acc['N']:064x}",
            "cells": count["C"], "nets": count["N"], "method": "sum of line SHA-256 mod 2^256"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dump", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    if not a.dump.is_file():
        print(f"result_hash: no dump at {a.dump}", file=sys.stderr)
        return 1
    r = result_hash(a.dump)
    if a.json:
        a.json.write_text(json.dumps(r, indent=2) + "\n")
    print(json.dumps(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
