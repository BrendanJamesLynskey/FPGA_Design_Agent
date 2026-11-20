"""The Python side of brief 110 without a simulator: the packers against the field tables of the specifications (transcribed below), the reference
model against hand-computed expectations (the RTL is compared with the model, so the model must be right on its own), the generator's determinism,
and the consistency of the counter list, the generated package, the mutation set and the datasheet."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

from designs.b110_itch_ouch.model import gen, proto
from designs.b110_itch_ouch.model.ref import BID, ASK, COUNTERS, Cfg, Model

D = Path(__file__).parent.parent
ROOT = D.parents[1]
MID, TK = gen.MID, gen.TICK

# (name, offset, length) from the tables of TotalView-ITCH 5.0 (sections 1.1 to 1.4.5), MoldUDP64 1.00 and OUCH 5.0 section 2.1
ITCH_TABLES = {
    "S": [("type", 0, 1), ("locate", 1, 2), ("tracking", 3, 2), ("timestamp", 5, 6), ("event", 11, 1)],
    "A": [("type", 0, 1), ("locate", 1, 2), ("tracking", 3, 2), ("timestamp", 5, 6), ("ref", 11, 8), ("side", 19, 1), ("shares", 20, 4), ("stock", 24, 8), ("price", 32, 4)],
    "F": [("ref", 11, 8), ("side", 19, 1), ("shares", 20, 4), ("stock", 24, 8), ("price", 32, 4), ("mpid", 36, 4)],
    "E": [("ref", 11, 8), ("shares", 19, 4), ("match", 23, 8)],
    "C": [("ref", 11, 8), ("shares", 19, 4), ("match", 23, 8), ("printable", 31, 1), ("price", 32, 4)],
    "X": [("ref", 11, 8), ("shares", 19, 4)],
    "D": [("ref", 11, 8)],
    "U": [("oref", 11, 8), ("nref", 19, 8), ("shares", 27, 4), ("price", 31, 4)],
    "R": [("stock", 11, 8)],
}
OUCH_ENTER = [("type", 0, 1), ("userref", 1, 4), ("side", 5, 1), ("qty", 6, 4), ("symbol", 10, 8), ("price", 18, 8), ("tif", 26, 1), ("display", 27, 1),
              ("capacity", 28, 1), ("ise", 29, 1), ("cross", 30, 1), ("clordid", 31, 14), ("applen", 45, 2)]


def field(m: bytes, off: int, n: int) -> int:
    return int.from_bytes(m[off:off + n], "big")


def test_itch_lengths_and_offsets() -> None:
    msgs = {"S": proto.itch_S(7, 5, "Q"), "A": proto.itch_A(7, 5, 0x1122334455667788, "S", 321, "ABC", 99_0000), "F": proto.itch_F(7, 5, 0x1122334455667788, "B", 321, "ABC", 99_0000),
            "E": proto.itch_E(7, 5, 0x1122334455667788, 33, 0x0102030405060708), "C": proto.itch_C(7, 5, 0x1122334455667788, 33, 98_0000, 9, "N"),
            "X": proto.itch_X(7, 5, 0x1122334455667788, 33), "D": proto.itch_D(7, 5, 0x1122334455667788),
            "U": proto.itch_U(7, 5, 0x1122334455667788, 0x99, 44, 97_0000), "R": proto.itch_R(7, 5, "ABC")}
    for t, m in msgs.items():
        assert len(m) == proto.ITCH_LEN[t] and chr(m[0]) == t and field(m, 1, 2) == 7 and field(m, 5, 6) == 5, t
    a = msgs["A"]
    assert (field(a, 11, 8), chr(a[19]), field(a, 20, 4), a[24:32], field(a, 32, 4)) == (0x1122334455667788, "S", 321, b"ABC     ", 990000)
    assert field(msgs["E"], 19, 4) == 33 and field(msgs["E"], 23, 8) == 0x0102030405060708
    assert field(msgs["C"], 32, 4) == 980000 and msgs["C"][31:32] == b"N"
    u = msgs["U"]
    assert (field(u, 11, 8), field(u, 19, 8), field(u, 27, 4), field(u, 31, 4)) == (0x1122334455667788, 0x99, 44, 970000)
    assert msgs["F"][36:40] == b"NSDQ" and msgs["R"][11:19] == b"ABC     "
    # the last field of each table ends at the message length (the spec's lengths follow from its offsets)
    for t, tab in ITCH_TABLES.items():
        last = max(o + n for _, o, n in tab)
        assert last <= proto.ITCH_LEN[t], t
        if t not in ("R",):
            assert last == proto.ITCH_LEN[t], t


def test_mold_packet_layout() -> None:
    p = proto.mold_packet(b"ABCDEFGHIJ", 0x0102030405060708, [b"x" * 12, b"y" * 13])
    assert p[:10] == b"ABCDEFGHIJ" and field(p, 10, 8) == 0x0102030405060708 and field(p, 18, 2) == 2
    assert field(p, 20, 2) == 12 and p[22:34] == b"x" * 12 and field(p, 34, 2) == 13 and len(p) == 20 + 14 + 15
    assert field(proto.heartbeat(b"ABCDEFGHIJ", 5), 18, 2) == 0 and field(proto.end_of_session(b"ABCDEFGHIJ", 5), 18, 2) == 0xFFFF
    w = proto.words(p)
    assert len(w) == (len(p) + 7) // 8 and w[-1][1] == (1 << (len(p) % 8 or 8)) - 1 and w[0][0] & 0xFF == ord("A")


def test_ouch_enter_and_soup_layout() -> None:
    m = proto.ouch_enter(0x01020304, "B", 100, b"AAA     ", 123456, "3", "Y", "P", "N", "N", proto.clordid(0x1A2B), 0, "N")
    assert len(m) == 56
    for name, off, n in OUCH_ENTER:
        assert off + n <= len(m), name
    assert (m[0:1], field(m, 1, 4), m[5:6], field(m, 6, 4), m[10:18], field(m, 18, 8)) == (b"O", 0x01020304, b"B", 100, b"AAA     ", 123456)
    assert m[26:31] == b"3YPNN" and m[31:45] == b"FDA11000001A2B" and field(m, 45, 2) == 9 and len(m) - 47 == 9
    # TagValue: length (tag byte plus value), tag, value; MinQty tag 3 (4 bytes), CustomerType tag 4 (1 byte) (Appendix A)
    assert m[47:53] == bytes([5, 3, 0, 0, 0, 0]) and m[53:56] == bytes([2, 4]) + b"N"
    f = proto.soup_unsequenced(m)
    assert len(f) == 59 and field(f, 0, 2) == 57 and f[2:3] == b"U" and f[3:] == m


def test_counter_list_package_and_docs() -> None:
    assert len(COUNTERS) == len(set(COUNTERS)) == 45
    pkg = (D / "rtl" / "itch_pkg.sv").read_text()
    for i, n in enumerate(COUNTERS):
        assert f"localparam int C_{n.upper()} = {i};" in pkg, n
    assert subprocess.run([sys.executable, str(D / "scripts" / "gen_pkg.py"), "--check"]).returncode == 0
    doc = (D / "docs" / "itch_ouch.md").read_text()
    for n in COUNTERS:
        assert re.search(rf"`{n}`|`{n} |\b{n}\b", doc), f"counter {n} is not defined in the datasheet"


def test_mutation_set_applies_once() -> None:
    ms = yaml.safe_load((D / "verif" / "mutants.yaml").read_text())["mutants"]
    assert len({m["name"] for m in ms}) == len(ms) >= 50
    for m in ms:
        assert (D / "rtl" / m["file"]).read_text().count(m["old"]) == 1, m["name"]
        assert m["old"] != m["new"]


# ---------------------------------------------------------------- the model against hand-computed behaviour
def mk(cfg: Cfg | None = None) -> Model:
    return Model(cfg or Cfg(thr=MID + 300, max_pos=2000, max_qty=500, band=20_000))


def open_day(m: Model, seq: int = 1) -> int:
    msgs = [proto.itch_S(0, 1, "O")] + [proto.itch_R(10 + i, 2, m.cfg.watch[i]) for i in range(m.cfg.n_inst)]
    m.feed(proto.mold_packet(b"SESSION001", seq, msgs))
    return seq + len(msgs)


def A(m, i, ref_, side, sh, px):
    return proto.itch_A(10 + i, 3, ref_, side, sh, m.cfg.watch[i], px)


def test_model_mold_gaps_duplicates_overlaps() -> None:
    m = mk()
    s = b"SESSION001"
    d = lambda n: [proto.itch_D(10, 0, 1000 + k) for k in range(n)]      # noqa: E731
    m.feed(proto.mold_packet(s, 100, d(3)))                              # first packet defines the expected number: 103
    assert m.cnt["pkt"] == 1 and m.cnt["gap"] == 0 and m.exp == 103
    m.feed(proto.mold_packet(s, 105, d(2)))                              # gap of 2
    assert (m.cnt["gap"], m.cnt["missing"], m.exp, m.gap) == (1, 2, 107, True)
    m.feed(proto.mold_packet(s, 105, d(2)))                              # exact duplicate
    assert m.cnt["dup"] == 1 and m.exp == 107
    n0 = len(m.msgs)
    m.feed(proto.mold_packet(s, 105, d(4)))                              # overlap: 105, 106 known, 107 and 108 new
    assert m.cnt["ovlp"] == 2 and len(m.msgs) - n0 == 2 and m.exp == 109 and m.msgs[-1][0] == 108
    m.feed(proto.heartbeat(s, 109))
    m.feed(proto.heartbeat(s, 112))                                      # a heartbeat that shows a gap
    assert (m.cnt["hb"], m.cnt["gap"], m.cnt["missing"], m.exp) == (2, 2, 5, 112)
    m.feed(proto.heartbeat(s, 50))                                       # an old heartbeat
    assert m.cnt["dup"] == 2
    m.feed(proto.mold_packet(b"OTHERSESS1", 112, d(1)))
    assert m.cnt["sess"] == 1 and m.exp == 112
    m.feed(proto.end_of_session(s, 112))
    assert m.cnt["eos"] == 1 and m.eos_seen
    m.feed(proto.mold_packet(s, 112, d(2))[:30])                         # cut in the second block's data
    assert m.cnt["trunc"] == 1
    m.feed(b"\0" * 19)
    assert m.cnt["short"] == 1
    m.feed(proto.mold_packet(s, 114, [proto.itch_D(10, 0, 1), b"\1" * 11, proto.itch_D(10, 0, 2)]))
    assert m.cnt["badlen"] == 1


def test_model_book_best_prices_and_replace() -> None:
    m = mk()
    s = open_day(m)
    px = MID
    m.feed(proto.mold_packet(b"SESSION001", s, [A(m, 0, 1, "B", 100, px - 100), A(m, 0, 2, "B", 50, px - 100), A(m, 0, 3, "B", 70, px - 200),
                                               A(m, 0, 4, "S", 10, px + 500), A(m, 0, 5, "S", 20, px + 600)]))
    assert m.tob[0][BID] == (px - 100, 150, True) and m.tob[0][ASK] == (px + 500, 10, True)
    m.feed(proto.mold_packet(b"SESSION001", s + 5, [proto.itch_X(10, 0, 1, 30), proto.itch_E(10, 0, 2, 50)]))      # 30 cancelled, 50 executed
    assert m.tob[0][BID] == (px - 100, 70, True)
    m.feed(proto.mold_packet(b"SESSION001", s + 7, [proto.itch_D(10, 0, 1)]))
    assert m.tob[0][BID] == (px - 200, 70, True)                         # the best level moved down: first level emptied
    m.feed(proto.mold_packet(b"SESSION001", s + 8, [proto.itch_U(10, 0, 4, 40, 15, px + 400)]))
    assert m.tob[0][ASK] == (px + 400, 15, True) and [t["px"] for t in m.tus[-2:]] == [px + 600, px + 400] and m.table[40 & 255]["side"] == ASK
    m.feed(proto.mold_packet(b"SESSION001", s + 9, [proto.itch_D(10, 0, 40), proto.itch_D(10, 0, 5), proto.itch_D(10, 0, 3)]))
    assert m.tob[0][ASK] == (0, 0, False) and m.tob[0][BID] == (0, 0, False) and not m.table


def test_model_risk_reasons_in_order() -> None:
    px = MID
    for kw, reason in ((dict(arm=False), "rej_arm"), (dict(kill=True), "rej_kill"), (dict(qty=600), "rej_size"), (dict(qty=0), "rej_size"),
                       (dict(max_pos=50), "rej_pos"), (dict(band=10), "rej_band"), (dict(arm=False, kill=True), "rej_arm")):
        m = mk(Cfg(**{**dict(thr=MID + 300, max_pos=2000, max_qty=500, band=20_000), **kw}))
        s = open_day(m)
        m.feed(proto.mold_packet(b"SESSION001", s, [A(m, 0, 1, "B", 100, px - 100), A(m, 0, 2, "S", 100, px + 100)]))
        assert m.cnt[reason] == 1 and m.cnt["cand"] == 1 and not m.orders, (kw, reason)
    m = mk()
    s = open_day(m)
    m.feed(proto.mold_packet(b"SESSION001", s, [A(m, 0, 2, "S", 100, px + 100)]))          # no bid: band refuses
    assert m.cnt["rej_band"] == 1
    m.feed(proto.mold_packet(b"SESSION001", s + 1, [A(m, 0, 1, "B", 100, px - 100), A(m, 0, 3, "S", 100, px + 400)]))   # above the threshold: no candidate
    assert m.cnt["cand"] == 1
    m.feed(proto.mold_packet(b"SESSION001", s + 3, [A(m, 0, 4, "S", 100, px + 300)]))      # exactly the threshold: a candidate that passes
    assert len(m.orders) == 1 and m.orders[0]["ref"] == 1 and m.pos[0] == 100
    f = m.orders[0]["frame"]
    assert len(f) == 59 and f[13:21] == b"AAA     " and field(f, 21, 8) == px + 300 and field(f, 9, 4) == 100 and f[34:48] == b"FDA11000000001"


def test_model_overflows_and_inexact() -> None:
    m = mk()
    s = open_day(m)
    px = MID
    N = 1 << m.cfg.ord_aw
    m.feed(proto.mold_packet(b"SESSION001", s, [A(m, 0, 1, "B", 10, px - 10), A(m, 0, 1, "B", 10, px - 10), A(m, 0, 1 + N, "B", 10, px - 20)]))
    assert (m.cnt["odup"], m.cnt["oovf"]) == (1, 1) and m.inexact[0] and not m.inexact[1]
    m.feed(proto.mold_packet(b"SESSION001", s + 3, [A(m, 1, 100 + k, "S", 5, px + 10 * (k + 1)) for k in range(9)]))
    assert m.cnt["lvovf"] == 1 and m.inexact[1] and len(m.lv[1][ASK]) == 8
    m.feed(proto.mold_packet(b"SESSION001", s + 12, [proto.itch_D(10 + 1, 0, 108)]))        # delete of the order that never got a level
    assert m.cnt["lvmiss"] == 1


def test_generator_is_deterministic_and_covers_every_type() -> None:
    cfg = Cfg(thr=MID + 300)
    a = gen.Gen(5, cfg).stream(400, p_gap=0.02, p_dup=0.02, p_overlap=0.03)
    b = gen.Gen(5, cfg).stream(400, p_gap=0.02, p_dup=0.02, p_overlap=0.03)
    assert [i.pkt for i in a] == [i.pkt for i in b]
    assert [i.pkt for i in gen.Gen(6, cfg).stream(400)] != [i.pkt for i in a]
    m = Model(cfg)
    for it in gen.Gen(5, cfg).stream(3000):
        m.feed(it.pkt)
    for k in ("m_a", "m_f", "m_e", "m_c", "m_x", "m_d", "m_u", "m_s", "m_r", "m_skip", "unwatch", "omiss", "fire", "cand", "hb"):
        assert m.cnt[k] > 0, k
    digest = hashlib.sha256(b"".join(i.pkt for i in gen.Gen(5, cfg).stream(400))).hexdigest()
    assert len(digest) == 64


def test_latency_record_matches_datasheet() -> None:
    rec = ROOT / "results" / "b110" / "latency_sim.json"
    if not rec.is_file():
        return
    j = json.loads(rec.read_text())
    doc = (D / "docs" / "itch_ouch.md").read_text()
    assert j["non_speculative"]["book_update_add"] == 7 and j["non_speculative"]["decoded_event"] == 2 and j["non_speculative"]["mold_message_out"] == 1
    assert j["non_speculative"]["first_order_word"] == 8 and j["speculative"]["first_order_word"] == 3 and j["non_speculative"]["book_update_replace_second"] == 8
    for row in ("| message delivered by mold_rx (`m_v`) | 1 |", "| decoded event (`e_v`) | 2 |", "| first word of the order frame, speculative start | 3 |",
                "| first word of the order frame, started at the verdict | 8 |", "| the second change of a Replace | 8 |"):
        assert row in doc, row
