"""python -m flow.eyescan run|probe|plot|page|compare|api|serve   (see flow/eyescan/__init__.py and README.md)"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from flow.eyescan import api, fake, page, scan, svg
from flow.eyescan import capture as C
from flow.eyescan import hw as H


SHIPPED_TXDIFF, MAX_CURSOR = H.SHIPPED_TXDIFF, H.MAX_CURSOR


def _cfg(a: argparse.Namespace) -> scan.ScanConfig:
    return scan.ScanConfig(target_ber=a.target_ber, min_errors=a.min_errors, hstep=a.hstep, vstep=a.vstep, vmax=a.vmax, vs_range=a.vs_range, equaliser=a.eq, label=a.label or "")


def _partial_writer(path: Path | None):
    if path is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")

    def cb(p: dict[str, Any], n: int, total: int) -> None:
        with path.open("a") as f:
            f.write(json.dumps({"n": n, "total": total, "point": p}, separators=(",", ":")) + "\n")
    return cb


def cmd_run(a: argparse.Namespace) -> int:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = _cfg(a)
    if a.tx_diff is not None and not 0 <= a.tx_diff <= SHIPPED_TXDIFF:
        print(f"--tx-diff {a.tx_diff} is above the shipped TXDIFFCTRL {SHIPPED_TXDIFF} (873 mVppd): refused, the optical module's input is protected by never exceeding it", file=sys.stderr)
        return 2
    for name, v in (("--tx-pre", a.tx_pre), ("--tx-post", a.tx_post)):
        if v is not None and not 0 <= v <= MAX_CURSOR:
            print(f"{name} {v} is above {MAX_CURSOR} (about 3.1 dB with UG576's table): refused", file=sys.stderr)
            return 2
    prog = _partial_writer(Path(a.partial) if a.partial else None)
    if a.fake:
        fb = fake.FakeBoard(seed=a.seed, lpm=(a.eq != "dfe"))
        cap = scan.run_scan(H.EyeHW(fb), cfg, conditions=lambda: {"temp_c": 50.0, "inside_roc": True, "note": "synthetic"}, link_ok=lambda: True, design=fake.design_info(),
                            synthetic=True, progress=prog)
    else:
        from designs.b96_kr260_10g.host import b96_bench as bb
        from designs.b96_kr260_10g.host import b96c_ppm as pp
        from flow import version_pin
        if not a.lock_text.startswith("96D:"):
            print("take _handoff/board.lock with a text starting '96D:' first and pass it as --lock-text", file=sys.stderr)
            return 2
        repo = Path(__file__).resolve().parents[2]
        t = bb.VivadoTcl(repo, a.serial, version_pin.vivado_path())
        try:
            b = bb.Board(t)
            if b.id() != 0x96A00001:
                print("wrong design loaded", file=sys.stderr)
                return 3
            eh = H.EyeHW(t, poll_s=0.0)
            eh.require_eyescan_build()
            import signal
            import time as _t

            def _term(signum, frame):  # noqa: ARG001 - SIGTERM/SIGHUP: unwind through the finally blocks (laser off first)
                raise SystemExit(128 + signum)
            signal.signal(signal.SIGTERM, _term)
            signal.signal(signal.SIGHUP, _term)
            tx0 = {"diff": H.SHIPPED_TXDIFF, "pre": 0, "post": 0}       # the baseline is the shipped drive, not whatever a killed earlier scan left
            try:
                b.laser(False)
                if not a.no_laser:
                    s0 = b.status()
                    b.laser(True)
                    _t.sleep(0.1)
                    s1 = b.status()
                    b.laser(False)
                    _t.sleep(0.1)
                    s2 = b.status()
                    if not (s0["rx_los"] == 1 and s1["rx_los"] == 0 and s2["rx_los"] == 1 and s0["mod_abs"] == 0):
                        print("laser polarity or pin functions differ from the open-source example (RX_LOS did not follow TX_DISABLE): stop, read the schematic", file=sys.stderr)
                        return 4
                    b.laser(True)
                    if not pp.relock(b):
                        print("link did not come up", file=sys.stderr)
                        return 5
                eh.set_tx_drive(a.tx_diff if a.tx_diff is not None else tx0["diff"], a.tx_pre if a.tx_pre is not None else 0, a.tx_post if a.tx_post is not None else 0)
                _t.sleep(0.3)
                cap = scan.run_scan(eh, cfg, conditions=lambda: pp.safe_conditions(t), link_ok=lambda: pp.link_ok(b), gt_info=lambda: {"buffers": pp.gt_buffers(t), "ddm": _safe(b.ddm)},
                                    design={"name": "b96_kr260_10g", "variant": "eyescan", "id": f"{b.id():08x}", "lock": a.lock_text}, progress=prog)
                cap["settings"]["ppm_offset"] = _safe(lambda: pp.measure_ppm(t, windows=2).get("ppm"))
            finally:
                try:
                    b.laser(False)                 # first, on every path
                finally:
                    try:
                        eh.set_tx_drive(tx0["diff"], tx0["pre"], tx0["post"])
                    except Exception as e:  # noqa: BLE001
                        print(f"TX drive not restored: {e}", file=sys.stderr)
        finally:
            t.close()
    path = C.save(cap, out / f"{a.name}.json")
    print(json.dumps({"capture": str(path), "points": len(cap["points"]), "restore_ok": cap["restore"]["ok"], "error": cap["run"]["error"], "synthetic": cap["synthetic"],
                      "eye": {k: cap and C.eye_at(cap, a.target_ber).get(k) for k in ("width_ui", "height_mv")}}, indent=1))
    return 0 if cap["restore"]["ok"] and not cap["run"]["error"] else 1


def _safe(f):
    try:
        return f()
    except Exception as e:  # noqa: BLE001 - recorded as text
        return f"unavailable: {type(e).__name__}: {e}"


def cmd_laser_off(a: argparse.Namespace) -> int:
    """Safety net for the owner's script: laser off (GT_CTRL bit 3), nothing else. Exit 0 only if the register reads back set."""
    from designs.b96_kr260_10g.host import b96_bench as bb
    from flow import version_pin
    t = bb.VivadoTcl(Path(__file__).resolve().parents[2], a.serial, version_pin.vivado_path())
    try:
        bb.Board(t).laser(False)
        return 0 if t.rd(H.R_GT_CTRL) & 0x8 else 1
    finally:
        t.close()


