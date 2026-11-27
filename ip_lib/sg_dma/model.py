"""Golden model for ip_lib/sg_dma (brief 241): the descriptor format, the burst split and the status word, written from the
datasheet's definitions (DATASHEET.md), not from the RTL.

The engine's contract in one place: a descriptor names a buffer (address, length in bytes); the engine moves the buffer in INCR
bursts of at most `max_burst` beats that never cross a 4 KB boundary; the descriptor's status word reports DONE, ERR, BAD and the
bytes moved. `split` is the burst list; `status` the word the engine writes back; `bad` the misalignment rule.
"""
from __future__ import annotations

import struct

DESC_BYTES = 16
DONE, ERR, BAD = 1 << 31, 1 << 30, 1 << 29
IOC = 1 << 31

# register offsets (AXI4-Lite)
CTRL, STATUS, RING_LO, RING_HI, RING_SIZE, HEAD, TAIL, IRQ_THRESH, DONE_COUNT, ERR_REG = (0x00, 0x04, 0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24)


def pack(addr: int, length: int, ioc: bool = False) -> bytes:
    """A descriptor as software writes it: word 3 (status) is zero."""
    return struct.pack("<IIII", addr & 0xFFFFFFFF, (addr >> 32) & 0xFFFFFFFF, (length & 0xFFFFFF) | (IOC if ioc else 0), 0)


def unpack_status(word: int) -> dict:
    return {"done": bool(word & DONE), "err": bool(word & ERR), "bad": bool(word & BAD), "code": (word >> 24) & 3, "bytes": word & 0xFFFFFF}


def bad(addr: int, length: int, beat_bytes: int) -> bool:
    """Zero length, a length that is not a whole number of beats, or a buffer address that is not beat aligned."""
    return length == 0 or length % beat_bytes != 0 or addr % beat_bytes != 0


def split(addr: int, length: int, beat_bytes: int, max_burst: int) -> list[tuple[int, int]]:
    """The bursts (start address, beats) of one buffer: at most max_burst beats, none across a 4 KB boundary, the rest in the
    next burst. The engine and the 4 KB rule agree on this list (the bench's memory checks every burst against it)."""
    out, rem = [], length
    while rem > 0:
        to4k = (4096 - (addr & 0xFFF)) // beat_bytes
        n = min(max_burst, to4k, rem // beat_bytes)
        out.append((addr, n))
        addr += n * beat_bytes
        rem -= n * beat_bytes
    return out


def status(length: int, is_bad: bool, err_code: int = 0) -> int:
    """The status word: DONE, ERR when a data beat answered non-OKAY (err_code = the first such response), BAD when nothing moved."""
    w = DONE | (BAD if is_bad else 0) | (ERR if err_code else 0) | ((err_code & 3) << 24)
    return w | (0 if is_bad else length & 0xFFFFFF)


def next_tail(tail: int, ring_size: int) -> int:
    return 0 if tail + 1 == ring_size else tail + 1


def irq_fires(since: int, thr: int, ioc: bool, drained: bool) -> bool:
    """After a completion, with `since` completions already counted since the last interrupt: raise the interrupt?"""
    return ioc or since + 1 >= max(thr, 1) or drained


def words(data: bytes, beat_bytes: int) -> list[int]:
    return [int.from_bytes(data[i:i + beat_bytes], "little") for i in range(0, len(data), beat_bytes)]
