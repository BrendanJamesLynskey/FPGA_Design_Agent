#!/usr/bin/env python3
"""read_counters.py: the PC side of the CDC soak rig (hil/cdc_soak).

Parses the rig's UART records (format in rtl/rig_ctrl.sv), checks each line's CRC-8, writes a CSV with host time
stamps, and applies the host-side stop rules: it stops (exit status 2) when the junction temperature reaches the limit
(default 80 degC) or when two epochs in a row are missed. It never programs or reprograms the board.

    # live, from the board's USB-UART (read only)
    python3 hil/cdc_soak/host/read_counters.py --port /dev/ttyUSB1 --epoch-s 60 --csv run.csv
    # offline, from a saved log (or the simulation's log)
    python3 hil/cdc_soak/host/read_counters.py --file uart.log --summary

Fields are upper-case hex. temp and vccint are raw 12-bit XADC codes (UG480: T = code x 503.975 / 4096 - 273.15;
V = code x 3 / 4096); cfgmclk is CFGMCLK cycles in 1 ms, i.e. kHz.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, TextIO

VARIANTS = ["C1", "C2", "C3a", "C3b", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12", "C13",
            "M1", "M1b", "M2", "M3", "M4", "M5", "M6a", "M6b", "M6c", "M7", "M8", "M9", "M10", "M11"]
CLASSES = ["far", "near", "boundary"]
DIRS = ["a->b", "b->a", "a->c"]
EW, VW, LW, RW = 24, 32, 8, 8          # record widths (rec_cnt)


class LineError(ValueError):
    """A line that is not a valid record (bad CRC, unknown type, wrong field count)."""


def crc8(data: bytes) -> int:
    """CRC-8, polynomial 0x07, initial value 0, no reflection (the rig's line_tx)."""
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def temp_c(code: int) -> float:
    return code * 503.975 / 4096 - 273.15


def vcc_mv(code: int) -> float:
    return code * 3000.0 / 4096


FIELDS = {"H": 3, "E": 6, "C": 9, "S": 3}


def parse_line(line: str) -> dict:
    """One record line (with or without CR/LF) as a dict; raises LineError if it is not valid."""
    line = line.strip()
    if "*" not in line:
        raise LineError(f"no CRC: {line!r}")
    body, _, cc = line.rpartition("*")
    try:
        want = int(cc, 16)
    except ValueError as e:
        raise LineError(f"bad CRC field: {line!r}") from e
    if crc8(body.encode("ascii", "replace")) != want:
        raise LineError(f"CRC mismatch: {line!r}")
    parts = body.split(",")
    kind = parts[0]
    if kind not in FIELDS or len(parts) - 1 != FIELDS[kind]:
        raise LineError(f"unknown record or wrong field count: {line!r}")
    h = [int(x, 16) for x in parts[1:]] if kind != "H" and kind != "S" else None
    if kind == "H":
        if parts[1] != "CDCRIG":
            raise LineError(f"not a CDC rig: {line!r}")
        return {"kind": "H", "copies": int(parts[2], 16), "build": parts[3]}
    if kind == "S":
        if parts[1] != "TJ":
            raise LineError(f"unknown stop: {line!r}")
        code = int(parts[2], 16)
        return {"kind": "S", "reason": "TJ", "temp_code": code, "tj_c": round(temp_c(code), 2),
                "uptime_s": int(parts[3], 16)}
    assert h is not None
    if kind == "E":
        epoch, up, t, v, khz, mode = h
        return {"kind": "E", "epoch": epoch, "uptime_s": up, "temp_code": t, "tj_c": round(temp_c(t), 2),
                "vccint_mv": round(vcc_mv(v), 1), "cfgmclk_khz": khz, "storm_mode": mode}
    g, var, cls, d, err, ev, lock, relock, sat = h
    if var >= len(VARIANTS) or cls >= len(CLASSES) or d >= len(DIRS):
        raise LineError(f"code out of range: {line!r}")
    return {"kind": "C", "copy": g, "variant": VARIANTS[var], "cls": CLASSES[cls], "dir": DIRS[d],
            "errors": err, "events": ev, "lockups": lock, "relocks": relock, "sat": sat}


def parse_stream(lines: Iterable[str], strict: bool = False) -> Iterator[dict]:
    """Records from text lines; invalid lines are yielded as {'kind': 'bad', 'line': ...} unless strict."""
    for ln in lines:
        if not ln.strip():
            continue
        try:
            yield parse_line(ln)
        except LineError:
            if strict:
                raise
            yield {"kind": "bad", "line": ln.rstrip("\r\n")}


@dataclass
class Run:
    """What a stream of records says: the latest record per copy, the epochs, the stop."""
    hello: dict | None = None
    epochs: list[dict] = field(default_factory=list)
    copies: dict[int, dict] = field(default_factory=dict)
    by_epoch: dict[int, dict[int, dict]] = field(default_factory=dict)
    stop: dict | None = None
    bad: int = 0

    def add(self, r: dict) -> None:
        k = r["kind"]
        if k == "H":
            self.hello = r
        elif k == "E":
            self.epochs.append(r)
        elif k == "C":
            self.copies[r["copy"]] = r
            if self.epochs:
                self.by_epoch.setdefault(self.epochs[-1]["epoch"], {})[r["copy"]] = r
        elif k == "S":
            self.stop = r
        else:
            self.bad += 1

    def copy_count(self) -> int | None:
        """The number of copies: the H line's, or (a CSV written before H carried it) the largest epoch seen."""
        if self.hello and self.hello.get("copies"):
            return self.hello["copies"]
        return max((len(cs) for cs in self.by_epoch.values()), default=None)

    def complete_epochs(self) -> list[int]:
        """Epochs whose C records cover every copy. An epoch is written over about 1.3 s, so a summary that takes the
        latest record of each copy can mix two epochs (and a read of a running log can stop inside one): summaries
        use these epochs only."""
        n = self.copy_count()
        return [e for e, cs in self.by_epoch.items() if n is not None and len(cs) == n]

    def per_variant(self, epoch: int | None = None) -> dict[str, dict]:
        """Totals per variant over one epoch's records (default: the latest complete epoch; with none complete, the
        latest record of each copy)."""
        out: dict[str, dict] = {}
        if epoch is None and self.complete_epochs():
            epoch = self.complete_epochs()[-1]
        recs = self.by_epoch[epoch].values() if epoch is not None else self.copies.values()
        for r in recs:
            s = out.setdefault(r["variant"], {"copies": 0, "errors": 0, "events": 0, "lockups": 0, "relocks": 0,
                                              "sat": 0, "copies_with_errors": 0})
            s["copies"] += 1
            for f in ("errors", "events", "lockups", "relocks", "sat"):
                s[f] += r[f]
            s["copies_with_errors"] += r["errors"] > 0 or r["sat"] > 0
        return dict(sorted(out.items(), key=lambda kv: VARIANTS.index(kv[0])))


CSV_COLS = ["host_time", "kind", "epoch", "uptime_s", "tj_c", "vccint_mv", "cfgmclk_khz", "storm_mode", "copy",
            "variant", "cls", "dir", "errors", "events", "lockups", "relocks", "sat", "line", "copies", "build"]
_INT_COLS = ("epoch", "uptime_s", "cfgmclk_khz", "storm_mode", "copy", "errors", "events", "lockups", "relocks", "sat",
             "copies")
_FLOAT_COLS = ("tj_c", "vccint_mv")


def run_from_csv(path: Path) -> Run:
    """A Run rebuilt from a CSV this script wrote (follow() or --file --csv). C rows follow their E row; the H row
    carries the copy count only in CSVs written since brief 11c (older ones: the largest epoch is taken as complete)."""
    run = Run()
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            rec: dict = {k: row[k] for k in row if row.get(k) not in (None, "")}
            for k in _INT_COLS:
                if k in rec:
                    rec[k] = int(rec[k])
            for k in _FLOAT_COLS:
                if k in rec:
                    rec[k] = float(rec[k])
            run.add(rec)
    return run


def follow(src: TextIO, out_csv: Path | None, epoch_s: float, tj_limit: float, clock=time.monotonic) -> int:
    """Read a live stream until a stop rule fires (returns 2) or the stream ends (returns 0)."""
    run = Run()
    w = None
    fh = None
    if out_csv:
        new = not out_csv.exists()
        fh = out_csv.open("a", newline="")
        w = csv.DictWriter(fh, fieldnames=CSV_COLS, extrasaction="ignore")
        if new:
            w.writeheader()
    last_e = clock()
    try:
        for ln in src:
            now = clock()
            if not ln:
                if now - last_e > 2 * epoch_s + 30:
                    print("STOP: two epochs missed", file=sys.stderr)
                    return 2
                continue
            for r in parse_stream([ln]):
                run.add(r)
                if w:
                    w.writerow({"host_time": f"{time.time():.3f}", **r})
                    fh.flush()
                if r["kind"] == "E":
                    last_e = now
                    print(f"epoch {r['epoch']} uptime {r['uptime_s']} s Tj {r['tj_c']} C "
                          f"VCCINT {r['vccint_mv']} mV CFGMCLK {r['cfgmclk_khz']} kHz", file=sys.stderr)
                    if r["tj_c"] >= tj_limit:
                        print(f"STOP: Tj {r['tj_c']} C >= {tj_limit} C", file=sys.stderr)
                        return 2
                if r["kind"] == "S":
                    print(f"STOP: the rig stopped itself at Tj {r['tj_c']} C", file=sys.stderr)
                    return 2
            if now - last_e > 2 * epoch_s + 30:
                print("STOP: two epochs missed", file=sys.stderr)
                return 2
    finally:
        if fh:
            fh.close()
    return 0


def summary_text(run: Run) -> str:
    done = run.complete_epochs()
    rows = [f"epoch {done[-1]} (latest complete)" if done else "no complete epoch: latest record of each copy",
            f"{'variant':8} {'copies':>6} {'errors':>10} {'events':>12} {'lockups':>7} {'relocks':>7} "
            f"{'sat':>4} {'copies_w_err':>12}"]
    for v, s in run.per_variant().items():
        rows.append(f"{v:8} {s['copies']:6d} {s['errors']:10d} {s['events']:12d} {s['lockups']:7d} "
                    f"{s['relocks']:7d} {s['sat']:4d} {s['copies_with_errors']:12d}")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--port", help="serial device (read only; the board is never programmed from here)")
    src.add_argument("--file", type=Path, help="a saved UART log, or a CSV this script wrote (--csv)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--csv", type=Path, help="append records to this CSV")
    ap.add_argument("--epoch-s", type=float, default=60.0)
    ap.add_argument("--tj-limit", type=float, default=80.0)
    ap.add_argument("--summary", action="store_true", help="print the per-variant totals at the end")
    a = ap.parse_args(argv)
    if a.file:
        run = Run()
        text = a.file.read_text(errors="replace")
        if text.startswith("host_time,"):
            run = run_from_csv(a.file)
        else:
            for r in parse_stream(text.splitlines()):
                run.add(r)
        if a.csv and not text.startswith("host_time,"):
            with a.csv.open("w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=CSV_COLS, extrasaction="ignore")
                w.writeheader()
                for r in parse_stream(a.file.read_text(errors="replace").splitlines()):
                    w.writerow({"host_time": "", **r})
        print(summary_text(run))
        print(f"epochs {len(run.epochs)}  complete {len(run.complete_epochs())}  bad lines {run.bad}  "
              f"stop {run.stop}")
        return 0
    import serial  # pyserial; imported only for live runs

    with serial.Serial(a.port, a.baud, timeout=1.0) as ser:
        lines = (ser.readline().decode("ascii", "replace") for _ in iter(int, 1))
        return follow(lines, a.csv, a.epoch_s, a.tj_limit)


if __name__ == "__main__":
    sys.exit(main())
