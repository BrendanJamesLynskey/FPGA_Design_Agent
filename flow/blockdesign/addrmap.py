"""The address editor: assign every interconnect slave a range, check the map, and export it.

Ranges are powers of two, aligned to their size (the crossbar decodes base and size that way). A range given with a
``base`` keeps it; the others are placed, in the order listed, at the lowest free aligned address from the map's
``base``. A slave on an interconnect but not listed is placed after the listed ones. The size is the larger of the
map's ``min_size`` (4 KB by default, as IP Integrator uses) and the slave's own address span.

Checks: overlaps (error BD-ADDR-01), holes between ranges (warning BD-ADDR-02: an access there gets DECERR from the
crossbar), a base not aligned to its size (BD-ADDR-03), a range outside the masters' address space (BD-ADDR-04), a
range for a slave that is on no interconnect (BD-ADDR-05), a size that is not a power of two or smaller than 4 bytes
(BD-ADDR-06), and a range smaller than the slave decodes (warning BD-ADDR-07: its top registers cannot be reached).

Exports: a C header and a Markdown page with every range and the generated register banks' offsets, and a JSON file
that tests and host scripts read.
"""
from __future__ import annotations

import json
import re


def _pow2(n: int) -> bool:
    return n > 0 and n & (n - 1) == 0


def assign(E) -> None:
    from flow.blockdesign.model import Range
    spec = E.data.get("address_map") or {}
    base0 = spec.get("base", 0)
    min_size = spec.get("min_size", 4096)
    if not _pow2(min_size):
        E.err("BD-ADDR-06", "address_map/min_size", f"min_size {min_size:#x} is not a power of two")
        min_size = 4096
    # slaves on interconnects, in order
    on_xbar = {}
    for L in E.links:
        if L.xbar and L.master[0] == L.xbar:
            on_xbar[f"{L.slave[0]}.{L.slave[1]}"] = L
    if not on_xbar and not spec.get("ranges"):
        return
    aw = {L.xbar: E.boxes[L.xbar].params["ADDR_W"] for L in on_xbar.values()}
    listed = []
    for i, r in enumerate(spec.get("ranges") or []):
        w = f"address_map/ranges/{i}"
        if r["slave"] not in on_xbar:
            E.err("BD-ADDR-05", w, f"{r['slave']} is not a slave on any interconnect",
                  "slaves on interconnects: " + (", ".join(on_xbar) or "none"))
            continue
        if r["slave"] in [x[0]["slave"] for x in listed]:
            E.err("BD-ADDR-01", w, f"{r['slave']} has two ranges")
            continue
        listed.append((r, w))
    for s in on_xbar:
        if s not in [x[0]["slave"] for x in listed]:
            listed.append(({"slave": s}, f"address_map (auto: {s})"))
    fixed, auto = [], []
    for r, w in listed:
        L = on_xbar[r["slave"]]
        sb = E.boxes[L.slave[0]].ifaces[L.slave[1]]
        span = 1 << sb.addr_w
        size = r.get("size", max(min_size, span))
        if not _pow2(size) or size < 4:
            E.err("BD-ADDR-06", w, f"size {size:#x} of {r['slave']} is not a power of two of at least 4 bytes")
            continue
        if size < span:
            E.warn("BD-ADDR-07", w, f"{r['slave']} decodes {span:#x} bytes but its range is {size:#x}: the rest cannot be reached")
        rg = Range(r["slave"], L.slave[0], L.slave[1], r.get("base", -1), size, "base" in r, L.xbar, L.index)
        (fixed if "base" in r else auto).append((rg, w))
    taken = []
    for rg, w in fixed:
        if rg.base % rg.size:
            E.err("BD-ADDR-03", w, f"{rg.slave} base {rg.base:#x} is not a multiple of its size {rg.size:#x}",
                  f"use {rg.base // rg.size * rg.size:#x} or {(rg.base // rg.size + 1) * rg.size:#x}")
        for other in taken:
            if rg.base < other.base + other.size and other.base < rg.base + rg.size:
                E.err("BD-ADDR-01", w, f"{rg.slave} [{rg.base:#x}, {rg.base + rg.size - 1:#x}] overlaps {other.slave} "
                      f"[{other.base:#x}, {other.base + other.size - 1:#x}]")
        taken.append(rg)
    for rg, w in auto:
        a = (base0 + rg.size - 1) // rg.size * rg.size
        while any(a < o.base + o.size and o.base < a + rg.size for o in taken):
            a += rg.size
        rg.base = a
        taken.append(rg)
    for rg, w in fixed + auto:
        lim = 1 << aw[rg.xbar]
        if rg.base + rg.size > lim:
            E.err("BD-ADDR-04", w, f"{rg.slave} [{rg.base:#x}, {rg.base + rg.size - 1:#x}] is outside the {aw[rg.xbar]}-bit address space")
    E.ranges = sorted(taken, key=lambda r: (r.xbar, r.base))
    # holes: gaps between ranges on the same interconnect, within the span they cover
    for xb in sorted({r.xbar for r in E.ranges}):
        rs = [r for r in E.ranges if r.xbar == xb]
        for a, b in zip(rs, rs[1:]):
            end = a.base + a.size
            if b.base > end:
                E.holes.append({"xbar": xb, "base": end, "size": b.base - end})
                E.warn("BD-ADDR-02", f"address_map ({xb})", f"hole [{end:#x}, {b.base - 1:#x}] between {a.slave} and {b.slave}: "
                       "an access there gets DECERR from the crossbar")


