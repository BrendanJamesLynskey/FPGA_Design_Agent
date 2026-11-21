"""Tests of the Python side of brief 119 without a simulator: checksums against outside vectors, the TCP endpoint, the owner and the exchange (model/softtcp.py)."""
from __future__ import annotations

import asyncio

from designs.b119_tcp_fast.model import orders, regs, soup, tcpref
from designs.b119_tcp_fast.model.softtcp import Endpoint
from designs.b119_tcp_fast.model.tcpref import Conn, FastModel
from designs.b119_tcp_fast.tests.netsim import Net, peer_view


# ---- the checksum reference against vectors that did not come from this repository
def test_rfc1071_example() -> None:
    # RFC 1071 section 3: the words 0001 f203 f4f5 f6f7 sum to ddf2 (folded); the checksum is its complement 220d
    data = bytes.fromhex("0001f203f4f5f6f7")
    assert tcpref.fold(tcpref.words_sum(data)) == 0xDDF2
    assert tcpref.checksum(data) == 0x220D


def test_published_ipv4_header() -> None:
    # the widely published example header (4500 0073 0000 4000 4011 .... c0a8 0001 c0a8 00c7) has checksum b861
    h = bytes.fromhex("45000073000040004011" "0000" "c0a80001c0a800c7")
    assert tcpref.checksum(h) == 0xB861


def test_odd_length_pads_low_byte() -> None:
    assert tcpref.words_sum(b"\x12\x34\x56") == 0x1234 + 0x5600


def test_checksum_in_place_sums_to_all_ones() -> None:
    """The identity every receiver uses: a header with its checksum in place sums to 0xFFFF (random headers)."""
    import random
    rng = random.Random(5)
    for _ in range(500):
        h = bytearray(rng.randbytes(20))
        h[10:12] = b"\0\0"
        h[10:12] = tcpref.checksum(bytes(h)).to_bytes(2, "big")
        assert tcpref.fold(tcpref.words_sum(bytes(h))) == 0xFFFF


def test_tcp_checksum_pseudo_header() -> None:
    c = Conn()
    f = tcpref.frame(c, 123456, 654321, 4096, 9, b"hello world")
    p = tcpref.parse(f)
    assert p.ok and p.payload == b"hello world" and p.seq == 123456 and p.ack == 654321 and p.win == 4096 and p.ident == 9 and p.df
    bad = bytearray(f)
    bad[60] ^= 1
    assert not tcpref.parse(bytes(bad)).tcp_ok
    bad = bytearray(f)
    bad[18] ^= 1
    assert not tcpref.parse(bytes(bad)).ip_ok


def test_frame_is_113_bytes_for_an_order() -> None:
    pay = orders.payload(1, 100, "AAA", 1_000_000)
    assert len(pay) == tcpref.PAYLEN == 59
    assert len(tcpref.frame(Conn(), 1, 2, 3, 4, pay)) == tcpref.FRAMELEN == 113


def test_soup_packets() -> None:
    assert soup.login_request("USER01", "PASSWORD01")[:3] == b"\x00\x2f" + b"L" and len(soup.login_request("USER01", "PASSWORD01")) == 49
    assert soup.client_heartbeat() == b"\x00\x01R"
    s = soup.Stream()
    pk = soup.sequenced(b"abc") + soup.server_heartbeat()
    assert s.feed(pk[:3]) == [] and s.feed(pk[3:]) == [(b"S", b"abc"), (b"H", b"")]
    m = orders.payload(7, 100, "AAA", 5)
    assert soup.parse_enter(m[3:])["userref"] == 7
    assert len(soup.ouch_accepted(1, 2, b"B", 3, b"AAA     ", 4, b"3", b"Y", 5, b"P", b"N", b"N", b"L", b"X" * 14)) == 64
    assert len(soup.ouch_rejected(1, 2, 0x13, b"X" * 14)) == 31


def test_fast_model_refusals() -> None:
    m = FastModel()
    assert m.refusal(10) == tcpref.REFUSE_NOT_ARMED
    m.arm_req = True
    assert m.refusal(10) == tcpref.REFUSE_STALE
    m.valid, m.snd_nxt, m.snd_una, m.snd_wnd = True, 1000, 1000, 59
    assert m.refusal(10) == 0
    m.snd_wnd = 58
    assert m.refusal(10) == tcpref.REFUSE_WINDOW
    m.snd_wnd, m.snd_nxt = 118, 1059
    assert m.refusal(10) == 0
    m.snd_nxt = 1060
    assert m.refusal(10) == tcpref.REFUSE_WINDOW
    m.snd_nxt, m.snd_una = 5, 2 ** 32 - 10                 # wraps: flight 15
    m.snd_wnd = 100
    assert m.refusal(10) == 0
    m.conn.mss = 58
    assert m.refusal(10) == tcpref.REFUSE_MSS
    m.conn.mss = 1460
    m.stale_limit, m.refreshed_at = 10, 100
    assert m.refusal(111) == 0 and m.refusal(112) == tcpref.REFUSE_STALE


