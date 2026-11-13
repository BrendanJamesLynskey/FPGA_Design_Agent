"""Reference model of eth_mac_rgmii 0.2's receive classification, store-and-forward output, pause and statistics.

Plain Python written from the standards, not from the RTL:
- IEEE 802.3 clause 3.2.3: the individual/group bit is the least significant bit of the first destination byte; the
  broadcast address is all ones.
- The multicast hash index is the 6 least significant bits of the Ethernet CRC-32 register (reflected, initial value
  all ones, not inverted) over the 6 destination bytes, i.e. Linux's ether_crc_le(6, addr) & 0x3f. zlib's CRC-32 is
  that register inverted.
- IEEE 802.1Q: a tag is the TPID 0x8100 (or 0x88A8, 802.1ad) at bytes 12-13 and the TCI at bytes 14-15.
- IEEE 802.3 clause 31 and annex 31B: MAC control frames have EtherType 0x8808; a pause frame has opcode 0x0001, is
  sent to 01-80-C2-00-00-01, and its quanta (bytes 16-17) count 512 bit times.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

BCAST = b"\xff" * 6
PAUSE_DA = bytes.fromhex("0180c2000001")

STAT_NAMES = ["rx_frames_good", "rx_octets_good", "rx_frames_bad", "rx_fcs_err", "rx_runt", "rx_giant", "rx_phy_err",
              "rx_bcast", "rx_mcast", "rx_pause", "rx_vlan", "rx_filtered", "rx_dropped", "rx_fifo_ovf",
              "tx_frames_good", "tx_octets_good", "tx_frames_bad", "tx_bcast", "tx_mcast", "tx_pause", "tx_underrun"]


def fcs(b: bytes) -> bytes:
    return struct.pack("<I", zlib.crc32(b) & 0xFFFFFFFF)


def hash_index(da: bytes) -> int:
    """Bit of the 64-bin multicast hash for this destination address."""
    return (zlib.crc32(bytes(da)) ^ 0xFFFFFFFF) & 0x3F


def mac_int(b: bytes) -> int:
    return int.from_bytes(b, "big")


@dataclass
class FilterCfg:
    own: bytes = bytes.fromhex("020000000001")       # a locally administered address
    promisc: bool = False
    bcast_en: bool = True
    mcast_all: bool = False
    hash_bits: int = 0                                 # bit i set: hash index i accepted
    exact: list = field(default_factory=list)          # enabled exact-table addresses (bytes)


def accept(da: bytes, c: FilterCfg) -> bool:
    if c.promisc or da == c.own:
        return True
    if da == BCAST:
        return c.bcast_en
    if da[0] & 1:
        return c.mcast_all or da in c.exact or bool((c.hash_bits >> hash_index(da)) & 1)
    return False


def classify(frame: bytes, c: FilterCfg) -> dict:
    """The per-frame flags the cut-through view reports (frame without FCS, at least 18 bytes)."""
    da, et = frame[:6], frame[12:14]
    vlan = et in (b"\x81\x00", b"\x88\xa8")
    ctrl = et == b"\x88\x08"
    return {"match": accept(da, c), "bcast": da == BCAST, "mcast": bool(da[0] & 1) and da != BCAST,
            "vlan": vlan, "tci": mac_int(frame[14:16]) if vlan else 0, "ctrl": ctrl,
            "pause": ctrl and frame[14:16] == b"\x00\x01" and (da == PAUSE_DA or da == c.own),
            "quanta": mac_int(frame[16:18])}


def sf_output(frame: bytes, strip: bool) -> tuple[bytes, int | None]:
    """What the store-and-forward output carries for a kept frame: (bytes, TCI or None)."""
    if strip and frame[12:14] in (b"\x81\x00", b"\x88\xa8"):
        return frame[:12] + frame[16:], mac_int(frame[14:16])
    return frame, None


def pause_frame(sa: bytes, quanta: int) -> bytes:
    """The 60 data bytes of a pause frame (annex 31B), FCS not included."""
    return (PAUSE_DA + sa + b"\x88\x08\x00\x01" + struct.pack(">H", quanta)).ljust(60, b"\x00")


def new_stats() -> dict:
    return {k: 0 for k in STAT_NAMES}


def count_rx(st: dict, frame_fcs: bytes, kind: str, c: FilterCfg, filter_on: bool, vlan_on: bool,
             pause_on: bool) -> None:
    """Count one received frame (bytes with FCS); kind is good/fcs/runt/giant/er as the bench made it."""
    good = kind == "good"
    if good:
        f = classify(frame_fcs[:-4], c)
        st["rx_frames_good"] += 1
        st["rx_octets_good"] += len(frame_fcs)
        st["rx_bcast"] += f["bcast"]
        st["rx_mcast"] += f["mcast"]
        st["rx_pause"] += pause_on and f["pause"]
        st["rx_vlan"] += f["vlan"]
        st["rx_filtered"] += filter_on and not f["match"] and not (pause_on and f["ctrl"])   # consumed control frames are not "filtered"
    else:
        st["rx_frames_bad"] += 1
    st["rx_fcs_err"] += kind == "fcs"
    st["rx_runt"] += kind == "runt"
    st["rx_giant"] += kind == "giant"
    st["rx_phy_err"] += kind == "er"


def count_tx(st: dict, data: bytes, good: bool, min_data: int, pause: bool = False) -> None:
    """Count one transmitted frame from its data bytes (before padding)."""
    if good:
        st["tx_frames_good"] += 1
        st["tx_octets_good"] += max(len(data), min_data) + 4
        st["tx_bcast"] += data[:6] == BCAST
        st["tx_mcast"] += bool(data[0] & 1) and data[:6] != BCAST
    else:
        st["tx_frames_bad"] += 1
    st["tx_pause"] += pause


def pause_byte_times(quanta: int) -> int:
    """A pause of `quanta` lasts quanta x 512 bit times = quanta x 64 byte times."""
    return quanta * 64
