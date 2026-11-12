#!/usr/bin/env python3
"""Read a 7-series .bit file as data, and compare two of them field by field (brief 54).

    python3 flow/bitstream.py info <file.bit>                 header fields, USR_ACCESS, packet summary (JSON)
    python3 flow/bitstream.py diff <a.bit> <b.bit> [--json f] every difference, named: header field, register write, frame word

A .bit file is a short header of tagged fields followed by the configuration packets (AMD UG470, "Configuration
Packets"; XAPP1232 appendix B for the USR_ACCESS write):

- header: a 13-byte preamble, then fields ``a`` (design name, ``UserID=``, ``Version=``), ``b`` (part), ``c`` (date),
  ``d`` (time) as 2-byte length + NUL-terminated text, and ``e`` (4-byte length of the configuration data);
- configuration data: padding, the bus-width pattern, the sync word ``AA995566``, then Type 1 packets (a 5-bit register
  address and a word count) and Type 2 packets (a long word count for the previous register, used for frame data).

The register writes are listed in order with their data. The USR_ACCESS value is the data of the write to AXSS
(register 01101). The CRC register writes are checked by recomputing the configuration CRC (the CRC-32C polynomial over
each register write's 5-bit address and 32-bit data, reset by the RCRC command), so a CRC word that differs between two
files is explained only if the recomputed CRC matches the file's in both.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any

SYNC = 0xAA995566
REGS = {0x00: "CRC", 0x01: "FAR", 0x02: "FDRI", 0x03: "FDRO", 0x04: "CMD", 0x05: "CTL0", 0x06: "MASK", 0x07: "STAT",
        0x08: "LOUT", 0x09: "COR0", 0x0A: "MFWR", 0x0B: "CBC", 0x0C: "IDCODE", 0x0D: "AXSS", 0x0E: "COR1",
        0x10: "WBSTAR", 0x11: "TIMER", 0x13: "RBCRC_SW", 0x16: "BOOTSTS", 0x18: "CTL1", 0x1F: "BSPI"}
CMDS = {0x00: "NULL", 0x01: "WCFG", 0x02: "MFW", 0x03: "LFRM", 0x04: "RCFG", 0x05: "START", 0x06: "RCAP", 0x07: "RCRC",
        0x08: "AGHIGH", 0x09: "SWITCH", 0x0A: "GRESTORE", 0x0B: "SHUTDOWN", 0x0C: "GCAPTURE", 0x0D: "DESYNC",
        0x0F: "IPROG", 0x10: "CRCC", 0x11: "LTIMER", 0x12: "BSPI_READ", 0x13: "FALL_EDGE"}
AXSS, CRC, CMD, FDRI = 0x0D, 0x00, 0x04, 0x02
FRAME_WORDS = 101          # 7-series frame length in 32-bit words (UG470, "Frame Address Register")
_POLY = 0x82F63B78         # CRC-32C (Castagnoli), bit-reversed form


class BitError(ValueError):
    pass


def crc_step(crc: int, addr: int, data: int) -> int:
    """One register write folded into the configuration CRC: 37 bits (data, then the 5-bit address), LSB first."""
    val = (addr & 0x1F) << 32 | (data & 0xFFFFFFFF)
    for _ in range(37):
        if (val ^ crc) & 1:
            crc = (crc >> 1) ^ _POLY
        else:
            crc >>= 1
        val >>= 1
    return crc


def parse_header(raw: bytes) -> tuple[dict[str, Any], int]:
    """The .bit header fields and the offset of the configuration data."""
    if len(raw) < 13 or raw[:2] != b"\x00\x09":
        raise BitError("not a .bit file (no 00 09 preamble)")
    pos = 2 + 9
    (n,) = struct.unpack(">H", raw[pos:pos + 2])
    pos += 2
    fields: dict[str, Any] = {}
    while pos < len(raw):
        key = chr(raw[pos])
        pos += 1
        if key == "e":
            (length,) = struct.unpack(">I", raw[pos:pos + 4])
            pos += 4
            fields["e"] = length
            if pos + length != len(raw):
                raise BitError(f"header says {length} bytes of configuration data, the file has {len(raw) - pos}")
            return fields, pos
        if key not in "abcd":
            raise BitError(f"unexpected header field {key!r} at byte {pos - 1}")
        (length,) = struct.unpack(">H", raw[pos:pos + 2])
        pos += 2
        fields[key] = raw[pos:pos + length].rstrip(b"\x00").decode("ascii", "replace")
        fields[f"{key}_offset"] = pos
        pos += length
    raise BitError("header has no 'e' field")


def parse_packets(data: bytes, base: int) -> dict[str, Any]:
    """Register writes in order. ``base`` is the file offset of ``data`` (for byte positions in the report)."""
    if len(data) % 4:
        raise BitError("configuration data is not a whole number of 32-bit words")
    words = struct.unpack(f">{len(data) // 4}I", data)
    try:
        i = words.index(SYNC) + 1
    except ValueError:
        raise BitError("no sync word AA995566") from None
    writes: list[dict[str, Any]] = []
    last_reg = None
    crc = 0
    crc_checks: list[dict[str, Any]] = []
    while i < len(words):
        h = words[i]
        typ = h >> 29
        op = (h >> 27) & 0x3
        if typ == 1:
            reg = (h >> 13) & 0x1F
            count = h & 0x7FF
        elif typ == 2:
            if last_reg is None:
                raise BitError(f"Type 2 packet at word {i} with no register")
            reg = last_reg
            count = h & 0x7FFFFFF
        else:
            raise BitError(f"unknown packet type {typ} at word {i} (0x{h:08X})")
        start = i + 1
        payload = words[start:start + count]
        if len(payload) != count:
            raise BitError(f"packet at word {i} runs past the end of the file")
        if op == 2 and count:            # write
            w: dict[str, Any] = {"reg": REGS.get(reg, f"R{reg:02X}"), "addr": reg, "words": count,
                                 "header_byte": base + 4 * i, "data_byte": base + 4 * start}
            if reg == FDRI:
                w["sha256"] = hashlib.sha256(struct.pack(f">{count}I", *payload)).hexdigest()
                w["_data"] = payload
            else:
                w["data"] = [f"{x:08X}" for x in payload]
                if reg == CMD:
                    w["cmd"] = [CMDS.get(x, f"0x{x:X}") for x in payload]
            if reg == CRC:
                crc_checks.append({"index": len(writes), "expected": f"{crc:08X}", "in_file": f"{payload[0]:08X}",
                                   "match": crc == payload[0]})
                crc = 0                   # a CRC check resets the running CRC
            else:
                for x in payload:
                    crc = crc_step(crc, reg, x)
                if reg == CMD and any(x == 0x07 for x in payload):
                    crc = 0               # RCRC
            writes.append(w)
        if typ == 1 or typ == 2:
            last_reg = reg if typ == 1 else last_reg
        i = start + count
    return {"writes": writes, "crc_checks": crc_checks}


def read(path: Path) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    hdr, off = parse_header(raw)
    pk = parse_packets(raw[off:], off)
    ua = [w for w in pk["writes"] if w["addr"] == AXSS]
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "header": hdr,
            "config_offset": off, "writes": pk["writes"], "crc_checks": pk["crc_checks"],
            "usr_access": ua[-1]["data"][0] if ua else None}


def usr_access(path: Path) -> str | None:
    """The USR_ACCESS value (8 hex digits, upper case) a bitstream writes, or None if it writes none."""
    return read(path)["usr_access"]


def info(path: Path) -> dict[str, Any]:
    b = read(path)
    fd = [w for w in b["writes"] if w["addr"] == FDRI]
    return {"path": b["path"], "bytes": b["bytes"], "sha256": b["sha256"],
            "header": {k: v for k, v in b["header"].items() if not k.endswith("_offset")},
            "usr_access": b["usr_access"], "register_writes": len(b["writes"]),
            "fdri_writes": [{"words": w["words"], "sha256": w["sha256"]} for w in fd],
            "crc_checks": b["crc_checks"], "crc_all_match": all(c["match"] for c in b["crc_checks"])}


def _frame_diff(a: tuple, b: tuple) -> dict[str, Any]:
    idx = [k for k in range(min(len(a), len(b))) if a[k] != b[k]]
    frames = sorted({k // FRAME_WORDS for k in idx})
    return {"words_a": len(a), "words_b": len(b), "words_differ": len(idx) + abs(len(a) - len(b)),
            "first_words": idx[:20], "frames_touched": len(frames), "first_frames": frames[:20]}


def diff(pa: Path, pb: Path) -> dict[str, Any]:
    """Every difference between two .bit files, by what it is. ``identical`` when the files are byte-identical."""
    ra, rb = Path(pa).read_bytes(), Path(pb).read_bytes()
    out: dict[str, Any] = {"a": str(pa), "b": str(pb), "identical": ra == rb,
                           "sha256_a": hashlib.sha256(ra).hexdigest(), "sha256_b": hashlib.sha256(rb).hexdigest()}
    a, b = read(pa), read(pb)
    hdr = []
    for k in "abcde":
        va, vb = a["header"].get(k), b["header"].get(k)
        if va != vb:
            hdr.append({"field": k, "a": va, "b": vb})
    out["header"] = hdr
    regs = []
    sa = [(w["reg"], w["words"]) for w in a["writes"]]
    sb = [(w["reg"], w["words"]) for w in b["writes"]]
    out["same_packet_sequence"] = sa == sb
    if sa == sb:
        for n, (wa, wb) in enumerate(zip(a["writes"], b["writes"])):
            if wa["addr"] == FDRI:
                if wa["sha256"] != wb["sha256"]:
                    regs.append({"index": n, "reg": "FDRI", "data_byte_a": wa["data_byte"],
                                 **_frame_diff(wa["_data"], wb["_data"])})
            elif wa["data"] != wb["data"]:
                words = [k for k in range(len(wa["data"])) if wa["data"][k] != wb["data"][k]]
                regs.append({"index": n, "reg": wa["reg"], "a": wa["data"], "b": wb["data"],
                             "bytes_a": [wa["data_byte"] + 4 * k for k in words]})
    out["register_writes"] = regs
    out["crc_recomputed_match"] = {"a": all(c["match"] for c in a["crc_checks"]),
                                   "b": all(c["match"] for c in b["crc_checks"])}
    # byte offsets that differ (same length only), grouped into the named places above
    if len(ra) == len(rb):
        offs = [k for k in range(len(ra)) if ra[k] != rb[k]]
        out["bytes_differ"] = len(offs)
        out["byte_ranges"] = _ranges(offs)[:50]
    else:
        out["bytes_differ"] = None
        out["length_a"], out["length_b"] = len(ra), len(rb)
    explained = _explain(out, a, b)
    out["explained"] = explained
    return out


def _ranges(offs: list[int]) -> list[list[int]]:
    r: list[list[int]] = []
    for o in offs:
        if r and o == r[-1][1] + 1:
            r[-1][1] = o
        else:
            r.append([o, o])
    return r


def _explain(d: dict[str, Any], a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Classify each difference: the date and time header fields (when write_bitstream ran), the USR_ACCESS word
    (the build ID), the CRC words (explained only when the recomputed CRC matches in both files), anything else."""
    kinds = []
    for h in d["header"]:
        kinds.append({"c": "header-date", "d": "header-time"}.get(h["field"], f"header-{h['field']}"))
    for r in d["register_writes"]:
        if r["reg"] == "AXSS":
            kinds.append("usr-access")
        elif r["reg"] == "CRC":
            kinds.append("crc" if d["crc_recomputed_match"]["a"] and d["crc_recomputed_match"]["b"] else "crc-unverified")
        else:
            kinds.append(f"register-{r['reg']}")
    ok = {"header-date", "header-time", "usr-access", "crc"}
    return {"kinds": sorted(set(kinds)), "only_documented": d["same_packet_sequence"] and set(kinds) <= ok,
            "configuration_identical_except_usr_access": d["same_packet_sequence"]
            and set(kinds) <= ok}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("info")
    s.add_argument("bit", type=Path)
    s = sub.add_parser("diff")
    s.add_argument("a", type=Path)
    s.add_argument("b", type=Path)
    s.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    try:
        r = info(a.bit) if a.cmd == "info" else diff(a.a, a.b)
    except (OSError, BitError) as e:
        print(f"bitstream.py: {e}", file=sys.stderr)
        return 2
    text = json.dumps(r, indent=1)
    if a.cmd == "diff" and a.json:
        a.json.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