# ---- the TCP endpoint on its own
def _pair():
    c = Conn()
    frames = {"a": [], "b": []}
    a = Endpoint("a", c, lambda f: frames["a"].append(f), iss=100, rto=10)
    b = Endpoint("b", peer_view(c), lambda f: frames["b"].append(f), iss=900, rto=10)
    b.listen()
    return a, b, frames


def _pump(a, b, frames, now, drop=lambda f: False):
    for _ in range(20):
        fa, fb = frames["a"][:], frames["b"][:]
        frames["a"].clear(); frames["b"].clear()
        if not fa and not fb:
            break
        for f in fa:
            if not drop(f):
                b.on_frame(f, now)
        for f in fb:
            a.on_frame(f, now)


def test_endpoint_handshake_data_and_acks() -> None:
    a, b, fr = _pair()
    a.connect(0)
    _pump(a, b, fr, 1)
    assert a.state == b.state == "ESTAB" and a.snd_una == a.snd_nxt == 101 and b.snd_una == b.snd_nxt == 901
    a.send_data(b"x" * 100, 2)
    _pump(a, b, fr, 3)
    assert bytes(b.stream_in) == b"x" * 100 and a.snd_una == a.snd_nxt == 201 and not a.rtx


def test_endpoint_out_of_order_and_retransmit() -> None:
    a, b, fr = _pair()
    a.connect(0)
    _pump(a, b, fr, 1)
    first = {"n": 0}

    def drop_first_data(f):
        p = tcpref.parse(f)
        if p.payload and first["n"] == 0:
            first["n"] = 1
            return True
        return False
    a.send_data(b"AAAA", 2)
    a.send_data(b"BBBB", 2)
    _pump(a, b, fr, 3, drop_first_data)
    assert bytes(b.stream_in) == b"" and b.stats["out_of_order"] == 1
    a.poll(20)
    _pump(a, b, fr, 21)
    assert bytes(b.stream_in) == b"AAAABBBB" and a.stats["retransmits"] == 1 and a.snd_una == a.snd_nxt


def test_endpoint_rejects_bad_checksum_and_foreign_frames() -> None:
    a, b, fr = _pair()
    a.connect(0)
    bad = bytearray(fr["a"][0])
    bad[40] ^= 0xFF
    b.on_frame(bytes(bad), 1)
    assert b.state == "LISTEN" and b.stats["bad_checksum"] == 1
    other = Conn(sport=1234)
    b.on_frame(tcpref.frame(other, 1, 0, 100, 0, b"", 0x02), 1)
    assert b.state == "LISTEN" and b.stats["wrong_connection"] == 1


def test_endpoint_drops_unacceptable_pure_ack() -> None:
    a, b, fr = _pair()
    a.connect(0)
    _pump(a, b, fr, 1)
    a.send_data(b"x" * 10, 2)
    _pump(a, b, fr, 3)
    stale_ack = tcpref.frame(a.conn, 100, b.snd_nxt, 100, 0, b"", 0x10)       # seq 100 < b.rcv_nxt
    b.on_frame(stale_ack, 4)
    assert b.stats["old_pure_ack_dropped"] == 1


# ---- the owner and the exchange, with the untimed stand-in for the block
def _go(coro):
    return asyncio.run(coro)


def test_session_login_orders_and_replies() -> None:
    async def scenario():
        n = Net(hb=10 ** 6)
        await n.start()
        assert n.ex.logged_in and n.owner.logged_in and n.owner.hw_armed
        for i in range(1, 11):
            assert n.order(i, qty=100 + i) is not None
            await n.run(3)
        await n.run(200)
        return n
    n = _go(scenario())
    login = soup.login_request("USER01", "PASSWORD01")
    assert bytes(n.ex.stream_in) == login + b"".join(n.sent_payloads)
    assert [o["reply"] for o in n.ex.orders] == ["A"] * 10
    assert [r["type"] for r in n.owner.responses] == ["A"] * 10 and [r["userref"] for r in n.owner.responses] == list(range(1, 11))
    assert n.owner.snd_una == n.owner.snd_nxt and not n.owner.rtx
    assert n.hw.fast.snd_una == n.owner.snd_una and n.hw.fast.snd_nxt == n.owner.snd_nxt
    assert n.ex.rcv_nxt == n.owner.snd_nxt and n.ex.stats["out_of_order"] == 0
    assert not n.owner.errors and n.owner.stats["retransmits"] == 0


