"""The pre-registered stages of the brief-127 board test (docs/board_test_plan.md), written against a `runner` so that the SAME code runs on the board (`BoardRunner`: a Transport and the plan's
`run`) and in the whole-core simulation (`SimRunner`: the plan as a script for sim/tb_itch_core.sv; the dry run of tests/test_b127_stages_sim.py). A stage builds sessions with brief 110's seeded
generator and model, plays them through the replay memory over the fibre loopback (or the simulation's loop), reads the counters and the capture ring back, and applies its PRE-REGISTERED pass
criteria; nothing is tuned after the fact. Synthetic data only.

Each stage returns {"stage": name, "pass": bool, "reasons": [...], "numbers": {...}}."""

from __future__ import annotations

import random
import statistics as st
from dataclasses import dataclass
from typing import Callable

from designs.b110_itch_ouch.model import gen, proto
from designs.b110_itch_ouch.model.ref import Cfg, Model
from designs.b96_kr260_10g.rm_gp_itch.host import itch_bench as B
from designs.b96_kr260_10g.rm_gp_itch.host import itch_host as H

#: What simulation predicts for the latency (docs/itch_integration.md section 3, results/b127/latency_sim.json): the clocks from the last payload word at the Mold receiver (s_eof) to the order's start
#: strobe in the MAC. Speculation on: 5 (6 in the clock the gearbox pause lands on the MAC); at the verdict: 10 (11). The board must land inside [min, max + 1].
PRED_T_TO_SOP = {"speculative": (5, 6), "at_verdict": (10, 11)}


def mk_frame(payload: bytes, **kw) -> bytes:
    args = dict(dst_mac=H.DEFAULTS["my_mac"], src_mac=H.DEFAULTS["venue_mac"], src_ip="192.168.58.15", dst_ip="192.168.58.10", sport=26000, dport=5810)
    args.update(kw)
    return H.eth_ip_udp(payload, **args)


def stage_cfg(**kw) -> Cfg:
    base = dict(thr=gen.MID + 3 * gen.TICK, max_pos=10**6, max_qty=1000, band=1_000_000)
    base.update(kw)
    return Cfg(**base)


@dataclass
class Runner:
    execute: Callable          # plan -> {tag: value}
    sim: bool = False          # the simulation: small sizes, fixed waits
    link_ready: bool = False

    def wait_ms(self, board_ms: int) -> int:
        return board_ms


def play(run: Runner, cfg: Cfg, frames: list[tuple], *, spec=False, strict=False, first=True, read_cap=True, prefix="", cap_slots=8) -> dict:
    """Configure (when `first`), then load and play the frames in chunks that fit the replay memory, and read the counters and the capture ring after the last chunk."""
    res = {}
    chunks = H.split_frames_for_memory(frames)
    for i, ch in enumerate(chunks):
        p = B.Plan()
        if not run.link_ready:
            p.link()
        if first and i == 0:
            B.configure(p, cfg, spec=spec, strict=strict)
        B.load_replay(p, H.replay_image(ch))
        B.start_replay(p, wait_ms=run.wait_ms(200), frames=len(ch))
        p.d(sum(g for _, g, *_ in ch) * 7 + len(ch) * 200 * 7 + 20_000)       # the replay's own time, generously (clocks of 6.2 ns -> ns, upper bound)
        if i == len(chunks) - 1:
            B.read_stats(p, prefix)
            if read_cap:
                B.read_capture(p, slots=cap_slots, prefix=prefix)
        res = run.execute(p)
        run.link_ready = True
    return res


def session_frames(cfg: Cfg, seed: int, n_msgs: int, gap: int, *, p_gap=0.0, p_dup=0.0, p_hb=0.0, bad_fcs=(), strays=True):
    """Frames, the model fed with them, and the stream's items. Frames in `bad_fcs` (item indices) are sent with a bad FCS; they must carry no candidate (docs: the model and the hardware agree only then)."""
    g = gen.Gen(seed, cfg)
    items = g.stream(n_msgs, max_per_pkt=1, p_gap=p_gap, p_dup=p_dup, p_hb=p_hb)
    m = Model(cfg)
    frames = []
    for i, it in enumerate(items):
        bad = i in bad_fcs
        m.feed(it.pkt, bad)
        frames.append((mk_frame(it.pkt, ident=i & 0xFFFF), gap, bad))
    return frames, m, items


def verdict(name: str, ok: bool, reasons: list[str], numbers: dict) -> dict:
    return {"stage": name, "pass": ok and not reasons, "reasons": reasons, "numbers": numbers}