def cmd_probe(a: argparse.Namespace) -> int:
    """READ-ONLY look at the board: FEATURES, the DRP words the scan would save, the geometry and the equaliser. No DRP write, no laser, no reset."""
    from designs.b96_kr260_10g.host import b96_bench as bb
    from flow import version_pin
    from flow.eyescan import hw as HW
    repo = Path(__file__).resolve().parents[2]
    t = bb.VivadoTcl(repo, a.serial, version_pin.vivado_path())
    try:
        eh = HW.EyeHW(t)
        out: dict[str, Any] = {"id": f"{t.rd(0):08x}", "features": f"{eh.features():#x}", "eyescan_build": bool(eh.features() & HW.FEATURE_EYESCAN)}
        if out["eyescan_build"]:
            out["drp"] = {f"{x:#05x}": f"{eh.drp_read(x):#06x}" for x in HW.SAVE_ADDRS + [HW.A_RX_INT]}
            out["geometry"] = eh.geometry()
            out["equaliser"] = eh.equaliser()
            out["tx_drive"] = eh.get_tx_drive()
            c = int(out["drp"]["0x03c"], 16)
            out["eye_scan_enabled_by_build"] = (c >> 8) & 3 == 3
            out["rx_int_datawidth_is_32bit"] = (int(out["drp"]["0x066"], 16) & 3) == 1
            out["es_stat"] = f"{eh.rd(HW.R_STAT):#x}"
        print(json.dumps(out, indent=1))
        ok = out["eyescan_build"] and out.get("eye_scan_enabled_by_build") and out.get("rx_int_datawidth_is_32bit")
    finally:
        t.close()
    return 0 if ok else 1


def cmd_plot(a: argparse.Namespace) -> int:
    cap = C.load(a.capture)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(a.capture).stem
    (out / f"{stem}_eye.svg").write_text(svg.heatmap_svg(cap, a.ber))
    (out / f"{stem}_bathtub.svg").write_text(svg.bathtub_svg(cap, a.ber))
    print(f"wrote {out / (stem + '_eye.svg')} and {out / (stem + '_bathtub.svg')}")
    return 0


def cmd_page(a: argparse.Namespace) -> int:
    p = page.write_page([Path(x) for x in a.captures], a.output, a.label)
    print(f"wrote {p}")
    return 0


def cmd_compare(a: argparse.Namespace) -> int:
    ca, cb = C.load(a.a), C.load(a.b)
    ea, eb = C.eye_at(ca, a.ber), C.eye_at(cb, a.ber)

    def f(v, u, p):
        return "-" if v is None else f"{v:.{p}f} {u}"
    print(f"at BER {a.ber:g}            A ({ca['settings']['equaliser']})        B ({cb['settings']['equaliser']})")
    print(f"width            {f(ea.get('width_ui'), 'UI', 3):>16} {f(eb.get('width_ui'), 'UI', 3):>16}")
    print(f"height           {f(ea.get('height_mv'), 'mV', 0):>16} {f(eb.get('height_mv'), 'mV', 0):>16}")
    print(f"open points      {ea['counts']['open']:>16} {eb['counts']['open']:>16}")
    if ca.get("synthetic") or cb.get("synthetic"):
        print("NOTE: at least one capture is SYNTHETIC (offline model); this comparison is not a measurement")
    return 0


