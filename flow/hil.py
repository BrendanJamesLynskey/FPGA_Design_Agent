#!/usr/bin/env python3
"""The hardware-in-the-loop stage (brief 30): run a design's hil.yaml on the attached board after the board build.

    python3 flow/hil.py designs/<name> [--out build/hil/<name>] [--skip audio,xadc_vs_jtag] [--no-program]

Steps: take _handoff/board.lock (own text; refuses if another session holds the board), program the SRAM through
flow/program.py (power gate, build-stamp check, never flash), run every check in the design's hil.yaml, release the lock
and write <out>/hil.json. Each check returns {pass, measured, expected, tolerance, ...}; a failing run also gets a
`feedback` list: one plain line per failed check giving measured against expected, for the repair loop to read.

The checks use the Python models in hil/instruments/models.py (the same ones the simulation tests use). A check whose
instrument is not connected is reported `skipped` with the reason, never as a pass.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flow import hw, program  # noqa: E402
from hil.instruments import audio, jtag_sysmon, models  # noqa: E402
from hil.instruments import shell_instruments as si  # noqa: E402
from hil.instruments.board_lock import BoardBusy, BoardLock  # noqa: E402

ROOT = hw.ROOT
PREFIX = os.environ.get("HIL_LOCK_PREFIX", "FPGA hil")


class Skipped(Exception):
    """The check cannot run here (an instrument is not connected); the message says what is missing."""


class Ctx:
    def __init__(self, sh: Any, spec: dict, out: Path) -> None:
        self.sh, self.spec, self.out = sh, spec, out
        self.W = si.WINDOW


def _res(ok: bool, measured: Any, expected: Any, tol: Any = None, **kw: Any) -> dict[str, Any]:
    return {"pass": bool(ok), "measured": measured, "expected": expected, "tolerance": tol, **kw}


def chk_design_id(c: Ctx, k: dict) -> dict:
    v = c.sh.read(0)
    text = v.to_bytes(4, "big").decode("latin-1")
    return _res(text == k["expect"], text, k["expect"])


def chk_frame_crc(c: Ctx, k: dict) -> dict:
    c.sh.write(c.W + 0, 1)                                   # tone on, no pixel fault
    fc = si.FrameCrcHost(c.sh)
    want = models.frame_crc32(si.lfsr_frame(), 24)
    fc.set_expect(want)
    time.sleep(0.3)
    m0 = fc.read()["mismatches"]
    time.sleep(0.5)
    r = fc.read()
    ok = r["crc"] == want and r["pix"] == 128 and r["sum"] == sum(si.lfsr_frame()) & 0xFFFFFFFF and r["mismatches"] == m0
    return _res(ok, {"crc": f"{r['crc']:08x}", "pix": r["pix"], "new_mismatches": r["mismatches"] - m0, "frames": r["frames"]},
                {"crc": f"{want:08x}", "pix": 128, "new_mismatches": 0}, "exact")


def chk_frame_crc_fault(c: Ctx, k: dict) -> dict:
    fc = si.FrameCrcHost(c.sh)
    want = models.frame_crc32(si.lfsr_frame(), 24)
    fc.set_expect(want)
    m0 = fc.read()["mismatches"]
    c.sh.write(c.W + 0, 3)                                   # flip one pixel bit per frame
    time.sleep(0.5)
    r = fc.read()
    c.sh.write(c.W + 0, 1)
    ok = r["mismatches"] > m0 and r["crc"] != want
    return _res(ok, {"new_mismatches": r["mismatches"] - m0, "crc_equals_model": r["crc"] == want},
                {"new_mismatches": ">0", "crc_equals_model": False}, "exact", note="the seeded fault must be seen")


def chk_freq(c: Ctx, k: dict) -> dict:
    fd = si.FreqDutyHost(c.sh)
    g0 = fd.read()["gates"]
    t0 = time.time()
    while fd.read()["gates"] < g0 + 2:
        if time.time() - t0 > 5:
            raise TimeoutError("no gate completed in 5 s")
    r = fd.read()
    return _res(abs(r["freq_hz"] - k["expect_hz"]) <= k["tolerance_hz"], round(r["freq_hz"], 2), k["expect_hz"], k["tolerance_hz"],
                edges=r["edges"], duty=round(r["duty"], 4))


def chk_la_dds(c: Ctx, k: dict) -> dict:
    c.sh.write(c.W + 1, 89463225)
    c.sh.write(c.W + 2, 0x20)                                # sine, shift 2
    la = si.LogicAnalyserHost(c.sh)
    got = [v - 65536 if v & 0x8000 else v for v in la.capture(0, 0, pre=0)]
    n0 = models.dds_find_offset(got, 89463225, 0, 32, 8, 16, 2)
    return _res(n0 is not None, f"{len(got)} samples, a run of the DDS output starting at tick {n0}" if n0 is not None else "no matching run",
                "a contiguous run of the DDS model (start tick unknown)", "exact", first_samples=got[:6])


def chk_la_pretrigger(c: Ctx, k: dict) -> dict:
    la = si.LogicAnalyserHost(c.sh)
    got = la.capture(0x8000, 0x8000, pre=8, edge=True)       # rising edge of bit 15 (the sine goes negative)
    ok = (got[8] & 0x8000) != 0 and (got[7] & 0x8000) == 0
    return _res(ok, {"sample7_sign": got[7] >> 15, "sample8_sign": got[8] >> 15}, {"sample7_sign": 0, "sample8_sign": 1}, "exact")


def chk_xadc(c: Ctx, k: dict) -> dict:
    fab = si.XadcHost(c.sh).read()
    jt = jtag_sysmon.read(c.out / "sysmon")
    tol = k["tolerance"]
    diffs = {n: fab[n] - jt[n] for n in tol}
    ok = all(abs(diffs[n]) <= tol[n] for n in tol) and fab["tj_c"] <= k["limits"]["tj_c_max"]
    return _res(ok, {n: round(fab[n], 4) for n in tol}, {n: round(jt[n], 4) for n in tol}, tol,
                differences={n: round(d, 4) for n, d in diffs.items()}, note="measured = fabric DRP readout, expected = JTAG sysmon")


def chk_audio(c: Ctx, k: dict) -> dict:
    wav = c.out / "tone.wav"
    try:
        audio.record(wav, seconds=4.0, device=k["device"])
    except Exception as e:                                   # no capture device, or busy
        raise Skipped(f"audio capture failed: {e}")
    a, fs = audio.read_wav(wav)
    m = audio.measure_tone(a[:, k["channel"]], fs, k["f_expect_hz"])
    r = audio.tone_check(m, k["f_expect_hz"], k["f_tol_hz"], k["min_level_dbfs"], k["max_thd_percent"], k["min_sinad_db"])
    return _res(r["pass"], {n: round(v, 2) for n, v in m.items()},
                {"freq_hz": k["f_expect_hz"], "min_level_dbfs": k["min_level_dbfs"], "max_thd_percent": k["max_thd_percent"],
                 "min_sinad_db": k["min_sinad_db"]}, {"f_tol_hz": k["f_tol_hz"]}, failed=[n for n, ok in r["checks"].items() if not ok])


CHECKS: dict[str, Callable[[Ctx, dict], dict]] = {
    "design_id": chk_design_id, "frame_crc": chk_frame_crc, "frame_crc_fault": chk_frame_crc_fault, "freq": chk_freq,
    "la_dds": chk_la_dds, "la_pretrigger": chk_la_pretrigger, "xadc_vs_jtag": chk_xadc, "audio_tone": chk_audio,
}


def feedback_line(name: str, r: dict) -> str:
    return f"HIL check '{name}' failed: measured {json.dumps(r.get('measured'))}, expected {json.dumps(r.get('expected'))}" + \
        (f", tolerance {json.dumps(r['tolerance'])}" if r.get("tolerance") is not None else "") + \
        (f" (failed: {', '.join(r['failed'])})" if r.get("failed") else "")


def run(design: Path, out: Path, skip: set[str], do_program: bool = True) -> dict[str, Any]:
    from shell.host.fpga_shell import FpgaShell
    spec = yaml.safe_load((design / "hil.yaml").read_text())
    out.mkdir(parents=True, exist_ok=True)
    res: dict[str, Any] = {"design": spec["design"], "board": spec["board"], "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "checks": {}}
    lock = BoardLock(f"{PREFIX}: {design.name} HIL run, {time.strftime('%H:%M')}, expected end +10 min")
    held = os.environ.get("HIL_LOCK_HELD", "")           # a session that already holds the board lock says so (its prefix)
    if held and lock.path.is_file() and lock.path.read_text().startswith(held):
        lock = None                                      # keep it; the caller releases it
    else:
        try:
            lock.take()
        except BoardBusy as e:
            res.update({"pass": False, "error": str(e)})
            return res
    try:
        if do_program:
            res["program"] = program.program(design, spec.get("variant", "base"), spec["board"], out / "program")
            if not res["program"]["pass"]:
                raise hw.HwError("programming failed")
            time.sleep(1.0)
        b = hw.load_board(spec["board"])
        with FpgaShell.open(b["uart"]) as sh:
            ctx = Ctx(sh, spec, out)
            for k in spec["checks"]:
                n = k["name"]
                if n in skip:
                    res["checks"][n] = {"pass": None, "skipped": "skipped by the caller"}
                    continue
                try:
                    r = CHECKS[k["type"]](ctx, k)
                except Skipped as e:
                    r = {"pass": None, "skipped": str(e)}
                except Exception as e:                       # a check that cannot run is a failure, with the reason
                    r = {"pass": False, "measured": f"{type(e).__name__}: {e}", "expected": "the check to run"}
                r["path"] = k["path"]
                res["checks"][n] = r
    except (hw.HwError, OSError) as e:
        res["error"] = str(e)
    finally:
        res["lock_released"] = lock.release() if lock else False
    done = [r for r in res["checks"].values() if r["pass"] is not None]
    res["pass"] = "error" not in res and bool(done) and all(r["pass"] for r in done)
    res["feedback"] = [feedback_line(n, r) for n, r in res["checks"].items() if r["pass"] is False]
    (out / "hil.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("design", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--skip", default="")
    ap.add_argument("--no-program", action="store_true")
    a = ap.parse_args(argv)
    design = (ROOT / a.design).resolve() if not a.design.is_absolute() else a.design
    out = a.out or ROOT / "build" / "hil" / design.name
    r = run(design, out, set(filter(None, a.skip.split(","))), not a.no_program)
    for n, c in r["checks"].items():
        print(f"{'PASS' if c['pass'] else 'SKIP' if c['pass'] is None else 'FAIL'}  {n}")
    for l in r.get("feedback", []):
        print(l)
    print("HIL", "PASS" if r["pass"] else "FAIL", r.get("error", ""))
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