def _safety(res: dict, reasons: list[str], *, allow_poison=False, prefix="") -> None:
    for k in ("ord.drop", "ord.fifo_ofl", "ord.pz_unres", "ord.late", "us.orphan", "us.drop_off", "us.drop_ipck", "us.drop_len", "us.drop_frag", "itch.evdrop", "itch.late_abort"):
        if res.get(prefix + k):
            reasons.append(f"{k} = {res[prefix + k]}, expected 0")
    if not allow_poison:
        for k in ("ord.pz_abort", "ord.pz_bad", "ord.pz_strict"):
            if res.get(prefix + k):
                reasons.append(f"{k} = {res[prefix + k]}, expected 0")


def stage_smoke(run: Runner, *, n_msgs=60, spec=False, seed=101) -> dict:
    """(a) A short seeded session through the whole chain: every counter of brief 110's path equals the model's, every captured order frame equals the model's frame byte for byte, the safety counters are 0."""
    cfg = stage_cfg()
    frames, m, items = session_frames(cfg, seed, n_msgs, gap=150)
    res = play(run, cfg, frames, spec=spec)
    reasons = []
    bad = B.counters_vs_model(res, m)
    if bad:
        reasons.append(f"counters differ from the model (hardware, model): {bad}")
    chk = B.order_frames_vs_model(res, m)
    reasons += chk["problems"]
    if not len(m.orders):
        reasons.append("the session produced no order: not a test")
    _safety(res, reasons, allow_poison=spec)
    if res["ord.sent"] != len(m.orders):
        reasons.append(f"orders sent {res['ord.sent']}, model {len(m.orders)}")
    if res["rp.frames"] != len(frames):
        reasons.append(f"frames played {res['rp.frames']} of {len(frames)}")
    return verdict("smoke", True, reasons, {"packets": len(items), "orders_model": len(m.orders), "orders_sent": res["ord.sent"], "aborted_speculative": res["ord.pz_abort"], "capture": chk,
                                            "lat_hist_nonzero": {k: v for k, v in res.items() if k.startswith("lat.hist") and v}})


def stray_frame(kind: str, payload: bytes, ident: int) -> bytes:
    """A frame the adapter must drop for exactly one reason: another destination MAC, UDP port, destination address, or IP protocol (6, with a valid header checksum)."""
    if kind == "mac":
        return mk_frame(payload, dst_mac=bytes.fromhex("02aabbccddee"), ident=ident)
    if kind == "port":
        return mk_frame(payload, dport=9, ident=ident)
    if kind == "dip":
        return mk_frame(payload, dst_ip="192.168.58.99", ident=ident)
    f = bytearray(mk_frame(payload, ident=ident))
    f[23] = 6                                                        # protocol TCP
    f[24:26] = b"\0\0"
    f[24:26] = H.csum16(bytes(f[14:34])).to_bytes(2, "big")           # a valid IPv4 header, so only the protocol is wrong
    return bytes(f)


def stage_counters(run: Runner, *, n_msgs=120, seed=202) -> dict:
    """(b) The same with impairments: sequence gaps, duplicates, heartbeats, frames with a bad FCS (the replay's poison bit; heartbeats only, so no candidate is inside), and stray frames for another MAC,
    port, address and protocol. Every counter of brief 110's path equals the model's; the adapter's drop counters equal what was sent; the bad frames are all counted."""
    cfg = stage_cfg(halt_on_gap=False)
    g = gen.Gen(seed, cfg)
    items = g.stream(n_msgs, max_per_pkt=1, p_gap=0.06, p_dup=0.06, p_hb=0.08)
    m = Model(cfg)
    frames = []
    expect_us = {"bad_fcs": 0, "drop_mac": 0, "drop_port": 0, "drop_dip": 0, "drop_proto": 0}
    rng = random.Random(seed)
    for i, it in enumerate(items):
        bad = (i % 17 == 9) and len(it.pkt) <= 20             # a bad FCS only on heartbeats (20 bytes: no message inside)
        m.feed(it.pkt, bad)
        frames.append((mk_frame(it.pkt, ident=i & 0xFFFF), 150, bad))
        expect_us["bad_fcs"] += int(bad)
        if i % 13 == 5:
            kind = rng.choice(("mac", "port", "dip", "proto"))
            frames.append((stray_frame(kind, it.pkt, (i + 1) & 0xFFFF), 150, False))
            expect_us["drop_" + kind] += 1
    res = play(run, cfg, frames, spec=False, read_cap=False)
    reasons = []
    bad = B.counters_vs_model(res, m)
    if bad:
        reasons.append(f"counters differ from the model (hardware, model): {bad}")
    for k, v in expect_us.items():
        got = res["us." + k]
        if got != v:
            reasons.append(f"us.{k} = {got}, sent {v}")
    if res["us.fwd"] != len(items):
        reasons.append(f"forwarded {res['us.fwd']}, expected {len(items)}")
    _safety(res, reasons)
    return verdict("counters", True, reasons, {"packets": len(items), "frames_played": len(frames), "orders_model": len(m.orders), "us": {k: v for k, v in res.items() if k.startswith("us.")}})


