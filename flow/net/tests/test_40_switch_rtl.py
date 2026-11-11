"""Brief 40, block 6: the learning, VLAN-aware 4-port switch (ip_lib/l2_switch), against model.L2Switch replayed in
the order the core took the frames. Hosts move between ports, VLANs overlap, unknown and group destinations flood,
the table is aged mid-run, and some frames arrive with bad FCS or as runts."""
from __future__ import annotations

import random

import pytest

from flow.net import model, pktio, sim

TB = sim.IP / "l2_switch" / "tb" / "tb_l2_switch.sv"


def srcs(rtl_dirs=None):
    rd = rtl_dirs or {}
    return (sim.rtl("match_exact", rd.get("match_exact")) + sim.rtl("pkt_queue_sched", rd.get("pkt_queue_sched")) +
            sim.rtl("l2_switch", rd.get("l2_switch")) + [TB])


PVID = [10, 10, 20, 30]
VLANS = {10: 0b0011 | 0b1000, 20: 0b0100 | 0b1000, 30: 0b1111, 40: 0b0110}


def traffic(seed, n_per_port=60):
    r = random.Random(seed)
    hosts = [(0x020000000000 | (i << 8) | r.randrange(256), r.randrange(4)) for i in range(16)]
    ports = [[] for _ in range(4)]
    for i in range(n_per_port * 4):
        h = r.randrange(len(hosts))
        mac, home = hosts[h]
        if r.random() < 0.03:                         # the host moves
            home = r.randrange(4)
            hosts[h] = (mac, home)
        u = r.random()
        if u < 0.1:
            dst = 0xFFFFFFFFFFFF
        elif u < 0.15:
            dst = 0x01005E000000 | r.randrange(1 << 16)
        elif u < 0.25:
            dst = 0x020000FF0000 | r.randrange(1 << 16)      # never a source: always unknown
        else:
            dst = r.choice(hosts)[0]
        pl = bytes(r.randrange(256) for _ in range(r.randint(46, 120)))
        tag = b""
        if r.random() < 0.3:
            tag = b"\x81\x00" + bytes([r.randrange(8) << 5, 0]) + b""
            vid = r.choice([10, 20, 30, 40, 99, 0])
            tag = b"\x81\x00" + (((r.randrange(8) << 13) | vid).to_bytes(2, "big"))
        fr = dst.to_bytes(6, "big") + mac.to_bytes(6, "big") + tag + b"\x08\x00" + pl
        user = 0
        if r.random() < 0.03:
            user = 1
        if r.random() < 0.02:
            fr = fr[:r.randint(1, 13)]
        ports[home].append((fr, user))
    return ports


def run(tmp, ports, ages=(), sched="random", seed=1, rtl_dirs=None, idx_w=9, p_valid=0.2):
    args = {"resp": tmp / "resp.txt", "pvid": "".join(f"{v:03x}" for v in reversed(PVID))}
    for p in range(4):
        pktio.write_stream(tmp / f"s{p}.txt", [f for f, _ in ports[p]], [u for _, u in ports[p]])
        args[f"stim{p}"] = tmp / f"s{p}.txt"
    lines = [f"V {v:x} {m:x}" for v, m in VLANS.items()] + [f"A {a}" for a in ages]
    (tmp / "cfg.txt").write_text("\n".join(lines) + "\n")
    args["cfg"] = tmp / "cfg.txt"
    args["nsched"] = pktio.write_sched(tmp / "sched.txt", sched, seed=seed, p_valid=p_valid, p_ready=0.9)
    args["sched"] = tmp / "sched.txt"
    sim.run(srcs(rtl_dirs), "tb_l2_switch", args, params={"IDX_W": idx_w}, tag="switch")
    return pktio.read_resp(tmp / "resp.txt")


def replay(r, ports, idx_w=9):
    events = sorted([(c, "P", w[0]) for c, w in r["words"]["P"]] + [(c, "G", 0) for c, w in r["words"]["G"]])
    sw = model.L2Switch(4, PVID, VLANS, idx_w=idx_w)
    queues = [[f for f, u in ports[p] if model.L2Switch.accepted(f, u)] for p in range(4)]
    heads = [0] * 4
    for _, kind, p in events:
        if kind == "G":
            sw.age()
        else:
            sw.frame(p, queues[p][heads[p]])
            heads[p] += 1
    assert heads == [len(q) for q in queues], "the core did not take every accepted frame exactly once"
    return sw


@pytest.mark.parametrize("seed,ages", [(1, ()), (2, (3000, 9000, 9100, 20000)), (3, (500,))])
def test_switch_bit_exact(tmp_path, seed, ages):
    ports = traffic(seed)
    r = run(tmp_path, ports, ages, seed=seed)
    sw = replay(r, ports)
    for p in range(4):
        got = [f for f, _, _ in r["pkts"][f"D{p}"]]
        assert got == sw.out[p], f"egress {p}: {len(got)} frames, model {len(sw.out[p])}"
    n_bad = sum(1 for q in ports for f, u in q if not model.L2Switch.accepted(f, u))
    assert r["meta"]["in_drops"] == n_bad
    assert r["meta"]["floods"] == sw.floods and r["meta"]["filtered"] == sw.filtered
    assert len(r["words"]["G"]) == len(ages)


def test_switch_guard():
    bad, out = sim.elaborate_fails(srcs(), "tb_l2_switch", {"IDX_W": 1})
    assert bad, out


def test_switch_oversubscribed_counts_every_loss(tmp_path):
    """Four ports offered 0.8 of a byte a clock each into a core that moves one byte a clock: the ingress buffers
    overflow; every frame is either taken by the core or counted as an ingress drop."""
    ports = traffic(5, 80)
    args_sched = "random"
    r = run(tmp_path, ports, (), sched=args_sched, seed=5, p_valid=0.8)
    assert r["meta"]["in_drops"] > 20
    offered = sum(len(q) for q in ports)
    picks = len(r["words"]["P"])
    assert picks + r["meta"]["in_drops"] == offered
