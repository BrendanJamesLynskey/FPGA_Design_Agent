"""Brief 40, block 5: packet buffer, per-queue descriptors and the three schedulers (ip_lib/pkt_queue_sched).

Fill-then-drain runs (deq_en held low until every packet is in) make the departure order a function of the queue
contents only, so it is compared bit-exact with model.schedule_order. Concurrent runs (random valid/ready) check that
each queue's packets leave intact and in order, and that every packet lost to a full region is counted."""
from __future__ import annotations

import random

import pytest

from flow.net import model, pktio, sim

BLOCK = "pkt_queue_sched"
TB = sim.IP / BLOCK / "tb" / "tb_pkt_queue_sched.sv"


def srcs(rtl_dir=None):
    return sim.rtl(BLOCK, rtl_dir) + [TB]


def pkts(seed, n, nq, lo=1, hi=300):
    r = random.Random(seed)
    out = []
    for _ in range(n):
        ln = r.choice([lo, 60, 64, r.randint(lo, hi), r.randint(lo, hi)])
        out.append((bytes(r.randrange(256) for _ in range(ln)), r.randrange(nq), int(r.random() < 0.1)))
    return out


def run(tmp, packets, params, mode=0, quantum=None, hold=1, sched="continuous", seed=1, rtl_dir=None):
    nq = params.get("NQ", 4)
    pktio.write_stream(tmp / "stim.txt", [p for p, _, _ in packets], [u for _, _, u in packets],
                       extra=[q for _, q, _ in packets])
    ns = pktio.write_sched(tmp / "sched.txt", sched, seed=seed)
    qv = sum((quantum or [0] * nq)[i] << (16 * i) for i in range(nq))
    sim.run(srcs(rtl_dir), "tb_pkt_queue_sched", {"stim": tmp / "stim.txt", "sched": tmp / "sched.txt",
                                                  "nsched": ns, "resp": tmp / "resp.txt", "mode": mode,
                                                  "quantum": f"{qv:x}", "hold": hold}, params=params, tag="queues")
    return pktio.read_resp(tmp / "resp.txt")


@pytest.mark.parametrize("mode,quantum", [(0, None), (1, None), (2, [100, 300, 64, 1500]), (2, [500, 500, 500, 500])])
def test_departure_order_bit_exact(tmp_path, mode, quantum):
    packets = pkts(10 + mode, 40, 4)
    r = run(tmp_path, packets, {"NQ": 4, "QBYTES": 8192, "DESC": 32}, mode, quantum, hold=1, sched="random")
    per_q = [[p for p in packets if p[1] == q] for q in range(4)]
    order = model.schedule_order([[len(p[0]) for p in per_q[q]] for q in range(4)], mode, quantum)
    want = [(per_q[q][i][0], per_q[q][i][2], q) for q, i in order]
    got = r["pkts"]["D"]
    assert got == want
    assert all(r["meta"][f"drop{q}"] == 0 for q in range(4))


@pytest.mark.parametrize("params,seed", [({"NQ": 2, "QBYTES": 256, "DESC": 4, "MAX_LEN": 200}, 1),
                                         ({"NQ": 4, "QBYTES": 512, "DESC": 2, "MAX_LEN": 512}, 2),
                                         ({"NQ": 8, "QBYTES": 1024, "DESC": 8, "MAX_LEN": 1000}, 3)])
def test_concurrent_order_and_drop_count(tmp_path, params, seed):
    nq = params["NQ"]
    packets = pkts(seed, 300, nq, hi=params["MAX_LEN"] + 40)
    r = run(tmp_path, packets, params, mode=seed % 3, quantum=[200] * nq, hold=0, sched="random", seed=seed)
    got = r["pkts"]["D"]
    total_drop = 0
    for q in range(nq):
        offered = [(p, u) for p, qq, u in packets if qq == q]
        out = [(p, u) for p, u, d in got if d == q]
        # out must be an in-order subsequence of offered
        it = iter(offered)
        assert all(any(o == x for x in it) for o in out), f"queue {q}: reordered or corrupted"
        assert len(offered) - len(out) == r["meta"][f"drop{q}"], f"queue {q}: drops not counted"
        assert not any(len(p) > params["MAX_LEN"] for p, _ in out)
        total_drop += r["meta"][f"drop{q}"]
    assert total_drop > 0                         # overflow paths were exercised


def test_queue_guards():
    for p in ({"NQ": 3}, {"QBYTES": 1000}, {"DESC": 1}, {"MAX_LEN": 5000, "QBYTES": 2048}):
        bad, out = sim.elaborate_fails(srcs(), "tb_pkt_queue_sched", p)
        assert bad, (p, out)


def line_rate(tmp) -> dict:
    """Minimum frames into one queue and out again, continuous: input and output bytes a clock."""
    r = random.Random(1)
    packets = [(bytes(r.randrange(256) for _ in range(60)), r.randrange(4), 0) for _ in range(300)]
    res = run(tmp, packets, {"NQ": 4, "QBYTES": 8192, "DESC": 64}, mode=0, hold=0)
    first = res["first"]["D"]
    got = res["pkts"]["D"]
    assert len(got) == 300
    return {"out_clocks_per_60B_frame": (first[-1] - first[0]) / (len(first) - 1),
            "latency_first_byte_clocks": first[0] - res["meta"]["first_in"]}


def test_queue_line_rate(tmp_path):
    m = line_rate(tmp_path)
    assert m["out_clocks_per_60B_frame"] <= 63.0