def latency_frames(cfg: Cfg, gap: int = 150, reps: int = 1):
    from designs.b96_kr260_10g.rm_gp_itch.tests import measure_xsim as M      # the same session as the simulation's records
    pkts, frames, meta = M.latency_session(cfg, gap=gap, reps=reps)
    return pkts, [(f, g, False) for f, g in frames], meta


def stage_latency(run: Runner, *, passes=125, spec=False) -> dict:
    """(c) The order latency distribution from the hardware's own statistics: `passes` passes of the replay (each: clears, the replayed session of 8 single-candidate packets, one for each alignment of the
    message end), so 8 x passes orders. The hardware histogram (clocks from the last payload word at the Mold receiver to the order's start strobe) must lie in the simulation's prediction + 1 clock."""
    cfg = stage_cfg()
    pkts, frames, meta = latency_frames(cfg)
    m = Model(cfg)
    first = True
    res = {}
    img = H.replay_image(frames)
    for i in range(passes):
        p = B.Plan()
        if not run.link_ready:
            p.link()
        if first:
            B.configure(p, cfg, spec=spec)
            B.load_replay(p, img)
            p.w(B.ADDR["IT_CMD"], B.CMD["lat_clr"]).d(B.HS_NS)
            first = False
        else:
            p.w(B.ADDR["IT_CMD"], B.CMD["clr_flags"] | B.CMD["clr_book"] | B.CMD["clr_pos"] | B.CMD["clr_ref"]).d(B.HS_NS * 4)
        B.start_replay(p, wait_ms=run.wait_ms(100), frames=len(frames))
        p.d(len(frames) * 150 * 7 + 15_000)
        if i == passes - 1:
            B.read_stats(p)
        res = run.execute(p)
        run.link_ready = True
    n_expected = 8 * passes
    hist = {}
    for i in range(8):
        w = res[f"lat.hist{2 * i}_{2 * i + 1}"]
        hist[2 * i], hist[2 * i + 1] = w & 0xFFFF, w >> 16
    lo, hi = PRED_T_TO_SOP["speculative" if spec else "at_verdict"]
    reasons = []
    outside = {k: v for k, v in hist.items() if v and not (lo <= k <= hi + 1)}
    if outside:
        reasons.append(f"latency bins outside the prediction [{lo}, {hi + 1}]: {outside}")
    if res["lat.count"] != n_expected - (res["lat.neg"] if spec else 0) and res["lat.count"] != n_expected:
        reasons.append(f"orders measured {res['lat.count']}, expected {n_expected}")
    if res["lat.neg"]:
        reasons.append(f"{res['lat.neg']} orders started before their packet ended")
    _safety(res, reasons, allow_poison=spec)
    return verdict("latency", True, reasons, {"mode": "speculative" if spec else "at_verdict", "orders": res["lat.count"], "min": res["lat.min"], "max": res["lat.max"], "hist": {k: v for k, v in hist.items() if v},
                                              "predicted_clocks": [lo, hi], "clock_ns": 6.2058})


def stage_rate(run: Runner, *, passes=100) -> dict:
    """(d) Line rate: frames of non-candidate messages (Delete, Cancel, Execute and other types: bytes, not orders) played back to back (gap 0), `passes` times; no event dropped, no bad frame, every frame forwarded."""
    cfg = stage_cfg()
    g = gen.Gen(303, cfg)
    pre = proto.mold_packet(b"SESSION001", 1, g.preamble()[:3])
    seq, pkts = 4, [pre]
    for k in range(18):
        m_ = proto.itch_other("P", 30 + (k % 5), g.loc0, 5) if k % 2 else proto.itch_D(g.loc0, g._t(), 5_000_000 + k)
        pkts.append(proto.mold_packet(b"SESSION001", seq, [m_])); seq += 1
    frames = [(mk_frame(p, ident=i), 0, False) for i, p in enumerate(pkts)]
    img = H.replay_image(frames)
    p = B.Plan()
    if not run.link_ready:
        p.link()
    B.configure(p, cfg, rp_loops=passes)
    B.load_replay(p, img)
    B.start_replay(p, wait_ms=run.wait_ms(2000), frames=len(frames))
    p.d(passes * len(frames) * 20 * 7 + 30_000)
    B.read_stats(p)
    res = run.execute(p)
    run.link_ready = True
    reasons = []
    want = passes * len(frames)
    # each pass repeats the same packets: after the first pass they are duplicates (dropped by the Mold layer, counted): the point is the receive and adapter path at line rate
    if res["rp.frames"] != want:
        reasons.append(f"frames played {res['rp.frames']} of {want}")
    if res["us.fwd"] != want:
        reasons.append(f"frames forwarded {res['us.fwd']} of {want}")
    for k in ("us.bad_fcs", "us.cut", "us.orphan", "itch.evdrop", "itch.pkt_err"):
        if res[k]:
            reasons.append(f"{k} = {res[k]}, expected 0")
    return verdict("rate", True, reasons, {"frames": want, "frame_bytes": [len(f) + 4 for f, *_ in frames][:3], "evdrop": res["itch.evdrop"], "dup": res["itch.dup"]})


