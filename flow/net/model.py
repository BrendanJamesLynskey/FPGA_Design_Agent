"""Golden models for the packet-processing library (brief 40): plain Python, written from the standards (IEEE 802.3
frame format, IEEE 802.1Q tags, RFC 791 IPv4, RFC 8200 IPv6, RFC 768 UDP, RFC 793 TCP, RFC 1071/1624 checksums), not
from the RTL. The RTL is compared against these bit-exact; scapy (tests only) cross-checks the parser model.
"""
from __future__ import annotations

import zlib

# ------------------------------------------------------------------------------------------------ Ethernet / RMII

PREAMBLE = bytes([0x55] * 7 + [0xD5])


def fcs(frame: bytes) -> bytes:
    """The 4 FCS bytes as sent (CRC-32 of 802.3; zlib's crc32 is the same function), least significant first."""
    return (zlib.crc32(frame) & 0xFFFFFFFF).to_bytes(4, "little")


def dibits(data: bytes) -> list[int]:
    """Bytes to RMII dibits, earliest first: each byte least significant bit pair first."""
    return [(b >> s) & 3 for b in data for s in (0, 2, 4, 6)]


def rx_line(items, speed10: bool = False, rng=None):
    """Build the RMII receive pins clock by clock for a list of frames, and the expected receive output.

    items: list of dicts {frame: bytes, bad_fcs: bool, extra_dibits: 0..3, toggle: int (dibit pairs of CRS_DV
    toggling at the end), rx_er: bool, lead00: dibits of 00 before the preamble, pre_bytes: preamble bytes 1..7,
    ifg: dibits of idle after the frame}.
    Returns (lines [(crs_dv, rxd, rx_er)], expected [(bytes, bad)], counts)."""
    import random
    rng = rng or random.Random(0)
    lines: list[tuple[int, int, int]] = []
    expect = []
    cnt = {"ok": 0, "bad": 0, "fcs": 0, "runt": 0}
    rep = 10 if speed10 else 1
    for it in items:
        fr = it["frame"]
        f = bytearray(fcs(fr))
        if it.get("bad_fcs"):
            f[rng.randrange(4)] ^= 1 << rng.randrange(8)
        wire = fr + bytes(f)
        ds = [0] * it.get("lead00", 0) + dibits(bytes([0x55] * it.get("pre_bytes", 7)) + b"\xD5")
        dv = [1] * len(ds)
        er = [0] * len(ds)
        data = dibits(wire) + [rng.randrange(4) for _ in range(it.get("extra_dibits", 0))]
        ddv = [1] * len(data)
        t = it.get("toggle", 0)
        if t:
            # carrier lost with data still in the PHY FIFO: CRS_DV low on the first dibit of each nibble
            n = len(data)
            start = max(0, n - 2 * t)
            start += start % 2                    # nibble boundary (data starts nibble aligned after the SFD)
            for i in range(start, n - 1, 2):      # the last dibit keeps CRS_DV high (else it reads as the end)
                ddv[i] = 0
        der = [0] * len(data)
        if it.get("rx_er"):
            der[len(data) // 2 & ~1] = 1
            ddv[len(data) // 2 & ~1] = 1
        ds += data
        dv += ddv
        er += der
        ifg = it.get("ifg", 48)
        ds += [0] * ifg
        dv += [0] * ifg
        er += [0] * ifg
        for d, v, e in zip(ds, dv, er):
            lines += [(v, d, e)] * rep
        # expected output
        nbytes = len(wire) + it.get("extra_dibits", 0) // 4
        fcs_ok = not it.get("bad_fcs")
        aligned = it.get("extra_dibits", 0) % 4 == 0
        runt = len(wire) < 64
        bad = (not fcs_ok) or (not aligned) or runt or bool(it.get("rx_er"))
        if nbytes >= 5:
            expect.append((bytes(fr), int(bad)))
            cnt["ok" if not bad else "bad"] += 1
            cnt["fcs"] += int(not fcs_ok)
        cnt["runt"] += int(runt)
    return lines, expect, cnt


def tx_wire_frames(packets, min_data: int = 60) -> list[list[int]]:
    """Expected transmit wire per packet: the dibits of preamble, SFD, padded frame and FCS."""
    out = []
    for p in packets:
        fr = p + bytes(max(0, min_data - len(p)))
        out.append(dibits(PREAMBLE + fr + fcs(fr)))
    return out


# ------------------------------------------------------------------------------------------------ parser

TPIDS = (0x8100, 0x88A8, 0x9100)
# packed header, most significant field first (name, bits)
HDR_FIELDS = [("dmac", 48), ("smac", 48), ("tci0", 16), ("tci1", 16), ("etype", 16), ("proto", 8), ("ttl", 8),
              ("src", 128), ("dst", 128), ("sport", 16), ("dport", 16), ("l3off", 8), ("l4off", 8), ("flags", 16)]
HDR_W = sum(w for _, w in HDR_FIELDS)
FLAG_BITS = ["vlan_n0", "vlan_n1", "ipv4", "ipv6", "udp", "tcp", "l4", "frag", "err_ihl", "err_ver", "err_csum",
             "trunc"]


def csum16(data: bytes) -> int:
    """RFC 1071 ones' complement sum of 16-bit words (not inverted)."""
    if len(data) % 2:
        data = data + b"\0"
    s = 0
    for i in range(0, len(data), 2):
        s += (data[i] << 8) | data[i + 1]
        s = (s & 0xFFFF) + (s >> 16)
    return s


def parse(fr: bytes, max_vlan: int = 2) -> dict:
    """The parser's reference: what the streaming parser must report for one frame (no FCS)."""
    h = {k: 0 for k, _ in HDR_FIELDS}
    fl = {k: 0 for k in FLAG_BITS}
    n = len(fr)

    def need(k):              # the frame holds bytes [0, k)
        return n >= k

    def done():
        fl_val = sum(1 << i for i, k in enumerate(FLAG_BITS) if fl[k])
        h["flags"] = fl_val
        return h

    h["dmac"] = _partial(fr, 0, 6)
    h["smac"] = _partial(fr, 6, 6)
    tp = 12
    nv = 0
    while True:
        if not need(tp + 2):
            fl["trunc"] = 1
            _setv(fl, nv)
            return done()
        t = int.from_bytes(fr[tp:tp + 2], "big")
        if t in TPIDS and nv < max_vlan:
            h["tci0" if nv == 0 else "tci1"] = _partial(fr, tp + 2, 2)
            nv += 1
            if not need(tp + 4):
                fl["trunc"] = 1
                _setv(fl, nv)
                return done()
            tp += 4
            continue
        h["etype"] = t
        break
    _setv(fl, nv)
    l3 = tp + 2
    h["l3off"] = l3
    if h["etype"] == 0x0800:
        fl["ipv4"] = 1
        if not need(l3 + 1):
            fl["trunc"] = 1
            return done()
        ver, ihl = fr[l3] >> 4, fr[l3] & 15
        if ver != 4:
            fl["err_ver"] = 1
            return done()
        if ihl < 5:
            fl["err_ihl"] = 1
            return done()
        hl = ihl * 4
        if not need(l3 + hl):
            fl["trunc"] = 1
            _ipv4_partial(fr, l3, h, fl)
            return done()
        _ipv4_partial(fr, l3, h, fl)
        if csum16(fr[l3:l3 + hl]) != 0xFFFF:
            fl["err_csum"] = 1
        off = ((fr[l3 + 6] & 0x1F) << 8) | fr[l3 + 7]
        mf = (fr[l3 + 6] >> 5) & 1
        fl["frag"] = int(mf or off != 0)
        l4 = l3 + hl
        if h["proto"] in (6, 17) and off == 0:
            return _l4(fr, l4, h, fl)
        return done()
    if h["etype"] == 0x86DD:
        fl["ipv6"] = 1
        if not need(l3 + 1):
            fl["trunc"] = 1
            return done()
        if fr[l3] >> 4 != 6:
            fl["err_ver"] = 1
            return done()
        if need(l3 + 7):
            h["proto"] = fr[l3 + 6]
        if need(l3 + 8):
            h["ttl"] = fr[l3 + 7]
        h["src"] = _partial(fr, l3 + 8, 16)
        h["dst"] = _partial(fr, l3 + 24, 16)
        if not need(l3 + 40):
            fl["trunc"] = 1
            return done()
        if h["proto"] in (6, 17):
            return _l4(fr, l3 + 40, h, fl)
        return done()
    return done()


def _setv(fl, nv):
    fl["vlan_n0"] = nv & 1
    fl["vlan_n1"] = (nv >> 1) & 1


def _partial(fr, start, nbytes):
    """Big-endian value of fr[start:start+nbytes], bytes beyond the frame end read as zero (the RTL keeps zero)."""
    v = 0
    for i in range(nbytes):
        v = (v << 8) | (fr[start + i] if start + i < len(fr) else 0)
    return v


def _ipv4_partial(fr, l3, h, fl):
    if len(fr) > l3 + 8:
        h["ttl"] = fr[l3 + 8]
    if len(fr) > l3 + 9:
        h["proto"] = fr[l3 + 9]
    h["src"] = _partial(fr, l3 + 12, 4)
    h["dst"] = _partial(fr, l3 + 16, 4)
    if len(fr) > l3 + 7:
        off = ((fr[l3 + 6] & 0x1F) << 8) | fr[l3 + 7]
        mf = (fr[l3 + 6] >> 5) & 1
        fl["frag"] = int(mf or off != 0)


def _l4(fr, l4, h, fl):
    h["l4off"] = l4
    fl["udp" if h["proto"] == 17 else "tcp"] = 1
    h["sport"] = _partial(fr, l4, 2)
    h["dport"] = _partial(fr, l4 + 2, 2)
    if len(fr) < l4 + 4:
        fl["trunc"] = 1
    else:
        fl["l4"] = 1
    fl_val = sum(1 << i for i, k in enumerate(FLAG_BITS) if fl[k])
    h["flags"] = fl_val
    return h


def pack_hdr(h: dict) -> int:
    v = 0
    for k, w in HDR_FIELDS:
        v = (v << w) | (h[k] & ((1 << w) - 1))
    return v


def unpack_hdr(v: int) -> dict:
    h = {}
    for k, w in reversed(HDR_FIELDS):
        h[k] = v & ((1 << w) - 1)
        v >>= w
    return h


def flags(h: dict) -> dict:
    return {k: (h["flags"] >> i) & 1 for i, k in enumerate(FLAG_BITS)}


# ------------------------------------------------------------------------------------------------ match tables

def crc_key(key: int, width: int, poly: int) -> int:
    """CRC-32 of a KEY_W-bit key, MSB first, register from zero, no reflection, no final inversion (match_exact)."""
    r = 0
    for i in range(width - 1, -1, -1):
        fb = ((r >> 31) & 1) ^ ((key >> i) & 1)
        r = (r << 1) & 0xFFFFFFFF
        if fb:
            r ^= poly
    return r


CRC32_POLY, CRC32C_POLY = 0x04C11DB7, 0x1EDC6F41
OK, FULL, NOT_FOUND, BAD_OP = 0, 1, 2, 3


class ExactTable:
    """match_exact's placement and results: two one-entry-bucket banks (CRC-32, CRC-32C) and a stash."""

    def __init__(self, key_w: int, idx_w: int, stash: int):
        self.kw, self.iw, self.ns = key_w, idx_w, stash
        self.b = [[None] * (1 << idx_w), [None] * (1 << idx_w)]      # entries [key, act, used]
        self.s = [None] * stash
        self.stash_peak = 0                        # most stash entries ever in use (collision path exercised)

    def h(self, key):
        m = (1 << self.iw) - 1
        return crc_key(key, self.kw, CRC32_POLY) & m, crc_key(key, self.kw, CRC32C_POLY) & m

    def lookup(self, key):
        h0, h1 = self.h(key)
        for e in (self.b[0][h0], self.b[1][h1]):
            if e and e[0] == key:
                return True, e[1]
        for e in self.s:
            if e and e[0] == key:
                return True, e[1]
        return False, 0

    def insert(self, key, act) -> int:
        h0, h1 = self.h(key)
        for bank, i in ((0, h0), (1, h1)):
            e = self.b[bank][i]
            if e and e[0] == key:
                self.b[bank][i] = [key, act, 1]
                return OK
        for j, e in enumerate(self.s):
            if e and e[0] == key:
                self.s[j] = [key, act, 1]
                return OK
        for bank, i in ((0, h0), (1, h1)):
            if self.b[bank][i] is None:
                self.b[bank][i] = [key, act, 1]
                return OK
        for j, e in enumerate(self.s):
            if e is None:
                self.s[j] = [key, act, 1]
                self.stash_peak = max(self.stash_peak, sum(x is not None for x in self.s))
                return OK
        return FULL

    def delete(self, key) -> int:
        h0, h1 = self.h(key)
        for bank, i in ((0, h0), (1, h1)):
            e = self.b[bank][i]
            if e and e[0] == key:
                self.b[bank][i] = None
                return OK
        for j, e in enumerate(self.s):
            if e and e[0] == key:
                self.s[j] = None
                return OK
        return NOT_FOUND

    def age(self) -> int:
        for bank in self.b:
            for i, e in enumerate(bank):
                if e:
                    bank[i] = [e[0], e[1], 0] if e[2] else None
        for j, e in enumerate(self.s):
            if e:
                self.s[j] = [e[0], e[1], 0] if e[2] else None
        return OK

    def count(self):
        return sum(e is not None for bank in self.b for e in bank) + sum(e is not None for e in self.s)


def lpm_oracle(routes, addr: int):
    """Brute-force longest-prefix match: routes = [(prefix int, length, nh)]. Returns (hit, nh)."""
    best = None
    for p, ln, nh in routes:
        m = ((1 << ln) - 1) << (32 - ln) if ln else 0
        if (addr & m) == (p & m) and (best is None or ln > best[0]):
            best = (ln, nh)
    return (True, best[1]) if best else (False, 0)


def lpm_compile(routes, act_w: int, nodes=(64, 64, 64), alloc: dict | None = None):
    """Controlled prefix expansion into match_lpm's 8-8-8-8 trie. Returns ({(level, index): word} for every non-zero
    word, alloc). Word = {has_nh, nh, has_child, child[5:0]}. `alloc` maps (level, path) -> node index; pass the
    previous compile's alloc so that existing nodes keep their index and an added route changes only the words it
    must (node indices that move would break lookups in flight)."""
    cw = 6
    alloc = dict(alloc or {})
    used = [set(), set(), set(), set()]
    for (lvl, _), idx in alloc.items():
        used[lvl].add(idx)
    tables: dict = {(0, 0): [[-1, 0, None] for _ in range(256)]}

    def node_of(level, path):
        if level == 0:
            return 0
        key = (level, path)
        if key not in alloc:
            free = next((i for i in range(nodes[level - 1]) if i not in used[level]), None)
            if free is None:
                raise ValueError(f"level {level} full")
            alloc[key] = free
            used[level].add(free)
        idx = alloc[key]
        tables.setdefault((level, idx), [[-1, 0, None] for _ in range(256)])
        return idx

    for p, ln, nh in sorted(routes, key=lambda r: r[1]):
        for level in range(4):
            node = node_of(level, p >> (32 - 8 * level) if level else 0)
            byte = (p >> (24 - 8 * level)) & 0xFF
            lo, hi = 8 * level, 8 * level + 8
            if ln <= hi:
                loc = ln - lo                      # bits of this stride the prefix fixes (0..8)
                base = byte & ~((1 << (8 - loc)) - 1) & 0xFF
                for e in range(base, base + (1 << (8 - loc))):
                    ent = tables[(level, node)][e]
                    if ln >= ent[0]:
                        ent[0], ent[1] = ln, nh
                break
            child = node_of(level + 1, p >> (24 - 8 * level))
            tables[(level, node)][byte][2] = child
    words = {}
    for (level, ni), n in tables.items():
        for e, (bl, nh, ch) in enumerate(n):
            w = 0
            if bl >= 0:
                w |= (1 << (act_w + cw + 1)) | (nh << (cw + 1))
            if ch is not None:
                w |= (1 << cw) | ch
            if w:
                words[(level, ni * 256 + e)] = w
    return words, alloc


class TernaryTable:
    def __init__(self, entries: int):
        self.e = [None] * entries                  # (value, care, act)

    def write(self, i, value, care, act):
        self.e[i] = (value, care, act)

    def delete(self, i):
        self.e[i] = None

    def lookup(self, key):
        for v in self.e:
            if v and ((key ^ v[0]) & v[1]) == 0:
                return True, v[2]
        return False, 0


# ------------------------------------------------------------------------------------------------ rewrite

ACT_FIELDS = [("drop", 0, 1), ("port", 1, 4), ("queue", 5, 3), ("set_dmac", 8, 1), ("dmac", 9, 48),
              ("set_smac", 57, 1), ("smac", 58, 48), ("dec_ttl", 106, 1), ("set_vid", 107, 1), ("vid", 108, 12),
              ("push_vlan", 120, 1), ("pop_vlan", 121, 1), ("set_dip", 122, 1), ("dip", 123, 32)]
ACT_W = 160


def pack_act(**kw) -> int:
    v = 0
    for k, lo, w in ACT_FIELDS:
        v |= (kw.get(k, 0) & ((1 << w) - 1)) << lo
    return v


def unpack_act(v: int) -> dict:
    return {k: (v >> lo) & ((1 << w) - 1) for k, lo, w in ACT_FIELDS}


def oc_add(a: int, b: int) -> int:
    s = a + b
    return (s & 0xFFFF) + (s >> 16)


def rewrite(fr: bytes, hdr: dict, act: int):
    """pkt_rewrite's reference. Returns (out bytes or None when dropped, tdest, ttl_drop)."""
    a = unpack_act(act)
    f = flags(hdr)
    v4, v6 = f["ipv4"], f["ipv6"]
    badv4 = f["err_ihl"] or f["err_ver"]
    ttl_en = a["dec_ttl"] and ((v4 and not badv4) or (v6 and not f["err_ver"]))
    expire = ttl_en and hdr["ttl"] <= 1
    dest = (a["queue"] << 4) | a["port"]
    if a["drop"] or expire:
        return None, dest, bool(expire and not a["drop"])
    dip_en = a["set_dip"] and v4 and not badv4
    l4_en = dip_en and f["l4"]
    udp = f["udp"]
    l3, l4 = hdr["l3off"], hdr["l4off"]
    vn = f["vlan_n0"] | (f["vlan_n1"] << 1)
    b = bytearray(fr)
    n = len(b)

    def put(i, v):
        if i < n:
            b[i] = v

    if a["set_dmac"]:
        for i in range(6):
            put(i, (a["dmac"] >> (8 * (5 - i))) & 0xFF)
    if a["set_smac"]:
        for i in range(6):
            put(6 + i, (a["smac"] >> (8 * (5 - i))) & 0xFF)
    if a["set_vid"] and not a["push_vlan"]:
        if not a["pop_vlan"] and vn:
            put(14, (fr[14] & 0xF0) | (a["vid"] >> 8) if n > 14 else 0)
            put(15, a["vid"] & 0xFF)
        if a["pop_vlan"] and vn == 2:
            put(18, (fr[18] & 0xF0) | (a["vid"] >> 8) if n > 18 else 0)
            put(19, a["vid"] & 0xFF)
    ttl_d = dip_d = 0
    if ttl_en:
        put(l3 + (8 if v4 else 7), (hdr["ttl"] - 1) & 0xFF)
        if v4:
            ttl_d = oc_add(~((hdr["ttl"] << 8) | hdr["proto"]) & 0xFFFF, (((hdr["ttl"] - 1) & 0xFF) << 8) | hdr["proto"])
    if dip_en:
        for i in range(4):
            put(l3 + 16 + i, (a["dip"] >> (8 * (3 - i))) & 0xFF)
        od = hdr["dst"] & 0xFFFFFFFF
        dip_d = oc_add(oc_add(~(od >> 16) & 0xFFFF, a["dip"] >> 16), oc_add(~od & 0xFFFF, a["dip"] & 0xFFFF))
    if v4 and not badv4 and (ttl_en or dip_en) and l3 + 11 < n:
        old = (fr[l3 + 10] << 8) | fr[l3 + 11]
        new = ~oc_add(oc_add(~old & 0xFFFF, ttl_d), dip_d) & 0xFFFF
        b[l3 + 10], b[l3 + 11] = new >> 8, new & 0xFF
    if l4_en:
        c = l4 + (6 if udp else 16)
        if c + 1 < n:
            old = (fr[c] << 8) | fr[c + 1]
            t = ~oc_add(~old & 0xFFFF, dip_d) & 0xFFFF
            new = 0 if (udp and old == 0) else (0xFFFF if (udp and t == 0) else t)
            b[c], b[c + 1] = new >> 8, new & 0xFF
    out = bytes(b)
    if a["push_vlan"] and n > 12:
        vid = a["vid"] if a["set_vid"] else 0
        tag = bytes([0x81, 0x00, (vid >> 8) & 0xF, vid & 0xFF])
        rest = out[12:]
        if a["pop_vlan"] and vn:
            rest = rest[4:]
        out = out[:12] + tag + rest
    elif a["pop_vlan"] and vn:
        out = out[:12] + out[16:]
    return out, dest, False


def lpm_walk(words: dict, addr: int, act_w: int):
    """Walk a compiled trie as match_lpm does (for checking lpm_compile against lpm_oracle)."""
    cw = 6
    node, hit, nh = 0, False, 0
    for level in range(4):
        w = words.get((level, node * 256 + ((addr >> (24 - 8 * level)) & 0xFF)), 0)
        if (w >> (act_w + cw + 1)) & 1:
            hit, nh = True, (w >> (cw + 1)) & ((1 << act_w) - 1)
        if not (w >> cw) & 1:
            break
        node = w & ((1 << cw) - 1)
    return hit, nh


# ------------------------------------------------------------------------------------------------ queues

def schedule_order(queues, mode: int, quantum=None, start_cur=None):
    """pkt_queue_sched's departure order when every packet is queued before the first departure.
    queues: list (per queue) of packet lengths. Returns [(queue, index within queue)]. mode 0 RR, 1 SP, 2 DRR."""
    nq = len(queues)
    heads = [0] * nq
    out = []
    cur = nq - 1 if start_cur is None else start_cur
    visited, deficit = False, [0] * nq

    def ne(q):
        return heads[q] < len(queues[q])

    while any(ne(q) for q in range(nq)):
        if mode == 1:
            q = min(q for q in range(nq) if ne(q))
        elif mode == 0:
            q = next((cur + k) % nq for k in range(1, nq + 1) if ne((cur + k) % nq))
            cur = q
        else:
            while True:                            # DRR steps until a packet goes
                if not visited:
                    if ne(cur):
                        deficit[cur] += quantum[cur]
                        visited = True
                    else:
                        deficit[cur] = 0
                        cur = (cur + 1) % nq
                elif ne(cur) and queues[cur][heads[cur]] <= deficit[cur]:
                    deficit[cur] -= queues[cur][heads[cur]]
                    break
                else:
                    if not ne(cur):
                        deficit[cur] = 0
                    cur = (cur + 1) % nq
                    visited = False
            q = cur
        out.append((q, heads[q]))
        heads[q] += 1
    return out


# ------------------------------------------------------------------------------------------------ L2 switch

class L2Switch:
    """l2_switch's forwarding, frame by frame, in the order the core took the frames (and aged the table)."""

    def __init__(self, nports: int, pvid, vlans: dict, idx_w: int = 9, stash: int = 4):
        self.np, self.pvid, self.vlans = nports, list(pvid), dict(vlans)
        self.tab = ExactTable(60, idx_w, stash)
        self.out = [[] for _ in range(nports)]
        self.floods = self.filtered = 0

    @staticmethod
    def accepted(fr: bytes, user: int) -> bool:
        """Ingress keeps a frame unless tuser (bad FCS) is set or it is shorter than 14 bytes."""
        return not user and len(fr) >= 14

    def frame(self, port: int, fr: bytes):
        tagged = len(fr) >= 16 and fr[12:14] == b"\x81\x00"
        tvid = ((fr[14] << 8) | fr[15]) & 0xFFF if tagged else 0
        vid = tvid if tagged and tvid else self.pvid[port]
        member = self.vlans.get(vid, 0)
        dmac = int.from_bytes(fr[0:6], "big")
        smac = int.from_bytes(fr[6:12], "big")
        hit, act = self.tab.lookup((vid << 48) | dmac)
        if not (member >> port) & 1:
            m = 0
        elif (dmac >> 40) & 1 or not hit:
            m = member & ~(1 << port)
            self.floods += 1
        elif act == port:
            m = 0
            self.filtered += 1
        else:
            m = member & (1 << act)
        if not (smac >> 40) & 1 and (member >> port) & 1:
            self.tab.insert((vid << 48) | smac, port)
        for p in range(self.np):
            if (m >> p) & 1:
                self.out[p].append(fr)

    def age(self):
        self.tab.age()
