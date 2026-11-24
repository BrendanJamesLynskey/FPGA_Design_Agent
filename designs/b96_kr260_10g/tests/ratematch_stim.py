"""Block streams for the rate-matching benches (brief 96C): what the receive PCS offers the elastic buffer, one entry per write clock.

An entry is (v, d, c, os): ``v`` is 0 once in 33 clocks (the gearbox gap of the receive PCS: 32 blocks in 33 words) and when the stream
has nothing to say; ``d``/``c`` the decoded XGMII block (lane i = bits 8i+7:8i of d, bit i of c = control); ``os`` marks an ordered set
(shown by the decoder as an all-idle control block). Frames are real: preamble, payload, FCS, terminate (``pcs.frame_words``), from lane 0
or lane 4, with an inter-frame gap of whole idle blocks chosen by the caller."""

from __future__ import annotations

import random

from designs.b96_kr260_10g.model import pcs

IDLE = (0x0707070707070707, 0xFF)


def make_frames(rng: random.Random, n: int, sizes=(64, 80, 128, 333, 1000)):
    out = []
    for i in range(n):
        size = rng.choice(sizes)
        payload = bytes([i & 0xFF, (i >> 8) & 0xFF]) + bytes(rng.randrange(256) for _ in range(size - 2))
        out.append(payload)
    return out


def block_stream(rng: random.Random, frames, gaps, os_every=0, err_every=0):
    """Blocks of the whole stream: idle blocks (gaps[i] of them) before frame i, then the frame; optional ordered-set and
    error blocks between frames. Returns the list of (d, c, os)."""
    blocks = []
    for i, f in enumerate(frames):
        for _ in range(gaps[i % len(gaps)]):
            blocks.append((IDLE[0], IDLE[1], 0))
        if os_every and i % os_every == os_every - 1:
            blocks.append((IDLE[0], IDLE[1], 1))
        if err_every and i % err_every == err_every - 1:
            blocks.append((0xFEFEFEFEFEFEFEFE, 0xFF, 0))
        for d, c in pcs.frame_words(f, lane0=(i % 3 != 1)):
            blocks.append((d, c, 0))
    return blocks


def is_start(d, c):
    """True for a block that starts a frame: Start (0xFB) in lane 0 (control mask 0x01) or in lane 4 (mask 0x1F), the two the receive PCS produces."""
    return (c == 0x01 and d & 0xFF == 0xFB) or (c == 0x1F and (d >> 32) & 0xFF == 0xFB)


def to_entries(blocks, phase=0, gap_every=33, pad=600, pause_after_start=0):
    """Write-clock entries: a block per clock except one clock in `gap_every` (phase picks which); `pad` idle blocks follow the stream.
    ``pause_after_start`` (brief 152): after every frame-start block, that many clocks with nothing to write (v = 0), so that the elastic buffer drains
    right after the start block is read and the reader has to stall inside the frame."""
    blocks = list(blocks) + [(IDLE[0], IDLE[1], 0)] * pad
    ent = []
    k = 0
    i = 0
    while i < len(blocks):
        if (k + phase) % gap_every == gap_every - 1:
            ent.append((0, 0, 0, 0))
        else:
            d, c, os = blocks[i]
            ent.append((1, d, c, os))
            i += 1
            if pause_after_start and not os and is_start(d, c):
                ent.extend([(0, 0, 0, 0)] * pause_after_start)
                k += pause_after_start
        k += 1
    return ent


def frames_of(blocks):
    """Frames (payload bytes, fcs_ok) found in a list of (d, c) blocks by the independent parser."""
    return [(f["data"], f.get("fcs_ok")) for f in pcs.parse_xgmii([(d, c) for d, c in blocks]) if "data" in f]