# ------------------------------------------------------------------------------------------------------------ exports
def _macro(*parts: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", "_".join(parts).upper()).strip("_")


def register_banks(E) -> dict:
    """slave endpoint -> list of registers (name, offset, access, reset, doc), for the generated register wrappers."""
    out = {}

    def walk(el, prefix, exported):
        for b in el.boxes.values():
            if b.sub is not None:
                exp = {ifn: f"{prefix}{b.name}.{ifn}" for ifn in b.sub.exports}
                walk(b.sub, f"{prefix}{b.name}/", {f"{inst}.{ifc}": exp[ifn] for ifn, (inst, ifc) in b.sub.exports.items()})
            elif b.wrap and b.kind == "wrapped":
                key = exported.get(f"{b.name}.s_axil", f"{prefix}{b.name}.s_axil")
                if b.wrap["kind"] == "registers":
                    regs = []
                    for i, r in enumerate(b.wrap["control"]):
                        regs.append({"name": r["name"], "offset": 4 * i, "access": "RW", "reset": r["reset"], "doc": r["doc"],
                                     "fields": r["fields"]})
                    n = len(b.wrap["control"])
                    for i, r in enumerate(b.wrap["status"]):
                        regs.append({"name": r["name"], "offset": 4 * (n + i), "access": "RO", "reset": None, "doc": r["doc"],
                                     "fields": r["fields"]})
                    out[key] = regs
                else:
                    out[key] = [{"name": "WINDOW", "offset": 0, "access": "RW", "reset": None, "fields": [], "words": 128,
                                 "doc": f"the {b.comp.name} register window: word w (0 to 127) at offset 4 x w, 0x000 to 0x1FC "
                                        f"(see ip_lib/{b.comp.name}); 0x200 to the end of the range answer SLVERR"}]
    walk(E, "", {})
    return out


def as_json(E) -> dict:
    banks = register_banks(E)
    return {"design": E.name, "ranges": [{"slave": r.slave, "base": r.base, "size": r.size, "fixed": r.fixed, "xbar": r.xbar,
                                           "registers": banks.get(r.slave, [])} for r in E.ranges],
            "holes": E.holes}


def c_header(E) -> str:
    m = as_json(E)
    g = _macro(E.name, "ADDRMAP_H")
    L = [f"/* {E.name} address map. Generated by flow/blockdesign from {E.path.name}; do not edit. */",
         f"#ifndef {g}", f"#define {g}", "", "#include <stdint.h>", ""]
    for r in m["ranges"]:
        p = _macro(E.name, r["slave"])
        L += [f"#define {p}_BASE 0x{r['base']:08X}u", f"#define {p}_SIZE 0x{r['size']:08X}u"]
        for g2 in r["registers"]:
            if g2["name"] == "WINDOW":
                L += [f"#define {p}_WINDOW_OFFSET 0x000u   /* RW: word w at WINDOW_OFFSET + 4 x w */",
                      f"#define {p}_WINDOW_WORDS {g2['words']}u   /* offsets 0x{4 * g2['words']:03X} and above answer SLVERR */"]
                continue
            L.append(f"#define {p}_{g2['name']}_OFFSET 0x{g2['offset']:03X}u   /* {g2['access']}: {g2['doc']} */")
        L.append("")
    L += ["#define " + _macro(E.name, "REG") + "(base, off) (*(volatile uint32_t *)((uintptr_t)(base) + (off)))", "",
          f"#endif /* {g} */", ""]
    return "\n".join(L)


def markdown(E) -> str:
    m = as_json(E)
    L = [f"# {E.name}: address map", "", f"Generated by `flow/blockdesign` from `{E.path.name}`; do not edit.", "",
         "| Slave | Base | Last address | Size | Placed |", "|---|---|---|---|---|"]
    for r in m["ranges"]:
        L.append(f"| `{r['slave']}` | `0x{r['base']:08X}` | `0x{r['base'] + r['size'] - 1:08X}` | {r['size'] // 1024} KB | "
                 f"{'fixed in the design' if r['fixed'] else 'by the address editor'} |")
    if m["holes"]:
        L += ["", "Holes (an access gets DECERR from the crossbar): " +
              "; ".join(f"`0x{h['base']:08X}`-`0x{h['base'] + h['size'] - 1:08X}`" for h in m["holes"]) + "."]
    for r in m["ranges"]:
        if not r["registers"]:
            continue
        L += ["", f"## `{r['slave']}`", "", "| Offset | Name | Access | Reset | What |", "|---|---|---|---|---|"]
        for g in r["registers"]:
            rst = "" if g["reset"] is None else f"`0x{g['reset']:08X}`"
            L.append(f"| `0x{g['offset']:03X}` | {g['name']} | {g['access']} | {rst} | {g['doc']} |")
    return "\n".join(L) + "\n"


def write_json(E) -> str:
    return json.dumps(as_json(E), indent=1) + "\n"
