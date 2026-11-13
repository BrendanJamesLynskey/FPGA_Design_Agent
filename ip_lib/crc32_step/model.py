"""Golden model of ip_lib/crc32_step, written from the CRC-32 definition (reflected, polynomial 0xEDB88320), not from
the RTL. zlib's CRC-32 of a buffer whose length is a multiple of 4 is
    crc = 0xFFFFFFFF; for each little-endian word w: crc = crc32_word(crc, w); result = crc ^ 0xFFFFFFFF
which tests check against zlib.crc32."""
from __future__ import annotations

POLY = 0xEDB88320


def crc32_bytes(crc: int, data: bytes) -> int:
    """The raw (no inversion) reflected update of crc by data, bit by bit."""
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ POLY if crc & 1 else crc >> 1
    return crc & 0xFFFFFFFF


def crc32_word(crc: int, word: int) -> int:
    """One crc32_step operation: the update by the four bytes of word, least significant first."""
    return crc32_bytes(crc & 0xFFFFFFFF, (word & 0xFFFFFFFF).to_bytes(4, "little"))
