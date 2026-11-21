"""Host side of the ITCH path (brief 127, build rm_gp_itch): synthetic MoldUDP64/ITCH frames, the replay-memory image, the expected order frames, and the software check of the order
frames that come back over the fibre loopback. Pure Python, no board: the same functions drive the simulation tests, and `b127_bench.py` drives the board with them.

Everything is synthetic: the messages come from designs/b110_itch_ouch/model/gen.py (seeded), the addresses are the bench's private ones (192.168.58.0/24, locally administered MACs).

What the loopback does and does not test (docs/itch_integration.md section 7): with the fibre looped back the board receives what it transmits. The replay source transmits the
synthetic feed frames, they come back and drive the ITCH path, the path transmits order frames, and those come back too and are captured (TCP frames, last 8). That exercises the
whole digital chain and the transmit and receive PCS and MAC with real frames. It does NOT test: a second MAC (the loop shares the frame check logic and the 66-to-64 gearbox
conventions of this design with itself), the frame check against another implementation, an exchange's or a NIC's acceptance of the TCP segment (the stand-in's TCP checksum is 0),
the clock difference between two ends (rate matching sees no offset), or any timing of a real network.
"""

from __future__ import annotations

import struct
import zlib

from designs.b110_itch_ouch.model import proto

BROADCAST = b"\xff" * 6
DEFAULTS = {
    "my_mac": bytes.fromhex("02000000580a"),          # 02:00:00:00:58:0A, the reset value of MY_MAC_LO/HI (first byte on the wire in bits 7:0 of the register)
    "venue_mac": bytes.fromhex("02000000580f"),
    "my_ip": "192.168.58.10", "venue_ip": "192.168.58.15", "sport": 5800, "order_port": 5801, "feed_port": 5810,
}


def ip_bytes(a: str) -> bytes:
    return bytes(int(x) for x in a.split("."))


def csum16(b: bytes) -> int:
    """Internet checksum (RFC 1071) of b (padded with a zero byte if odd): the value to put in the field."""
    if len(b) % 2:
        b += b"\0"
    s = sum(struct.unpack(f">{len(b) // 2}H", b))
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return (~s) & 0xFFFF


def eth_ip_udp(payload: bytes, *, dst_mac: bytes, src_mac: bytes, src_ip: str, dst_ip: str, sport: int, dport: int, ident: int = 0, ttl: int = 64, udp_cksum: bool = False) -> bytes:
    """One Ethernet frame (without FCS) carrying a UDP datagram, padded to 60 bytes. The UDP checksum is 0 (none) unless udp_cksum."""
    udp_len = 8 + len(payload)
    ip = struct.pack(">BBHHHBBH4s4s", 0x45, 0, 20 + udp_len, ident, 0x4000, ttl, 17, 0, ip_bytes(src_ip), ip_bytes(dst_ip))
    ip = ip[:10] + struct.pack(">H", csum16(ip)) + ip[12:]
    udp = struct.pack(">HHHH", sport, dport, udp_len, 0)
    if udp_cksum:
        pseudo = ip_bytes(src_ip) + ip_bytes(dst_ip) + struct.pack(">BBH", 0, 17, udp_len)
        c = csum16(pseudo + udp + payload) or 0xFFFF
        udp = udp[:6] + struct.pack(">H", c)
    f = dst_mac + src_mac + b"\x08\x00" + ip + udp + payload
    return f.ljust(60, b"\0")


def mcast_mac(group_ip: str) -> bytes:
    b = ip_bytes(group_ip)
    return bytes([0x01, 0x00, 0x5E, b[1] & 0x7F, b[2], b[3]])


def words64(frame: bytes) -> list[int]:
    return [int.from_bytes(frame[i:i + 8].ljust(8, b"\0"), "little") for i in range(0, len(frame), 8)]


def replay_image(frames: list[tuple], end_gap: int = 0) -> list[int]:
    """The replay memory for [(frame without FCS, gap clocks before it[, poison])]: header word {poison, gap, length}, then the frame's words; ends with a zero header whose gap field is the
    pause between passes (RP_CFG). poison = 1 makes the MAC's FCS of that frame wrong. Max 256 words."""
    img: list[int] = []
    for fr in frames:
        f, gap = fr[0], fr[1]
        pz = int(fr[2]) if len(fr) > 2 else 0
        assert 60 <= len(f) <= 1514
        img.append((pz << 32) | (gap << 16) | len(f))
        img += words64(f)
    img.append(end_gap << 16)
    assert len(img) <= 256, f"{len(img)} words do not fit the 256-word replay memory"
    return img


