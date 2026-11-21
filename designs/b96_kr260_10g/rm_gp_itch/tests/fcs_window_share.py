"""The share of candidates that fall outside the FCS window (brief 127): for the seeded synthetic generator, how many Add Orders on the sell side at or below the threshold have more bytes after their last byte in their packet than the
window of docs/itch_integration.md section 4 (results/b127/fcs_window_unit_sim.json). `python3 -m designs.b96_kr260_10g.rm_gp_itch.tests.fcs_window_share <out json>`. Synthetic data only: a real feed's packet lengths are not known here."""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

from designs.b110_itch_ouch.model import gen, proto
from designs.b110_itch_ouch.model.ref import Cfg

ROOT = Path(__file__).resolve().parents[4]


def tails(pkt: bytes, thr: int):
    """For each sell Add (A or F) at or below thr in the Mold packet: the bytes after its last byte to the end of the payload."""
    n = int.from_bytes(pkt[18:20], "big")
    pos, out = 20, []
    for _ in range(n if n not in (0, 0xFFFF) else 0):
        ln = int.from_bytes(pkt[pos:pos + 2], "big")
        m = pkt[pos + 2:pos + 2 + ln]
        end = pos + 2 + ln
        if m[:1] in (b"A", b"F") and m[19:20] == b"S" and struct.unpack(">I", m[32:36])[0] <= thr:
            out.append(len(pkt) - end)
        pos = end
    return out


def main() -> None:
    w = json.loads((ROOT / "results/b127/fcs_window_unit_sim.json").read_text())
    win = {"speculative": w["speculative_largest_poisoned_tail_bytes"], "at_verdict": w["at_verdict_largest_poisoned_tail_bytes"]}
    cfg = Cfg(thr=gen.MID + 3 * gen.TICK)
    res = {"window_bytes": win, "by_messages_per_packet": {}}
    for k in (1, 3, 6):
        tl = []
        for seed in range(1, 21):
            g = gen.Gen(seed, cfg)
            for it in g.stream(400, max_per_pkt=k, preamble=True):
                tl += tails(it.pkt, cfg.thr)
        res["by_messages_per_packet"][str(k)] = {"candidates": len(tl), **{f"outside_{m}": sum(1 for t in tl if t > win[m]) for m in win},
                                                 **{f"share_outside_{m}": round(sum(1 for t in tl if t > win[m]) / max(1, len(tl)), 3) for m in win}, "mean_tail_bytes": round(sum(tl) / max(1, len(tl)), 1)}
    Path(sys.argv[1]).write_text(json.dumps(res, indent=1))
    print(json.dumps(res["by_messages_per_packet"]))


if __name__ == "__main__":
    main()
