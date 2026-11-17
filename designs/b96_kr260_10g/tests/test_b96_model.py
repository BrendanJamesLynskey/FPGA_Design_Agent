"""The Python PCS reference against itself and against independent checks (brief 96). No simulator needed."""

from __future__ import annotations

import random

from designs.b96_kr260_10g.model import pcs

IDLE_W = pcs.IDLE_WORD


def line(frames, seed=1, gap=3, tail=140, lead=4800):
    """XGMII words for: idles, then each frame with `gap` idle words after it (>= 1 needed for IFG), then idles."""
    rng = random.Random(seed)
    w = [IDLE_W] * lead
    for f in frames:
        w += pcs.frame_words(f) + [IDLE_W] * (gap + rng.randrange(2))
    return w + [IDLE_W] * tail


def serial(words):
    tx = pcs.TxPcs()
    out = []
    i = 0
    while i < len(words):
        if tx.adv:
            out.append(tx.step(*words[i]))
            i += 1
        else:
            out.append(tx.step(0, 0))
    return out


def channel(words, offset, flips=()):
    bits = pcs.words_to_bits(words)[offset:]
    for f in flips:
        bits[f] ^= 1
    return pcs.bits_to_words(bits)


def frames_of(rx):
    return pcs.parse_xgmii([(d, c) for d, c, _ in rx.out])


def test_lfsr_properties() -> None:
    # the scrambler of zeros from a non-zero seed is the recurrence s[n] = s[n-39] ^ s[n-58]
    s = pcs.Scrambler(0x2AAAAAAAAAAAAAA & pcs.M58)
    seq = [(s.hist >> (57 - i)) & 1 for i in range(58)]    # oldest first
    seq = seq[::-1][::-1]
    out = [s.bit(0) for _ in range(500)]
    full = seq + out
    for n in range(58, len(full)):
        assert full[n] == full[n - 39] ^ full[n - 58]
    # period of the x^58+x^39+1 generator divides 2^58-1: check it is not tiny
    assert len(set(tuple(out[i:i + 20]) for i in range(400))) > 200


def test_descrambler_inverts_and_self_synchronises() -> None:
    rng = random.Random(5)
    data = [rng.getrandbits(64) for _ in range(40)]
    sc, ds = pcs.Scrambler(rng.getrandbits(58)), pcs.Descrambler(rng.getrandbits(58))   # unrelated seeds
    got = [ds.word(sc.word(d)) for d in data]
    assert got[2:] == data[2:]          # the first 58 bits (one word) are wrong, then it has synchronised
    assert got[0] != data[0]


def test_block_codes_round_trip() -> None:
    rng = random.Random(2)
    for _ in range(300):
        n = rng.randrange(0, 200)
        f = bytes(rng.getrandbits(8) for _ in range(60 + n))
        for d, c in pcs.frame_words(f) + [IDLE_W]:
            sh, p = pcs.encode_block(d, c)
            assert pcs.decode_block(sh, p) == (d, c, ""), (hex(d), hex(c))


def test_every_terminate_lane_is_produced() -> None:
    seen = set()
    for n in range(60, 70):
        for d, c in pcs.frame_words(bytes(n)):
            sh, p = pcs.encode_block(d, c)
            if sh == 2 and (p & 0xFF) in pcs.T_TERM:
                seen.add(p & 0xFF)
    assert seen == set(pcs.T_TERM)


def test_tx_pause_one_in_33() -> None:
    tx = pcs.TxPcs()
    advs = []
    for _ in range(330):
        advs.append(tx.adv)
        tx.step(*IDLE_W)
    assert advs.count(0) == 10 and all(advs[i] == 0 for i in range(32, 330, 33))


def test_end_to_end_any_alignment() -> None:
    rng = random.Random(9)
    frames = [bytes(rng.getrandbits(8) for _ in range(rng.randrange(60, 300))) for _ in range(12)]
    ws = serial(line(frames))
    for off in (0, 1, 2, 31, 33, 64, 65):
        rx = pcs.RxPcs()
        for w in channel(ws, off):
            rx.step(w)
        fr = [f for f in frames_of(rx) if f.get("fcs_ok")]
        assert rx.fsm.lock and rx.fsm.losses == 0
        assert [f["data"] for f in fr][-len(fr):] == frames[-len(fr):]
        assert len(fr) >= len(frames) - 1, (off, len(fr))


def test_lock_time_by_offset() -> None:
    ws = serial(line([bytes(60)], gap=3, tail=600, lead=100))
    times = []
    for off in range(0, 66):
        rx = pcs.RxPcs()
        for i, w in enumerate(channel(ws, off)):
            rx.step(w)
            if rx.fsm.lock:
                times.append(i)
                break
    assert len(times) == 66
    assert max(times) < 66 * 70 and min(times) >= 64          # blocks to lock: 64 good headers at least


def test_bit_errors_in_lock() -> None:
    rng = random.Random(4)
    frames = [bytes(rng.getrandbits(8) for _ in range(100)) for _ in range(60)]
    ws = serial(line(frames, tail=400))
    # a few isolated flips keep the lock; some frames fail the FCS
    base = 64 * 4900
    flips = [base + 5, base + 64 * 200 + 17, base + 64 * 400 + 40]
    rx = pcs.RxPcs()
    for w in channel(ws, 0, flips):
        rx.step(w)
    assert rx.fsm.lock and rx.fsm.losses == 0
    # a burst of bad headers (bits at the sync position every block) loses the lock, which then comes back
    # headers 01 -> 00 or 10 -> 11 flips are invalid only if both bits change; set 40 headers in a row to 00
    bits = pcs.words_to_bits(ws)
    for k in range(5000, 5040):
        bits[66 * k] = bits[66 * k + 1] = 0           # header 00: invalid
    rx = pcs.RxPcs()
    for w in pcs.bits_to_words(bits):
        rx.step(w)
    assert rx.fsm.losses >= 1 and rx.fsm.lock


def test_ordered_set_and_error_counts() -> None:
    d, c, note = pcs.decode_block(0b10, 0x4B)
    assert note == "os" and c == 0xFF
    assert pcs.decode_block(0b00, 0)[2] == "sh" and pcs.decode_block(0b11, 0)[2] == "sh"
    assert pcs.decode_block(0b10, 0xAB)[2] == "type"
