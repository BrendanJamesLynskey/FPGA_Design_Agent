"""Brief 40, block 1: the RMII MAC (ip_lib/eth_mac_rmii) against the golden model, bit-exact.

Receive: scapy-built frames as RMII pins (preamble variants, CRS_DV toggling at the end of the frame, bad FCS,
alignment errors, rx_er, runts), at 100 and 10 Mb/s. Transmit: the wire dibits for each packet, and the inter-frame
gap at back-to-back load. Loopback: transmit into receive.
"""
from __future__ import annotations

import os
import random
from pathlib import Path

import pytest

from flow.net import model, sim, traffic

pytestmark = pytest.mark.skipif(not traffic.HAVE_SCAPY, reason="scapy not installed")

BLOCK = "eth_mac_rmii"
TB = sim.IP / BLOCK / "tb" / "tb_eth_mac_rmii.sv"


def srcs(rtl_dir=None):
    return sim.rtl(BLOCK, rtl_dir) + [TB]


def read_rx(path: Path):
    frames, cur, meta, cycles = [], [], {}, []
    for ln in path.read_text().splitlines():
        if ln.startswith("#"):
            _, k, v = ln.split()
            meta[k] = int(v)
            continue
        c, d, last, user = ln.split()
        if not cur:
            cycles.append(int(c))
        cur.append(int(d, 16))
        if last == "1":
            frames.append((bytes(cur), int(user)))
            cur = []
    return frames, meta, cycles


def read_wire(path: Path, rep: int = 1):
    """Split the recorded transmit pins into frames of dibits; also the idle clocks between frames."""
    frames, gaps, cur, last_c, start_c = [], [], [], None, []
    prev_end = None
    for ln in path.read_text().splitlines():
        c, en, d = map(int, ln.split())
        if en:
            if not cur:
                start_c.append(c)
                if prev_end is not None:
                    gaps.append(c - prev_end)
            cur.append(d)
        elif cur:
            frames.append(cur[::rep])
            prev_end = c
            cur = []
    if cur:
        frames.append(cur[::rep])
    return frames, gaps, start_c


def rx_items(seed: int, n: int):
    r = random.Random(seed)
    items = []
    for k, fr in traffic.mix(seed, n, max_payload=120):
        it = {"frame": fr, "lead00": r.choice([0, 0, 1, 3]), "pre_bytes": r.choice([7, 7, 6, 5]),
              "toggle": r.choice([0, 0, 1, 3, 6]), "ifg": r.choice([48, 48, 60, 100])}
        u = r.random()
        if u < 0.12:
            it["bad_fcs"] = True
        elif u < 0.18:
            it["extra_dibits"] = r.choice([1, 2, 3])
        elif u < 0.22:
            it["rx_er"] = True
        items.append(it)
    return items


def run_rx(tmp: Path, items, speed10=False, rtl_dir=None, seed=0):
    lines, expect, cnt = model.rx_line(items, speed10=speed10, rng=random.Random(seed))
    lf = tmp / "rx_line.txt"
    lf.write_text("".join(f"{v} {d} {e}\n" for v, d, e in lines))
    out = tmp / "rx_resp.txt"
    sim.run(srcs(rtl_dir), "tb_eth_mac_rmii", {"rx_line": lf, "rx_resp": out, "tx_wire": tmp / "w.txt",
                                               "speed10": int(speed10), "cycles": len(lines) + 200}, tag="mac")
    got, meta, _ = read_rx(out)
    return got, expect, meta, cnt


@pytest.mark.parametrize("seed,speed10,n", [(1, False, 120), (2, False, 120), (3, True, 25)])
def test_rx_bit_exact(tmp_path, seed, speed10, n):
    got, expect, meta, cnt = run_rx(tmp_path, rx_items(seed, n), speed10, seed=seed)
    assert len(got) == len(expect)
    bad = [i for i, (g, e) in enumerate(zip(got, expect)) if g != e]
    assert not bad, f"first mismatch frame {bad[0]}: got {got[bad[0]]} expect {expect[bad[0]]}"
    assert meta["ev_ok"] == cnt["ok"] and meta["ev_bad"] == cnt["bad"] and meta["ev_fcs"] == cnt["fcs"]
    assert meta["ev_runt"] == cnt["runt"]


def tx_stim(path: Path, packets, gaps):
    with open(path, "w") as f:
        for p, g in zip(packets, gaps):
            for i, b in enumerate(p):
                f.write(f"{g if i == 0 else 0} {b:02x} {int(i == len(p) - 1)} 0\n")


