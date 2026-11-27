"""A behavioural model of the AMD AXI DMA (PG021 v7.1) in scatter-gather mode, built only from what the product guide documents (brief 241;
owner rule: vendor IP we cannot see inside gets our own model, written from the public document, with its validity stated).

Sources, all PG021 v7.1 (2025-06-24), chapter 3 "Performance" and chapter 4 "Designing with the Core" (cited, summarised in our words):
  * Table 1 (latency, default configuration, clocks): MM2S: a tail-descriptor write to the first descriptor-fetch address 10;
    descriptor-fetch address to the first data read address 28; first data read address to the first stream beat 6. S2MM: tail write to
    the descriptor fetch 10; the first stream beat to the first write address 39.
  * Table 2 (throughput, 10,000 bytes at 100 MHz, 32-bit): MM2S 399.04 MB/s (99.76 % of the 400 MB/s the port allows); S2MM 298.59 MB/s
    (74.64 %). Measured by AMD from the first read address (MM2S) or first stream beat (S2MM) to the end of the transfer.
  * A descriptor is 16 words (64 bytes) aligned to 64 bytes; 13 words are used (Table 25).
  * Max burst size per channel: 2 to 256 beats (default 16); bursts do not cross 4 KB.

What the model does: the MM2S channel moves one beat a clock after its start-up latency; the S2MM channel needs a gap between bursts that
reproduces the documented 298.59 MB/s for 10,000 bytes. The gap (g = 5.2 clocks per 16-beat burst) is OUR inference from Table 2 (the guide gives
no S2MM gap); it is fitted to that one number and is not a vendor figure. The start-up latencies are the table's, which include the memory and
interconnect of AMD's test bench, whose latency the guide does not state: the comparison with our engine is therefore at equal memory latency
only after that is allowed for (the report's table says so).

Validity envelope (outside it the functions raise): 32-bit memory-mapped and stream data, burst 16, one channel active, default
configuration, transfers of at least one beat. The model has NOT been checked against the vendor core (no simulation or board run of the
vendor IP; a conformance table is in results/241_dma/README.md: each row is "documented" or "inferred").
"""
from __future__ import annotations

BEAT_BYTES = 32 // 8
BURST = 16
MM2S = {"tail_to_sg_ar": 10, "sg_ar_to_data_ar": 28, "data_ar_to_stream": 6}
S2MM = {"tail_to_sg_ar": 10, "stream_to_aw": 39}
S2MM_EFFICIENCY = 0.7464                      # Table 2
MM2S_EFFICIENCY = 0.9976
#: inferred: the clocks between S2MM bursts that make 10,000 bytes take the documented time: 10,000 B at 298.59 MB/s and 100 MHz is 3,349 clocks,
#: of which 39 are the start-up latency and 2,500 the beats, over 156 gaps between the 157 bursts of 16 beats
S2MM_GAP = round((10000 / 298.59 * 100 - 39 - 2500) / 156, 2)
DESC_BYTES = 64


def _check(nbytes: int, beat_bytes: int, burst: int):
    if beat_bytes != BEAT_BYTES or burst != BURST or nbytes < beat_bytes:
        raise ValueError("outside the validity envelope of the AXI DMA model (32-bit data, 16-beat bursts, at least one beat)")


def mm2s_clocks(nbytes: int, beat_bytes: int = BEAT_BYTES, burst: int = BURST) -> dict:
    """Clocks of one MM2S descriptor from the tail-descriptor write: first stream beat, last stream beat."""
    _check(nbytes, beat_bytes, burst)
    first = sum(MM2S.values())
    beats = nbytes // beat_bytes
    last = first + beats - 1
    return {"first_beat": first, "last_beat": last, "span": beats}


def s2mm_clocks(nbytes: int, beat_bytes: int = BEAT_BYTES, burst: int = BURST) -> dict:
    """S2MM, from the first stream beat (the table's reference point): the first write address and the last write beat."""
    _check(nbytes, beat_bytes, burst)
    beats = nbytes // beat_bytes
    nb = -(-beats // burst)
    last = S2MM["stream_to_aw"] + beats + (nb - 1) * S2MM_GAP
    return {"first_aw": S2MM["stream_to_aw"], "last_beat": round(last, 1), "span": round(last, 1)}


def mm2s_throughput_bytes_per_clock(nbytes: int, **kw) -> float:
    """What Table 2 measures for MM2S: bytes over (first data read address to the last stream beat)."""
    c = mm2s_clocks(nbytes, **kw)
    return nbytes / (c["span"] + MM2S["data_ar_to_stream"])


def s2mm_throughput_bytes_per_clock(nbytes: int, **kw) -> float:
    """What Table 2 measures for S2MM: bytes over (first stream beat to the last write beat)."""
    c = s2mm_clocks(nbytes, **kw)
    return nbytes / c["last_beat"]