def cmd_api(a: argparse.Namespace) -> int:
    cap = C.load(a.capture)
    what = {"summary": lambda: api.summary(cap, a.ber), "eye": lambda: api.eye(cap, a.ber), "bathtub": lambda: api.bathtub(cap, a.axis), "surface": lambda: api.surface(cap),
            "margin": lambda: api.margin(cap, a.ber, a.min_width_ui, a.min_height_mv), "page": lambda: api.page_data(cap)}[a.what]()
    print(json.dumps(what, indent=None if a.what in ("surface", "page") else 1))
    return 0


def _partial_capture(path: Path) -> dict[str, Any]:
    """Build a capture-shaped dict from a partial JSONL (header in <path>.header.json if present)."""
    pts = []
    for line in path.read_text().splitlines():
        if line.strip():
            pts.append(json.loads(line)["point"])
    hdr_p = path.with_suffix(".header.json")
    hdr = json.loads(hdr_p.read_text()) if hdr_p.exists() else {}
    hdr["points"] = pts
    return hdr


def cmd_serve(a: argparse.Namespace) -> int:
    import http.server
    src = Path(a.source)

    def data() -> bytes:
        cap = C.load(src) if src.suffix == ".json" and not src.name.endswith(".partial.jsonl") else _partial_capture(src)
        return json.dumps(api.page_data(cap)).encode()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/api/data"):
                body, ctype = data(), "application/json"
            else:
                cap = C.load(src) if not src.name.endswith(".jsonl") else _partial_capture(src)
                body, ctype = page.build_page([cap]).replace("var LIVE=(", "var LIVE=('/api/data'||").encode(), "text/html"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            pass
    srv = http.server.HTTPServer(("127.0.0.1", a.port), Handler)
    print(f"serving on http://127.0.0.1:{a.port}/ (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m flow.eyescan", description="On-chip RX eye scan: run, plot, page, compare, api, serve.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="scan (board, or --fake for the offline synthetic eye)")
    r.add_argument("--out", required=True)
    r.add_argument("--name", default="eye")
    r.add_argument("--label", default="")
    r.add_argument("--fake", action="store_true", help="SYNTHETIC offline eye (flow/eyescan/fake.py): not a measurement")
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--serial")
    r.add_argument("--lock-text", default="")
    r.add_argument("--eq", choices=["keep", "lpm", "dfe"], default="keep")
    r.add_argument("--target-ber", type=float, default=1e-9)
    r.add_argument("--min-errors", type=int, default=10)
    r.add_argument("--hstep", type=int, default=2)
    r.add_argument("--vstep", type=int, default=8)
    r.add_argument("--vmax", type=int, default=120)
    r.add_argument("--vs-range", type=int, default=0, choices=[0, 1, 2, 3])
    r.add_argument("--tx-diff", type=int, default=None, help="TXDIFFCTRL (5 bits); never above the shipped 24 (873 mVppd)")
    r.add_argument("--tx-pre", type=int, default=None)
    r.add_argument("--tx-post", type=int, default=None)
    r.add_argument("--no-laser", action="store_true", help="do not touch the laser (the caller has the link up)")
    r.add_argument("--partial", default=None, help="write each point to this JSONL as it is taken (for `serve`)")
    r.set_defaults(f=cmd_run)
    lo = sub.add_parser("laser-off", help="switch the laser off (safety net) and verify")
    lo.add_argument("--serial", required=True)
    lo.set_defaults(f=cmd_laser_off)
    pr = sub.add_parser("probe", help="READ-ONLY check of the board's eye-scan build and the DRP words (no writes, no laser)")
    pr.add_argument("--serial", required=True)
    pr.set_defaults(f=cmd_probe)
    p = sub.add_parser("plot", help="static heat map and bathtub SVG")
    p.add_argument("capture")
    p.add_argument("-o", "--out", default=".")
    p.add_argument("--ber", type=float, default=1e-9)
    p.set_defaults(f=cmd_plot)
    g = sub.add_parser("page", help="interactive HTML page (one or two captures)")
    g.add_argument("captures", nargs="+")
    g.add_argument("-o", "--output", required=True)
    g.add_argument("--label", action="append")
    g.set_defaults(f=cmd_page)
    c = sub.add_parser("compare", help="width, height and open points of two captures at a depth")
    c.add_argument("a")
    c.add_argument("b")
    c.add_argument("--ber", type=float, default=1e-9)
    c.set_defaults(f=cmd_compare)
    i = sub.add_parser("api", help="JSON from a capture")
    i.add_argument("capture")
    i.add_argument("--what", choices=["summary", "eye", "bathtub", "surface", "margin", "page"], default="summary")
    i.add_argument("--ber", type=float, default=1e-9)
    i.add_argument("--axis", default="h")
    i.add_argument("--min-width-ui", type=float, default=0.3)
    i.add_argument("--min-height-mv", type=float, default=30.0)
    i.set_defaults(f=cmd_api)
    s = sub.add_parser("serve", help="serve the page and a live JSON feed from a capture or a partial JSONL")
    s.add_argument("source")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(f=cmd_serve)
    a = ap.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
