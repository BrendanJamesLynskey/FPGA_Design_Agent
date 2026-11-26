"""Criteria collection for a pilot host check: every criterion is named, has its value and its expectation, and prints PASS or FAIL."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class Report:
    def __init__(self, design: str, expect_id: int, expect_build: int | None) -> None:
        self.design, self.expect_id, self.expect_build = design, expect_id, expect_build
        self.criteria: list[dict[str, Any]] = []
        self.data: dict[str, Any] = {}
        self.aborted: str | None = None            # an inconclusive run (setup fault), never a design FAIL

    def crit(self, name: str, ok: bool, value: Any, expected: Any) -> bool:
        self.criteria.append({"name": name, "pass": bool(ok), "value": value, "expected": expected})
        print(f"  {'PASS' if ok else 'FAIL'} {name}: {value} (expected {expected})", flush=True)
        return bool(ok)

    @property
    def all_pass(self) -> bool:
        return self.aborted is None and bool(self.criteria) and all(c["pass"] for c in self.criteria)

    def verdict(self) -> str:
        return "INCONCLUSIVE" if self.aborted else ("PASS" if self.all_pass else "FAIL")

    def write(self, out: Path) -> Path:
        out.mkdir(parents=True, exist_ok=True)
        p = out / f"{self.design}.json"
        p.write_text(json.dumps({"design": self.design, "verdict": self.verdict(), "aborted": self.aborted, "expect_id": self.expect_id,
                                 "expect_build": self.expect_build, "stamp_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                 "criteria": self.criteria, "data": self.data}, indent=1) + "\n")
        return p


class Inconclusive(Exception):
    """A setup fault (wrong ID or build, a dead bus), not a design fault."""


def basics(bus, rep: Report) -> None:
    """The three registers every pilot design has: ID, BUILD (the stamp) and SCRATCH."""
    i = bus.rd(0x000)
    b = bus.rd(0x004)
    rep.data["id"], rep.data["build"] = f"{i:08x}", f"{b:08x}"
    if i != rep.expect_id:
        rep.aborted = f"ID {i:08x} is not {rep.expect_id:08x}: wrong design loaded or the bus is not answering"
        raise Inconclusive(rep.aborted)
    if rep.expect_build is not None and b != rep.expect_build:
        rep.aborted = f"BUILD {b:08x} is not the expected stamp {rep.expect_build:08x}: wrong bitstream"
        raise Inconclusive(rep.aborted)
    rep.crit("id", True, f"{i:08x}", f"{rep.expect_id:08x}")
    rep.crit("build_stamp", rep.expect_build is not None and b == rep.expect_build, f"{b:08x}",
             f"{rep.expect_build:08x}" if rep.expect_build is not None else "no stamp given")
    ok = True
    vals = []
    for v in (0xA5A5A5A5, 0x5A5A5A5A, 0xFFFFFFFF, 0x00000001, 0x80000000, 0):
        bus.wr(0x008, v)
        got = bus.rd(0x008)
        vals.append(got)
        ok &= got == v
    rep.crit("scratch_readback", ok, [f"{v:08x}" for v in vals], "what was written")
