"""P3 host check: CRC-32 over 1,000 random messages against zlib. Criteria: pilots/209/p3_crc_engine/preregistration.md."""
from __future__ import annotations

import random
import zlib

from report import Report, basics

SEED = 2093
FIXED = [0, 1, 2, 3, 4, 5, 7, 8, 63, 64, 65, 255, 256, 300, 513]
TOTAL = 1000


def messages() -> list[bytes]:
    r = random.Random(SEED)
    lens = FIXED + [r.randint(0, 400) for _ in range(TOTAL - len(FIXED))]
    return [bytes(r.getrandbits(8) for _ in range(n)) for n in lens]


def send(bus, msg: bytes) -> None:
    bus.wr(0x010, 1)
    full = len(msg) // 4
    for i in range(full):
        bus.wr(0x014, int.from_bytes(msg[4 * i:4 * i + 4], "little"))
    tail = msg[4 * full:]
    if tail:
        bus.wr(0x01C, len(tail))
        bus.wr(0x018, int.from_bytes(tail, "little"))


def run(bus, rep: Report, clk=None, **_) -> None:
    basics(bus, rep)
    bad, bad_cnt, bad_busy, nbusy = [], 0, 0, 0
    msgs = messages()
    for k, m in enumerate(msgs):
        send(bus, m)
        crc, cnt, busy = bus.rd(0x020), bus.rd(0x024), bus.rd(0x028)
        if crc != zlib.crc32(m):
            bad.append((k, len(m), f"{crc:08x}", f"{zlib.crc32(m):08x}"))
        if cnt != len(m):
            bad_cnt += 1
        if len(m) > 0 and len(m) % 4 == 0:
            nbusy += 1
            bad_busy += busy != len(m) // 4
    rep.data["lengths"] = sorted({len(m) for m in msgs})[:20]
    rep.data["first_mismatches"] = bad[:10]
    rep.crit("crc_equals_zlib_1000_messages", not bad, f"{len(bad)} of {len(msgs)} differ", "0 differ")
    rep.crit("byte_count_equals_length", bad_cnt == 0, f"{bad_cnt} wrong", 0)
    rep.crit("busy_cycles_one_per_word", bad_busy == 0, f"{bad_busy} of {nbusy} full-word messages wrong", "BUSY_CYCLES = length / 4")
    rep.crit("empty_message_crc_zero", zlib.crc32(b"") == 0, "model", "0x00000000")