def stage_risk(run: Runner, *, passes=60) -> dict:
    """(e) The kill switch and the limits changed from the host while traffic runs: candidate frames play in a loop; the host sets KILL, then clears it, then lowers IT_MAXPOS; each change must show in the
    counters (rej_kill, rej_pos) and no order is sent while KILL is set, beyond the frames already in flight (at most 2)."""
    cfg = stage_cfg(max_pos=10**6)
    g = gen.Gen(404, cfg)
    pkts = [proto.mold_packet(b"SESSION001", 1, g.preamble()[:3]),
            proto.mold_packet(b"SESSION001", 4, [proto.itch_A(g.loc0, g._t(), g._newref(), "B", 100, cfg.watch[0], gen.MID - 100)])]
    seq = 5
    for k in range(4):
        pkts.append(proto.mold_packet(b"SESSION001", seq, [proto.itch_A(g.loc0, g._t(), g._newref(), "S", 100, cfg.watch[0], gen.MID + 100 + 10 * k)])); seq += 1
    frames = [(mk_frame(p, ident=i), 400, False) for i, p in enumerate(pkts)]
    p = B.Plan()
    if not run.link_ready:
        p.link()
    B.configure(p, cfg, rp_loops=1)
    B.load_replay(p, H.replay_image(frames))
    B.start_replay(p, wait_ms=run.wait_ms(300), frames=len(frames))
    p.d(len(frames) * 400 * 7 + 20_000)
    B.read_stats(p, "a.")
    p.w(B.ADDR["IT_CTRL"], 1 | 2 | 4 | 16).d(B.HS_NS)          # KILL
    p.w(B.ADDR["IT_CMD"], B.CMD["clr_flags"] | B.CMD["clr_book"] | B.CMD["clr_ref"]).d(B.HS_NS * 4)
    B.start_replay(p, wait_ms=run.wait_ms(300), frames=len(frames))
    p.d(len(frames) * 400 * 7 + 20_000)
    B.read_stats(p, "b.")
    p.w(B.ADDR["IT_CTRL"], 1 | 2 | 16).d(B.HS_NS)               # KILL off
    p.w(B.ADDR["IT_MAXPOS"], 150).d(B.HS_NS)                    # room for one order of 100 only
    p.w(B.ADDR["IT_CMD"], B.CMD["clr_flags"] | B.CMD["clr_book"] | B.CMD["clr_ref"] | B.CMD["clr_pos"]).d(B.HS_NS * 4)
    B.start_replay(p, wait_ms=run.wait_ms(300), frames=len(frames))
    p.d(len(frames) * 400 * 7 + 20_000)
    B.read_stats(p, "c.")
    res = run.execute(p)
    run.link_ready = True
    reasons = []
    a_sent, b_sent, c_sent = res["a.ord.sent"], res["b.ord.sent"] - res["a.ord.sent"], res["c.ord.sent"] - res["b.ord.sent"]
    if a_sent != 4:
        reasons.append(f"before the kill: {a_sent} orders, expected 4")
    if b_sent != 0 or res["b.itch.rej_kill"] - res["a.itch.rej_kill"] != 4:
        reasons.append(f"with KILL: {b_sent} orders sent (expected 0), rej_kill rose by {res['b.itch.rej_kill'] - res['a.itch.rej_kill']} (expected 4)")
    if c_sent != 1 or res["c.itch.rej_pos"] - res["b.itch.rej_pos"] != 3:
        reasons.append(f"with the position limit: {c_sent} orders (expected 1), rej_pos rose by {res['c.itch.rej_pos'] - res['b.itch.rej_pos']} (expected 3)")
    return verdict("risk", True, reasons, {"orders_before_kill": a_sent, "orders_with_kill": b_sent, "orders_with_limit": c_sent})


STAGES = {"smoke": stage_smoke, "counters": stage_counters, "latency": stage_latency, "rate": stage_rate, "risk": stage_risk}


def run_all(run: Runner, which=("smoke", "counters", "latency", "rate", "risk"), sizes: dict | None = None) -> dict:
    out = {}
    for name in which:
        kw = (sizes or {}).get(name, {})
        out[name] = STAGES[name](run, **kw)
    out["all_pass"] = all(v["pass"] for v in out.values())
    return out
