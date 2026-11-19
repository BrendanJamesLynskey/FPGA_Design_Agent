"""Stage 3 bench driver for the KR260 10G design (brief 96): register access, bring-up steps, the loop measurement and the link-restart
distribution. NOT YET RUN ON A BOARD. The method is the one pre-registered in docs/design.md section 6 and docs/board_run_plan.md.

Transport: `Board` takes any object with rd(addr) -> int and wr(addr, value). `VivadoTcl` is the real one (a `vivado -mode tcl` child holding the
hardware manager open); tests use a fake. Nothing here turns the laser on except `laser(True)`, which `run_all` calls only after the
polarity step has passed, and `run_all` refuses to start unless it is given the board lock text it took."""

from __future__ import annotations

import json
import math
import statistics
import subprocess
import time
from pathlib import Path
from typing import Protocol

from designs.b96_kr260_10g.host import sfp_i2c

CLK_NS = 1000.0 / 161.1328125            # one user-clock period, 6.2058 ns
TX = dict(n_order=0, n_feed=1, n_probe=2, n_test=3, poisoned=4, dropped=5, underrun=6, late=7, stale=8, go=9, t_tx_feed=10, t_tx_probe=11,
          t_tx_order=12, t_rx_feed=13, t_rx_probe=14, t_rx_order=15, e_last=16, e_min=17, e_max=18, e_cnt=19, l_last=20, l_min=21,
          l_max=22, l_cnt=23, d_last=24, ts=25)
RX = dict(lock=0, slip=1, loss=2, lock_ev=3, sh=4, type=5, os=6, frames=7, good=8, bad=9, err=10, fired=11, blocked=12, toolong=13,
          last_len=14, lock_clk=15, order_ok=16, order_bad=17,
          # brief 96C: rate matching (elastic buffer) and the frequency counter; they read 0 on a bitstream built before 96C
          rm_wr=18, rm_ovf=19, rm_ins=20, rm_del=21, rm_stall=22, rm_out=23, rm_drain=24, rm_fmin=25, rm_fmax=26, f_delta=27, f_win=28)
NRXW, NTXW = 29, 26
#: Safety counters that must be 0 in every restart (TX side from TXV, RX side from RXV); `blocked` is recorded but is not a failure on its own
#: (a blocked hit means one order fewer, which the order-count check catches). `order_bad` (97C) counts returned orders whose content, length or
#: FCS did not match what the rule decided; `order_ok` must equal the expected order count (checked below), so a silent order cannot pass either.
SAFETY_TX = ("poisoned", "dropped", "underrun", "late", "stale")
SAFETY_RX = ("bad", "err", "toolong", "order_bad")
GT_STAT_BITS = dict(tx_done=0, rx_done=1, pgood=2, cdr_lock=3, txpma=4, rxpma=5, cdr_stable=8, pcs_lock=9, mod_abs=10, rx_los=11, tx_fault=12)


class Transport(Protocol):
    def rd(self, addr: int) -> int: ...
    def wr(self, addr: int, value: int) -> None: ...


