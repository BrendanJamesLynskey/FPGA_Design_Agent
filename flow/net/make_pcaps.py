#!/usr/bin/env python3
"""Write the brief-40 sample traffic and its expected rewrite output as pcap files (results/b40/pcap/), so the
stimulus can be opened in Wireshark or replayed by a later hardware-in-the-loop run. Needs scapy (a test-time tool)."""
from __future__ import annotations

import sys
from pathlib import Path

from flow.net import model, traffic
from flow.net.tests.test_40_rewrite_rtl import case


def main(out: str = "results/b40/pcap") -> int:
    d = Path(out)
    d.mkdir(parents=True, exist_ok=True)
    traffic.write_pcap(d / "mix_seed101_in.pcap", traffic.mix(101, 400, max_payload=80))
    frames, hdrs, acts = case(41)
    traffic.write_pcap(d / "rewrite_seed41_in.pcap", frames)
    outs = [o for o, _, _ in (model.rewrite(f, h, a) for f, h, a in zip(frames, hdrs, acts)) if o is not None]
    traffic.write_pcap(d / "rewrite_seed41_expected.pcap", outs)
    for p in sorted(d.glob("*.pcap")):
        print(p, p.stat().st_size)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