def split_frames_for_memory(frames: list[tuple], capacity: int = 255) -> list[list[tuple[bytes, int]]]:
    """Cut a long list of frames into chunks that each fit the replay memory (the host reloads between chunks)."""
    chunks, cur, n = [], [], 1
    for fr in frames:
        w = 1 + (len(fr[0]) + 7) // 8
        if n + w > capacity:
            chunks.append(cur)
            cur, n = [], 1
        cur.append(fr)
        n += w
    if cur:
        chunks.append(cur)
    return chunks


def xgmii_words(frame: bytes, *, lane4: bool = False, bad_fcs: bool = False) -> list[tuple[int, int]]:
    """XGMII (data, control) words of one frame: start, preamble, data, FCS (wrong when bad_fcs), terminate, idles in the rest of the last word; the same as
    designs/b96_kr260_10g/model/pcs.py frame_words with a switch for a bad FCS."""
    fcs = bytearray(zlib.crc32(frame).to_bytes(4, "little"))
    if bad_fcs:
        fcs[0] ^= 0x5A
    data = bytes([0xFB] + [0x55] * 6 + [0xD5]) + frame + bytes(fcs)
    cs = [1] + [0] * (len(data) - 1)
    if lane4:
        data = bytes([0x07] * 4) + data
        cs = [1] * 4 + cs
    data += bytes([0xFD])
    cs += [1]
    while len(data) % 8:
        data += bytes([0x07])
        cs += [1]
    return [(int.from_bytes(data[i:i + 8], "little"), sum(b << j for j, b in enumerate(cs[i:i + 8]))) for i in range(0, len(data), 8)]


IDLE_WORD = (0x0707070707070707, 0xFF)


# ---------------------------------------------------------------------------------------------------- expected order frames
def tcp_stub_frame(payload59: bytes, *, my_mac: bytes, venue_mac: bytes, my_ip: str, venue_ip: str, sport: int, dport: int, seq: int, ack: int) -> bytes:
    """The 113-byte frame the stand-in order_seg builds: Ethernet, IPv4 (ID 0, DF, TTL 64, TCP), TCP (PSH+ACK, window 0xFFFF, checksum 0) and the SoupBinTCP packet."""
    assert len(payload59) == 59
    ip = struct.pack(">BBHHHBBH4s4s", 0x45, 0, 99, 0, 0x4000, 64, 6, 0, ip_bytes(my_ip), ip_bytes(venue_ip))
    ip = ip[:10] + struct.pack(">H", csum16(ip)) + ip[12:]
    tcp = struct.pack(">HHIIBBHHH", sport, dport, seq & 0xFFFFFFFF, ack & 0xFFFFFFFF, 0x50, 0x18, 0xFFFF, 0, 0)
    f = venue_mac + my_mac + b"\x08\x00" + ip + tcp + payload59
    assert len(f) == 113
    return f


def tcp_frame_valid(payload59: bytes, **kw) -> bytes:
    """The same frame with a CORRECT TCP checksum: what tcp_fast (brief 119) sends. Used by the check to say what the stand-in's frame lacks."""
    f = bytearray(tcp_stub_frame(payload59, **kw))
    tcp = bytes(f[34:])
    pseudo = f[26:30] + f[30:34] + struct.pack(">BBH", 0, 6, len(tcp))
    f[50:52] = struct.pack(">H", csum16(bytes(pseudo) + tcp))
    return bytes(f)


def check_order_frame(frame: bytes, expect59: bytes, **kw) -> list[str]:
    """Problems of one returned order frame against the model's 59-byte packet and the template; an empty list means it matches byte for byte (the TCP checksum is excluded: 0 in the stand-in)."""
    exp = tcp_stub_frame(expect59, **kw)
    if len(frame) != len(exp):
        return [f"length {len(frame)} != {len(exp)}"]
    bad = [i for i in range(len(exp)) if frame[i] != exp[i]]
    return [f"byte {i}: {frame[i]:02x} != {exp[i]:02x}" for i in bad[:8]] + (["..."] if len(bad) > 8 else [])