@pytest.mark.parametrize("speed10,ifg,min_data", [(False, 12, 60), (True, 12, 60), (False, 16, 46), (False, 1, 1)])
def test_tx_bit_exact_and_ifg(tmp_path, speed10, ifg, min_data):
    pk = [fr for _, fr in traffic.mix(7, 12 if speed10 else 60, max_payload=150)]
    pk[0] = pk[0][:20]                                    # short: padded by the MAC
    tx_stim(tmp_path / "tx.txt", pk, [0] * len(pk))
    rep = 10 if speed10 else 1
    ncyc = rep * sum(4 * (8 + max(60, len(p)) + 4 + ifg) for p in pk) + 400
    sim.run(srcs(), "tb_eth_mac_rmii", {"tx_stim": tmp_path / "tx.txt", "rx_resp": tmp_path / "r.txt",
                                        "tx_wire": tmp_path / "w.txt", "speed10": int(speed10), "cycles": ncyc},
            params={"MIN_DATA": min_data, "IFG": ifg}, tag="mac")
    frames, gaps, _ = read_wire(tmp_path / "w.txt", rep)
    want = model.tx_wire_frames(pk, min_data)
    assert len(frames) == len(want)
    for i, (g, w) in enumerate(zip(frames, want)):
        assert g == w, f"frame {i} differs"
    # back to back: exactly the inter-frame gap (802.3: 96 bit times = 48 dibits) between frames
    assert gaps and all(g == 4 * ifg * rep for g in gaps), sorted(set(gaps))


def test_loopback_and_underrun(tmp_path):
    pk = [fr for _, fr in traffic.mix(11, 40, max_payload=200)]
    lines = []
    with open(tmp_path / "tx.txt", "w") as f:
        for j, p in enumerate(pk):
            for i, b in enumerate(p):
                g = 0
                if j == 5 and i == 30:
                    g = 40                                # an underrun inside frame 5
                f.write(f"{g if i else 3} {b:02x} {int(i == len(p) - 1)} {int(j == 9 and i == 20)}\n")
    ncyc = sum(4 * (8 + max(60, len(p)) + 4 + 12) + 60 for p in pk) + 2000
    sim.run(srcs(), "tb_eth_mac_rmii", {"tx_stim": tmp_path / "tx.txt", "rx_resp": tmp_path / "r.txt",
                                        "tx_wire": tmp_path / "w.txt", "loop": 1, "cycles": ncyc}, tag="mac")
    got, meta, _ = read_rx(tmp_path / "r.txt")
    assert meta["ev_under"] == 1
    assert meta["ev_sent"] == len(pk) - 2                # frame 5 (underrun) and 9 (tuser abort) are bad
    good = [g for g in got if g[1] == 0]
    want = [p for j, p in enumerate(pk) if j not in (5, 9)]
    assert [g[0][:len(w)] for g, w in zip(good, want)] == want   # padded frames come back with their pad
    assert all(len(g[0]) == max(60, len(w)) for g, w in zip(good, want))
    assert len([g for g in got if g[1] == 1]) == 2


def line_rate_rx(tmp: Path) -> dict:
    """Minimum frames back to back with the minimum gap: every frame must come out (148,809 frames/s at 100 Mb/s)."""
    r = random.Random(5)
    fr = [traffic.frame("min", r) for _ in range(200)]
    items = [{"frame": f, "ifg": 48} for f in fr]
    got, expect, meta, cnt = run_rx(tmp, items)
    _, _, cycles = read_rx(tmp / "rx_resp.txt")
    per = (cycles[-1] - cycles[0]) / (len(cycles) - 1)
    return {"frames_in": len(fr), "frames_out_ok": sum(1 for g in got if g[1] == 0), "clocks_per_frame": per,
            "frames_per_s_at_50MHz": 50e6 / per, "theory_100M": 100e6 / (84 * 8), "latency_note":
            "receive output lags the wire by 5 bytes (FCS strip) plus 2 register stages"}


@pytest.mark.parametrize("params", [{"MIN_FRAME": 4}, {"MIN_DATA": 0}, {"IFG": 0}, {"MIN_FRAME": 2000}])
def test_mac_guards(params):
    bad, out = sim.elaborate_fails(srcs(), "tb_eth_mac_rmii", params)
    assert bad, out


def test_rx_line_rate_min_frames(tmp_path):
    m = line_rate_rx(tmp_path)
    assert m["frames_out_ok"] == m["frames_in"]
    assert abs(m["frames_per_s_at_50MHz"] - m["theory_100M"]) < 1.0