def test_rejected_orders() -> None:
    async def scenario():
        n = Net(hb=10 ** 6)
        await n.start()
        n.order(1, qty=0)
        n.order(2, sym="ZZZZ")        # known
        n.order(3, sym="NOPE")
        n.order(4, px=0)
        n.order(5, qty=999_999)
        await n.run(300)
        return n
    n = _go(scenario())
    assert [o["reply"] for o in n.ex.orders] == ["J", "A", "J", "J", "A"]
    assert [r.get("reason") for r in n.owner.responses] == [0x13, None, 0x17, 0x1D, None]


def test_dropped_fast_path_segment_is_retransmitted_by_software() -> None:
    hw_frames = []

    def drop(frame, dest, idx):
        if dest != "ex":
            return False
        p = tcpref.parse(frame)
        if p.payload.startswith(b"\x00\x39U"):
            hw_frames.append(p.seq)
            return len(hw_frames) == 3
        return False

    async def scenario():
        n = Net(drop=drop, hb=10 ** 6)
        await n.start()
        for i in range(1, 7):
            n.order(i)
            await n.run(4)
        await n.run(3000)
        return n
    n = _go(scenario())
    login = soup.login_request("USER01", "PASSWORD01")
    assert len(n.world.dropped) == 1
    assert bytes(n.ex.stream_in) == login + b"".join(n.sent_payloads)
    assert n.owner.stats["retransmits"] >= 1 and n.ex.stats["out_of_order"] >= 1
    assert [o["reply"] for o in n.ex.orders] == ["A"] * 6 and not n.owner.rtx and not n.owner.errors


def test_client_heartbeat_takes_the_sequence_space_and_gives_it_back() -> None:
    async def scenario():
        n = Net(hb=300)
        await n.start()
        for i in range(1, 4):
            n.order(i)
            await n.run(5)
        await n.run(1000)                       # idle: heartbeats, server's too
        before = n.owner.snd_nxt
        n.order(4)
        await n.run(200)
        return n, before
    n, before = _go(scenario())
    assert n.owner.takeovers >= 2 and n.ex.client_hbs >= 2 and n.owner.server_hbs >= 2
    login = soup.login_request("USER01", "PASSWORD01")
    # the stream is the login, three orders, any heartbeats (3 bytes each), then the fourth order
    s = bytes(n.ex.stream_in)
    assert s.startswith(login + b"".join(n.sent_payloads[:3]))
    assert s.endswith(n.sent_payloads[3]) and (len(s) - len(login) - 4 * 59) % 3 == 0
    assert n.hw.fast.snd_nxt == n.owner.snd_nxt and not n.owner.errors


def test_window_closed_refuses_until_acked() -> None:
    async def scenario():
        n = Net(ex_window=100, hb=10 ** 6)
        await n.start()
        a = n.order(1)
        b = n.order(2)                 # 59 + 59 > 100 in flight
        await n.run(200)               # acked
        c = n.order(3)
        return n, a, b, c
    n, a, b, c = _go(scenario())
    assert a is not None and b is None and c is not None
    assert n.hw.fast.counters["ref_win"] == 1


def test_stale_state_is_refused_and_a_refreshing_owner_keeps_it_fresh() -> None:
    async def scenario(refresh: bool):
        n = Net(hb=10 ** 6)
        await n.start(stale_limit=50)
        n.owner.refresh_ticks = 25 if refresh else 0
        ok = n.order(1)
        await n.run(100)
        late = n.order(2)
        return n, ok, late
    n, ok, late = _go(scenario(False))
    assert ok is not None and late is None and n.hw.fast.counters["ref_stale"] == 1
    n, ok, late = _go(scenario(True))
    assert ok is not None and late is not None and n.owner.refresh_writes >= 3


def test_disarmed_block_refuses() -> None:
    async def scenario():
        n = Net(hb=10 ** 6)
        await n.start()
        await n.owner.bus.write(regs.CTRL, 0)
        return n, n.order(1)
    n, fr = _go(scenario())
    assert fr is None and n.hw.fast.counters["ref_arm"] == 1


def test_nothing_is_sent_by_software_while_the_fast_path_is_idle_and_armed() -> None:
    async def scenario():
        n = Net(hb=100000)
        await n.start()
        tx0 = n.owner.stats["tx"]
        await n.run(500)
        return n, tx0
    n, tx0 = _go(scenario())
    assert n.owner.stats["tx"] == tx0