class VivadoTcl:
    """A `vivado -mode tcl` child with the hardware manager open on one cable (selected by serial, never 'the first target')."""

    def __init__(self, repo: Path, cable_serial: str, vivado: str) -> None:
        self.p = subprocess.Popen([vivado, "-mode", "tcl", "-nojournal", "-nolog"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.cmd(f"set ::env(FDA_ROOT) {repo}")
        self.cmd(f"source {repo}/designs/b96_kr260_10g/host/b96_regs.tcl")
        self.cmd(f"b58a_open {cable_serial}")

    def cmd(self, line: str) -> str:
        assert self.p.stdin and self.p.stdout
        # A piped `vivado -mode tcl` does not echo a command's result, and an error would otherwise pass silently: wrap
        # each line so its result or error comes back on a tagged line (measured on the KR260, 2026-11-17).
        self.p.stdin.write("if {[catch {" + line + "} __r]} {puts \"__ERR__ $__r\"} else {puts \"__RES__ $__r\"}\nputs __DONE__\n")
        self.p.stdin.flush()
        out, res, err = [], None, None
        while True:
            l = self.p.stdout.readline()
            if not l:
                raise RuntimeError("vivado closed")
            t = l.rstrip()
            if t.endswith("__DONE__"):
                break
            if t.startswith("__RES__"):
                res = t[8:]
            elif t.startswith("__ERR__"):
                err = t[8:]
            else:
                out.append(t)
        if err is not None:
            raise RuntimeError(f"vivado: {line}: {err}")
        return "\n".join(out + ([res] if res else []))

    def rd(self, addr: int) -> int:
        return int(self.cmd(f"b96_rd {addr:#x}").strip().splitlines()[-1], 16)

    def wr(self, addr: int, value: int) -> None:
        self.cmd(f"b96_wr {addr:#x} {value:#x}")

    def close(self) -> None:
        try:
            self.cmd("b96_laser_off")
            self.cmd("b58a_close")
        finally:
            self.p.terminate()


class Board:
    def __init__(self, t: Transport) -> None:
        self.t = t

    # ---- basics
    def id(self) -> int:
        return self.t.rd(0x000)

    def status(self) -> dict:
        s = self.t.rd(0x014)
        return {k: (s >> b) & 1 for k, b in GT_STAT_BITS.items()}

    def laser(self, on: bool) -> None:
        c = self.t.rd(0x00C)
        self.t.wr(0x00C, (c & ~0x8) if on else (c | 0x8))

    def set_loopback(self, mode: int) -> None:
        c = self.t.rd(0x00C)
        self.t.wr(0x00C, (c & ~0x7) | mode)
        self.reset(rx_dp=True)

    def reset(self, all_=False, rx_dp=False, rx_pll=False, tx_dp=False) -> None:
        self.t.wr(0x010, (1 if all_ else 0) | (4 if rx_pll else 0) | (8 if tx_dp else 0) | (16 if rx_dp else 0))

    def wait(self, pred, timeout_s: float, poll_s: float = 0.05) -> bool:
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if pred(self.status()):
                return True
            time.sleep(poll_s)
        return False

    def snapshot(self) -> tuple[dict, dict]:
        self.t.wr(0x018, 4)
        tx = {k: self.t.rd(0x200 + 4 * i) for k, i in TX.items()}
        rx = {k: self.t.rd(0x100 + 4 * i) for k, i in RX.items()}
        return tx, rx

    def clear(self) -> None:
        self.t.wr(0x018, 1)

    def configure(self, *, arm=False, kill=False, trade=True, kind=2, length=66, inst=1, price=9950, interval=2000, count=1, thr=9975, qty=100) -> None:
        self.t.wr(0x060, thr); self.t.wr(0x064, qty)
        self.t.wr(0x068, (1 if arm else 0) | (2 if kill else 0) | (4 if trade else 0) | (kind << 4))
        self.t.wr(0x06C, (inst << 16) | length); self.t.wr(0x070, price); self.t.wr(0x074, interval); self.t.wr(0x078, count)

    def run(self, wait_s: float = 0.05) -> None:
        self.t.wr(0x018, 2)
        time.sleep(wait_s)

    # ---- the module's I2C (laser state is not changed here; a powered module answers on I2C)
    def i2c(self) -> sfp_i2c.I2CMaster:
        def drive(scl: int, sda: int) -> None:
            self.t.wr(0x080, (0 if scl else 1) | (0 if sda else 2))

        def sda() -> int:
            return (self.t.rd(0x080) >> 9) & 1
        return sfp_i2c.I2CMaster(drive, sda)

    def module_info(self) -> dict:
        m = self.i2c()
        a0 = m.read(0x50, 0, 64)
        return {"identifier": a0[0], "vendor": a0[20:36].decode("ascii", "replace").strip(), "part": a0[40:56].decode("ascii", "replace").strip(),
                "wavelength_nm": int.from_bytes(a0[60:62], "big"), "diag_monitoring_type_byte92": m.read(0x50, 92, 1)[0]}

    def ddm(self) -> dict:
        return sfp_i2c.ddm(self.i2c().read(0x51, 96, 10))


def clocks_to_ns(c: float) -> float:
    return c * CLK_NS


def summarise(values: list[int]) -> dict:
    """Min, max, median, mean and the histogram of a list of clock counts (the link-restart distribution)."""
    if not values:
        return {"n": 0}
    h: dict[int, int] = {}
    for v in values:
        h[v] = h.get(v, 0) + 1
    return {"n": len(values), "min": min(values), "max": max(values), "median": statistics.median(values), "mean": statistics.fmean(values),
            "histogram": dict(sorted(h.items())), "min_ns": clocks_to_ns(min(values)), "max_ns": clocks_to_ns(max(values))}


def settled_snapshot(b: Board, expected_orders: int, tries: int = 10, wait_s: float = 0.02) -> tuple[dict, dict]:
    """A snapshot taken once the run has stopped moving. The run command returns before the generator has finished, and `late`, `poisoned`, `bad`
    and `err` land after `n_order` and `fired` do, so the test is: both order counts reached AND two consecutive snapshots agree on every
    counter except the free-running ones (`ts`, `d_last`). After `tries` retakes the last snapshot is returned; a shortfall is then reported
    by `safety_verdict`, never hidden."""
    skip = ("ts", "d_last")
    def key(tx: dict, rx: dict) -> tuple:
        return tuple(sorted((k, v) for k, v in {**{"t_" + k: v for k, v in tx.items() if k not in skip}, **{"r_" + k: v for k, v in rx.items()}}.items()))
    prev = None
    tx, rx = b.snapshot()
    for _ in range(tries):
        cur = key(tx, rx)
        if prev == cur and tx["n_order"] >= expected_orders and rx["fired"] >= expected_orders:
            break
        prev = cur
        time.sleep(wait_s)
        tx, rx = b.snapshot()
    return tx, rx


def safety_verdict(snapshots: list[dict | None], expected_orders: int, n_restarts: int) -> dict:
    """The acceptance test for the latency variants that fire combinationally. `snapshots` has one entry per restart: {"tx": {...}, "rx": {...}},
    or None for a restart whose link did not lock (nothing was read, so nothing can be vouched for). `ok` is true only when there are n_restarts
    snapshots, every counter is present, the nine safety counters are 0 in every restart and orders sent, fired and returned intact
    (`order_ok`, the hardware's content check) all equal the expected count in every restart. Every failing counter is named, with the restart it failed in."""
    reasons: list[str] = []
    if not (isinstance(n_restarts, int) and n_restarts >= 1 and isinstance(expected_orders, int) and expected_orders >= 1):
        return {"ok": False, "failing_counters": [], "reasons": [f"nothing to judge: restarts={n_restarts!r}, expected orders={expected_orders!r}"]}
    failing: set[str] = set()
    bad_restarts: list[dict] = []
    sums = {k: 0 for k in SAFETY_TX + SAFETY_RX + ("blocked", "n_order", "fired", "order_ok")}
    unreadable = [i for i, sn in enumerate(snapshots) if sn is None]
    if len(snapshots) != n_restarts:
        reasons.append(f"{len(snapshots)} snapshots for {n_restarts} restarts")
    if unreadable:
        reasons.append(f"{len(unreadable)} restarts have no counters (link did not lock): {unreadable[:10]}")
    for i, sn in enumerate(snapshots):
        if sn is None:
            continue
        vals: dict[str, int] = {}
        missing = [k for k in SAFETY_TX + ("n_order",) if k not in sn.get("tx", {})] + [k for k in SAFETY_RX + ("blocked", "fired", "order_ok") if k not in sn.get("rx", {})]
        if missing:
            reasons.append(f"restart {i}: counters not read: {missing}")
            failing.update(missing)
            continue
        for k in SAFETY_TX + ("n_order",):
            vals[k] = sn["tx"][k]
        for k in SAFETY_RX + ("blocked", "fired", "order_ok"):
            vals[k] = sn["rx"][k]
        for k, v in vals.items():
            sums[k] += v
        nonzero = {k: vals[k] for k in SAFETY_TX + SAFETY_RX if vals[k] != 0}
        short = {}
        if vals["n_order"] != expected_orders:
            short["n_order"] = vals["n_order"]
        if vals["fired"] != expected_orders:
            short["fired"] = vals["fired"]
        if vals["order_ok"] != expected_orders:
            short["order_ok"] = vals["order_ok"]
        if nonzero or short:
            bad_restarts.append({"restart": i, "nonzero": nonzero, "order_count_wrong": short, "n_order": vals["n_order"], "fired": vals["fired"], "blocked": vals["blocked"]})
            failing.update(nonzero)
            failing.update(short)
    if bad_restarts:
        reasons.append(f"{len(bad_restarts)} restarts with a non-zero safety counter or a wrong order count; failing: {sorted(failing)}")
    ok = not reasons and not failing
    return {"ok": ok, "failing_counters": sorted(failing), "reasons": reasons, "expected_orders_per_restart": expected_orders,
            "restarts": n_restarts, "restarts_checked": len(snapshots) - len(unreadable), "restarts_unreadable": unreadable, "sums": sums,
            "orders": {"expected_total": expected_orders * n_restarts, "sent_total": sums["n_order"], "fired_total": sums["fired"]},
            "bad_restarts": bad_restarts}


def restart_distribution(b: Board, n: int = 100, probes_per_link: int = 5, timeout_s: float = 5.0) -> dict:
    """Restart the receive datapath n times; after each link-up send probe frames and the trading loop (frames and orders); collect E, L and the lock clocks.
    The brief's method (design.md section 6): at least 100 restarts; min, max and distribution of E (echo) and L (loop) per link-up.
    Brief 97B: the full TX and RX counter snapshot of every restart is kept and judged by `safety_verdict` (`clear()` runs after the link locks, so
    a counter that moved during the relock itself is not seen: the counters judge the traffic of the run, not the restart transient)."""
    E, L, lock_clk, fails = [], [], [], 0
    snapshots: list[dict | None] = []
    # Since 97C every counter, `stale` and `go` included, is cleared by CMD bit 0, and the order number restarts with every restart of either
    # side, so each restart's snapshot is judged as it reads. (Bitstreams built before 97C accumulate `stale` and lack the order-content words.)
    pre_clear: list[dict | None] = []
    for i in range(n):
        b.reset(rx_dp=True)
        if not b.wait(lambda s: s["rx_done"] and s["pcs_lock"], timeout_s):
            fails += 1
            snapshots.append(None)
            continue
        pre_clear.append(dict(zip(("tx", "rx"), b.snapshot())))        # relock transient: recorded, not judged
        b.clear()
        b.configure(kind=2, count=probes_per_link, interval=3000)
        b.run(0.02)
        b.configure(arm=True, kind=1, count=probes_per_link, interval=3000)
        b.run(0.02)
        tx, rx = settled_snapshot(b, probes_per_link)
        snapshots.append({"tx": tx, "rx": rx})
        lock_clk.append(rx["lock_clk"])
        if tx["e_cnt"]:
            E.append((tx["e_min"], tx["e_max"]))
        if tx["l_cnt"]:
            L.append((tx["l_min"], tx["l_max"]))
    return {"restarts": n, "failed_to_lock": fails, "lock_clocks": summarise(lock_clk),
            "E_min_per_link": summarise([e[0] for e in E]), "E_max_per_link": summarise([e[1] for e in E]),
            "L_min_per_link": summarise([l[0] for l in L]), "L_max_per_link": summarise([l[1] for l in L]),
            "safety": safety_verdict(snapshots, probes_per_link, n), "snapshots": snapshots, "pre_clear_snapshots": pre_clear}


def decision_latency(E_clocks: float, L_clocks: float) -> float:
    """D = L - 2E, in clocks (design.md section 6: the trading loop crosses the link twice; the brief's 'minus one echo' counts one pass)."""
    return L_clocks - 2 * E_clocks


def fibre_delay_ns(length_m: float, group_index: float = 1.468) -> float:
    """One-way delay of a fibre of the measured length (group index of G.652 at 1310 nm is about 1.467 to 1.468: stated, not measured)."""
    return length_m * group_index / 0.299792458


def run_all(t: Transport, lock_text: str, out_dir: Path, *, cable_loop_m: float, n_restarts: int = 100) -> dict:
    """The stage-3 loopback sequence (board plan steps 1 to 4 and 1b). Refuses to run without the board.lock text the caller took."""
    if not lock_text.startswith(("96:", "97:", "96C:")):          # 97: brief 97 measures latency variants with the same sequence; 96C: the rate-matched builds
        raise RuntimeError("take _handoff/board.lock with a text starting '96:', '97:' or '96C:' first, and pass that text")
    b = Board(t)
    res: dict = {"lock": lock_text, "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    res["id"] = f"{b.id():08x}"
    assert b.id() == 0x96A00001, "wrong design loaded"
    b.laser(False)
    res["status_laser_off"] = b.status()
    res["module"] = b.module_info()
    # step 1: polarity. The laser goes on for seconds only.
    s0 = b.status()
    b.laser(True); time.sleep(0.1); s1 = b.status(); b.laser(False); time.sleep(0.1); s2 = b.status()
    res["polarity"] = {"off": s0, "on": s1, "off_again": s2}
    ok = s0["rx_los"] == 1 and s1["rx_los"] == 0 and s2["rx_los"] == 1 and s0["mod_abs"] == 0
    res["polarity_ok"] = ok
    if not ok:
        res["safety"] = {"ok": False, "reasons": ["not run: polarity step failed"]}
        res["stopped"] = "laser polarity or pin functions differ from the open-source example: read the schematic, do not continue"
        (out_dir / "stage3.json").write_text(json.dumps(res, indent=1)); return res
    # step 4: bring-up with the laser on, loop fitted
    b.laser(True)
    b.reset(all_=True)
    res["link_up"] = b.wait(lambda s: s["tx_done"] and s["rx_done"] and s["pcs_lock"], 5.0)
    res["status_up"] = b.status()
    res["ddm_start"] = b.ddm()
    res["safety"] = {"ok": False, "reasons": ["not run: link did not come up"]}
    if res["link_up"]:
        res["restarts"] = restart_distribution(b, n_restarts)
        res["safety"] = res["restarts"]["safety"]
        E = res["restarts"]["E_min_per_link"].get("median"); L = res["restarts"]["L_min_per_link"].get("median")
        if E is not None and L is not None:
            res["D_clocks_from_medians_of_minima"] = decision_latency(E, L)
            res["fibre_one_way_ns"] = fibre_delay_ns(cable_loop_m)
    res["ddm_end"] = b.ddm()
    b.laser(False)
    (out_dir / "stage3.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def main() -> None:
    import argparse

    from flow import version_pin
    ap = argparse.ArgumentParser(description="Stage 3 loopback bench (brief 96). Laser polarity first; the laser is left off at the end.")
    ap.add_argument("--serial", required=True, help="the cable serial of the KR260's JTAG (from ~/.config/fpga_design_agent/boards.yaml, never 'the first target')")
    ap.add_argument("--lock-text", required=True, help="the text you wrote into _handoff/board.lock (must start '96:' or '97:')")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--loop-m", type=float, required=True, help="measured length of the fibre loopback lead in metres")
    ap.add_argument("--restarts", type=int, default=100)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[3]
    t = VivadoTcl(repo, a.serial, version_pin.vivado_path())
    try:
        res = run_all(t, a.lock_text, a.out, cable_loop_m=a.loop_m, n_restarts=a.restarts)
    finally:
        t.close()
    out = {k: res[k] for k in res if k in ("id", "polarity_ok", "link_up", "stopped")}
    sf = res.get("safety", {})
    out["safety_ok"] = sf.get("ok", False)
    out["safety_failing"] = sf.get("failing_counters", []) or sf.get("reasons", [])
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
