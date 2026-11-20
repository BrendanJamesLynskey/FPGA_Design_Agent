#!/usr/bin/env python3
"""Find where the valid data sits in GTHE4's 160-bit ES_SDATA_MASK on the KR260 eyescan build (planner, 2026-11-20).

Why: the 2026-11-20 re-run with the ten-word masks counted samples (the 96D2 fix works) but saturated the error counter at every
point, eye centre included (65535 errors in ~2050 samples ~ every compared bit wrong): the unmasked window of ES_SDATA_MASK
{80'b1, 32'b0, 48'b1} is on the wrong bits. This probe slides the unmasked window and measures, per candidate, the eye centre
and two points near the edges (prescale 0, a few ms each). The right window: centre err 0 with the sample counter saturated,
edges with errors. Control: everything masked must give err 0 everywhere (if not, the mask is not the cause).

Board use (owner runs it): laser on for well under a minute in total; DRP eye-scan words written back to the build's values
(from the morning probe.json) at the end, on every path; laser off first on every path; TX drive back to the shipped value.

    PYTHONPATH=<this worktree> python3 tools/eyescan_mask_probe.py --serial <cable> --baseline <probe.json> --out <dir> \
        --stale-lock "<exact text of a stale 96D: lock to take over>"
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from designs.b96_kr260_10g.host import b96_bench as bb  # noqa: E402
from designs.b96_kr260_10g.host import b96c_ppm as pp  # noqa: E402
from designs.b96_kr260_10g.model import eyescan as tw  # noqa: E402
from flow import version_pin  # noqa: E402
from flow.eyescan import hw as H  # noqa: E402

LOCK = Path("/home/brendan/Claude_sandbox/_handoff/board.lock")
ALL = (1 << 160) - 1


def window_mask(lo: int, width: int) -> int:
    """1 = masked. Unmask bits [lo+width-1 : lo]."""
    return ALL & ~(((1 << width) - 1) << lo)


def candidates() -> list[tuple[str, int]]:
    c = [("all_masked", ALL)]
    c += [(f"w32_lo{lo}", window_mask(lo, 32)) for lo in range(0, 129, 8)]
    c += [(f"w16_lo{lo}", window_mask(lo, 16)) for lo in range(0, 145, 16)]
    c += [("w80_lo0", window_mask(0, 80)), ("w80_lo80", window_mask(80, 80))]
    return c


def take_lock(text: str, stale: str) -> None:
    if LOCK.exists():
        cur = LOCK.read_text().strip()
        if cur != stale.strip():
            raise SystemExit(f"board.lock is held ('{cur}'); pass its exact text as --stale-lock only if it is a dead session's")
        LOCK.write_text(text + "\n")
    else:
        with open(LOCK, "x") as f:
            f.write(text + "\n")


def release_lock(text: str) -> None:
    if LOCK.exists() and LOCK.read_text().strip() == text:
        LOCK.unlink()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", required=True)
    ap.add_argument("--baseline", required=True, help="probe.json read right after programming (the build's DRP values)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--stale-lock", default="")
    ap.add_argument("--edge", type=int, default=28, help="horizontal counts for the edge points (32 = half a UI)")
    a = ap.parse_args()

    base = {int(k, 16): int(v, 16) for k, v in json.load(open(a.baseline))["drp"].items()}
    missing = [f"{x:#05x}" for x in H.SAVE_ADDRS if x not in base]
    if missing:
        raise SystemExit(f"baseline lacks {missing}")
    if (base[tw.A_ES_CONTROL] >> 10) & 0x3F:
        raise SystemExit("baseline ES_CONTROL has run/arm set; not a build value")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    lock_text = f"96D: mask probe (planner), {time.strftime('%H:%M')}, expected end +15min"
    take_lock(lock_text, a.stale_lock)

    def _term(signum, frame):  # noqa: ARG001
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGHUP, _term)

    res: dict = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "lock": lock_text, "edge_counts": a.edge, "rows": []}
    t = bb.VivadoTcl(ROOT, a.serial, version_pin.vivado_path())
    b = bb.Board(t)
    eh = H.EyeHW(t)
    try:
        if b.id() != 0x96A00001:
            raise SystemExit("wrong design loaded")
        eh.require_eyescan_build()
        b.laser(False)
        # put the build's values back first (a killed scan may have left ES_CONTROL running or other masks)
        for adr in H.SAVE_ADDRS:
            eh.drp_write(adr, base[adr])
        eh.setup()                      # saves the (now build) values, checks enables and width, writes the 96D2 masks
        b.laser(True)
        if not pp.relock(b):
            raise SystemExit("link did not come up")
        eh.set_tx_drive(H.SHIPPED_TXDIFF, 0, 0)
        time.sleep(0.3)
        res["link_before"] = pp.link_ok(b)
        for name, m in candidates():
            w = H.words_of(m)
            for i in range(H.N_WORDS):
                eh.drp_write(tw.SDATA_MASK_ADDRS[i], w[i])
            rb = [eh.drp_read(tw.SDATA_MASK_ADDRS[i]) for i in range(H.N_WORDS)]
            row = {"name": name, "mask_hex": f"{m:040x}", "readback_ok": rb == w, "points": {}}
            for label, h in (("centre", 0), ("left", -a.edge), ("right", a.edge)):
                p = eh.point(h, 0, 0, 0, 0, timeout_s=1.0)
                row["points"][label] = {k: p[k] for k in ("err", "samp", "tmo", "status")}
            res["rows"].append(row)
            c, l, r = (row["points"][k] for k in ("centre", "left", "right"))
            print(f"{name:12s} centre err {c['err']:5d} samp {c['samp']:5d} | left err {l['err']:5d} samp {l['samp']:5d} | right err {r['err']:5d} samp {r['samp']:5d}"
                  f"{'' if row['readback_ok'] else '  READBACK MISMATCH'}", flush=True)
        res["link_after"] = pp.link_ok(b)
    finally:
        try:
            b.laser(False)
            res["laser_off"] = bool(t.rd(H.R_GT_CTRL) & 0x8)
        finally:
            try:
                eh.set_tx_drive(H.SHIPPED_TXDIFF, 0, 0)
                res["restore"] = eh.restore() if eh.saved else {"ok": False, "reason": "setup not reached"}
            finally:
                t.close()
                release_lock(lock_text)
                res["ended"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                (out / "mask_probe.json").write_text(json.dumps(res, indent=1))
                print(f"laser_off={res.get('laser_off')} restore_ok={res.get('restore', {}).get('ok')} -> {out / 'mask_probe.json'}")
    good = [r["name"] for r in res["rows"] if r["points"]["centre"]["err"] == 0 and r["points"]["centre"]["samp"] > 0 and r["name"] != "all_masked"]
    print("centre error-free candidates:", good)
    return 0


if __name__ == "__main__":
    sys.exit(main())
