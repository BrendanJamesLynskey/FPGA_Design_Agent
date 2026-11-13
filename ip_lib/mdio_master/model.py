"""Reference model of a clause 22 management frame (IEEE 802.3 clause 22.2.4.5), written from the standard.

Frame, most significant bit first: PRE (32 ones), ST (01), OP (10 read, 01 write), PHYAD (5), REGAD (5), TA (write:
10; read: the station releases the line, the PHY drives the second bit 0), DATA (16). The PHY samples the line on
the rising edge of MDC; during a read it drives each bit after a rising edge, and the station samples it on the next.
"""
from __future__ import annotations


def frame(read: bool, phy: int, reg: int, data: int = 0) -> list[int | None]:
    """The 64 bit times as the station drives them: 0/1, or None where it releases the line."""
    bits = [1] * 32 + [0, 1] + ([1, 0] if read else [0, 1])
    bits += [(phy >> (4 - i)) & 1 for i in range(5)] + [(reg >> (4 - i)) & 1 for i in range(5)]
    if read:
        return bits + [None] * 18
    return bits + [1, 0] + [(data >> (15 - i)) & 1 for i in range(16)]


def phy_drives(read: bool, value: int) -> dict[int, int]:
    """Bit times the PHY drives during a read: the second TA bit (0) and the 16 data bits."""
    if not read:
        return {}
    return {47: 0, **{48 + i: (value >> (15 - i)) & 1 for i in range(16)}}
