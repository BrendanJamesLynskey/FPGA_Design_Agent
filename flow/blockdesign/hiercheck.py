"""Does the viewer's graph match the synthesised design?

The graph (``gen/graph.json``) is what the viewer draws. This check compares it with what Vivado built, and takes
nothing about the design's structure from the graph itself: which cells must appear, and how they are wired, come from
the routed netlist (``annotate.tcl``) and from the generated RTL that the build used.

1. **Instances.** Every block of the graph (and, for a generated wrapper, its library block and its register bank or
   window adapter) must be a cell of the netlist at its RTL path (``u_tone/u_dds``) with the module the graph names
   (Vivado's ``ORIG_REF_NAME``, so a parameterised copy still matches). Every netlist cell directly inside the top or
   inside a *generated* module (the modules declared in ``gen/rtl/*.sv``, so the hierarchies and wrappers) must be in
   the graph: a hierarchy drawn as a plain block, or a wrapper left out, fails. Cells inside a library block (the
   shell's UART, for example) are that block's own business and are not compared.
2. **Links.** Every link the graph draws between two blocks must be a net between their cells in the netlist, in the
   direction drawn: for a bus, the master's ``AWVALID`` (``TVALID``, the window's ``win_wr``) is an output on the same
   net as the slave's input; for a signal link, each source bit is an output on the same net as its sink bit. And every
   net that joins two blocks' cells must be drawn as a link between them. Two kinds are not compared and are counted
   instead: a link through logic (an inverted signal goes through a LUT, so no single net joins the two cells), and a
   link whose pins synthesis removed (constant or unused). The reset synchroniser's fan-out is not drawn as links and
   is not compared.
3. **Address map.** The graph's base and size for each crossbar slave must equal the ``S_BASE`` and ``S_BITS`` the
   generated top gives the crossbar, in the RTL whose SHA-256 the build recorded.

What it does not check: links to the design's own ports, constants, parameters other than the crossbar's map, and
anything inside a library block.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

IGNORE = re.compile(r"^(dbg_hub|u_ila_\d+)")
VALID = {"axi4lite": "awvalid", "axi4": "awvalid", "axis": "tvalid"}


def _mod(m: str) -> str:
    return re.sub(r"__parameterized\d+$", "", m or "")


def modules_in(rtl_texts: list[str]) -> set:
    """The modules the generator wrote (``module <name>`` in gen/rtl/*.sv)."""
    out = set()
    for t in rtl_texts:
        out |= set(re.findall(r"^\s*module\s+(\w+)", t, re.M))
    return out


def _graph_instances(g: dict) -> dict:
    """RTL path -> module, for every instance the graph shows (blocks, and the inside of each wrapper it shows)."""
    exp = {}
    for lv in g["levels"].values():
        for b in lv["blocks"]:
            exp[b["rtl_path"]] = b["module"]
            if b.get("wrapper"):
                inner = b["wrapper"]["inner"]
                exp[inner[0]] = b["component_top"] if b.get("component_top") else b["component"]
                exp[inner[1]] = "bd_axil_win" if b["wrapper"]["kind"] == "window" else "bd_axil_regs"
    return exp


def check_instances(g: dict, hier: list[dict], gen_modules: set) -> dict:
    exp = _graph_instances(g)
    found = {h["path"]: _mod(h["module"]) for h in hier if not IGNORE.match(h["path"])}
    mism, matched = [], 0
    for p, m in sorted(exp.items()):
        if p not in found:
            mism.append(f"{p} ({m}) is in the diagram but not in the synthesised hierarchy")
        elif found[p] != m:
            mism.append(f"{p}: the diagram says {m}, the netlist has {found[p]}")
        else:
            matched += 1
    must = 0
    for p in sorted(found):
        parent = p.rsplit("/", 1)[0] if "/" in p else ""
        if parent == "" or found.get(parent) in gen_modules:          # decided by the netlist, not by the graph
            must += 1
            if p not in exp:
                why = "inside the generated module " + found[parent] if parent else "directly inside the top"
                mism.append(f"{p} ({found[p]}) is in the synthesised hierarchy, {why}, but not in the diagram")
    return {"matched": matched, "expected": len(exp), "netlist_required": must, "mismatches": mism}


# ------------------------------------------------------------------------------------------------------------ links
def _pin_index(pins: list[dict]) -> tuple[dict, dict]:
    """(cell, pin name) -> (dir, net); and net -> [(cell, pin name, dir)]."""
    by_pin, by_net = {}, {}
    for r in pins:
        cell, pn = r["pin"].rsplit("/", 1)
        by_pin[(cell, pn)] = (r["dir"], r["net"])
        by_net.setdefault(r["net"], []).append((cell, pn, r["dir"]))
    return by_pin, by_net


def _bit_pin(by_pin: dict, cell: str, port: str, bit: int) -> str | None:
    if (cell, f"{port}[{bit}]") in by_pin:
        return f"{port}[{bit}]"
    if bit == 0 and (cell, port) in by_pin:
        return port
    return None


def _bus_pin(found: dict, block: dict, ifn: str, kind: str) -> str:
    if found.get(block["rtl_path"]) == "axil_xbar":                     # the crossbar's ports are vectors, one bit a port
        return f"{'m' if ifn.startswith('m') else 's'}_axil_{VALID['axi4lite']}[{int(ifn[1:])}]"
    if kind == "window":
        return "win_wr"
    return f"{ifn}_{VALID.get(kind, 'awvalid')}"


def check_links(g: dict, hier: list[dict], pins: list[dict]) -> dict:
    found = {h["path"]: _mod(h["module"]) for h in hier}
    by_pin, by_net = _pin_index(pins)
    blocks = {b["id"]: b for lv in g["levels"].values() for b in lv["blocks"]}
    cell_of = {b["id"]: b["rtl_path"] for b in blocks.values()}
    mism, matched, expected, unseen = [], 0, 0, []
    drawn = set()                                     # unordered cell pairs the graph joins
    for key, lv in g["levels"].items():
        for L in lv["links"]:
            if L["from"] not in blocks or L["to"] not in blocks:
                continue                              # a link to the design's ports or a constant: not compared
            a, b = cell_of[L["from"]], cell_of[L["to"]]
            drawn.add(frozenset((a, b)))
            expected += 1
            name = f"{L['from']} -> {L['to']} ({L.get('label') or L['kind']})"
            if L["kind"] in ("axi4lite", "axi4", "axis", "window"):
                pa = _bus_pin(found, blocks[L["from"]], L["from_if"], L["kind"])
                pb = _bus_pin(found, blocks[L["to"]], L["to_if"], L["kind"])
                ra, rb = by_pin.get((a, pa)), by_pin.get((b, pb))
                if ra is None or rb is None:
                    unseen.append(f"{name}: {a}/{pa} or {b}/{pb} is not in the netlist")
                elif ra[1] == rb[1] and ra[0] == "OUT" and rb[0] == "IN":
                    matched += 1
                else:
                    mism.append(f"{name}: the diagram has {L['from']} as the master, but in the netlist {a}/{pa} ({ra[0]}) "
                                f"and {b}/{pb} ({rb[0]}) are " + ("not on one net" if ra[1] != rb[1] else "the other way round"))
                continue
            pairs, through = [], False
            for s in L.get("signals") or []:
                if s.get("invert"):
                    through = True
                    continue
                slo = (s.get("bits") or [0, 0])[1]
                dlo = (s.get("to_bits") or [0, 0])[1]
                for i in range(s["width"]):
                    pa, pb = _bit_pin(by_pin, a, s["from"], slo + i), _bit_pin(by_pin, b, s["to"], dlo + i)
                    if pa and pb:
                        pairs.append((by_pin[(a, pa)], by_pin[(b, pb)], f"{a}/{pa}", f"{b}/{pb}"))
            good = [p for p in pairs if p[0][1] == p[1][1] and p[0][0] == "OUT" and p[1][0] == "IN"]
            if good:
                matched += 1
            elif pairs:
                ra, rb, na, nb = pairs[0]
                mism.append(f"{name}: no source bit drives its sink on one net (for example {na} is {ra[0]}, {nb} is {rb[0]}"
                            + (", on different nets" if ra[1] != rb[1] else "") + ")")
            else:
                unseen.append(f"{name}: " + ("through logic (inverted), not a direct net" if through
                                              else "its pins were removed by synthesis (constant or unused)"))
    # every net between two blocks' cells must be drawn
    block_cells = set(cell_of.values())
    undrawn = set()
    for net, ends in by_net.items():
        drivers = [c for (c, pn, d) in ends if d == "OUT" and c in block_cells and found.get(c) != "reset_sync"]
        loads = [c for (c, pn, d) in ends if d == "IN" and c in block_cells]
        for x in drivers:
            for y in loads:
                if x != y and frozenset((x, y)) not in drawn:
                    undrawn.add((x, y))
    for x, y in sorted(undrawn):
        mism.append(f"{x} drives {y} in the netlist, but the diagram draws no link between them")
    return {"edges_matched": matched, "edges_expected": expected, "edges_not_visible": unseen, "mismatches": mism}


# ------------------------------------------------------------------------------------------------------- address map
def _field(text: str, name: str, inst: str) -> int | None:
    m = re.search(rf"\.{name}\((\d+)'h([0-9a-fA-F_]+)\)[^;]*?\)\s*{re.escape(inst)}\s*\(", text, re.S)
    return int(m.group(2).replace("_", ""), 16) if m else None


def check_addrmap(g: dict, top_rtl: str) -> dict:
    mism, checked = [], 0
    for lv in g["levels"].values():
        for b in lv["blocks"]:
            if not b.get("slaves"):
                continue
            inst = b["rtl_path"].rsplit("/", 1)[-1]
            hdr = re.search(rf"axil_xbar\s*#\((.*?)\)\s*{re.escape(inst)}\s*\(", top_rtl, re.S)
            if hdr is None:
                mism.append(f"{b['rtl_path']}: no axil_xbar instance {inst} in the generated top")
                continue
            ps = dict(re.findall(r"\.(\w+)\(([^()]*)\)", hdr.group(1)))
            aw = int(ps["ADDR_W"])
            sbase = int(ps["S_BASE"].split("'h")[1].replace("_", ""), 16)
            sbits = int(ps["S_BITS"].split("'h")[1].replace("_", ""), 16)
            ranges = {r["slave"]: r for r in g["address_map"]["ranges"] if r.get("xbar") in (None, b["id"].rsplit("/", 1)[-1])}
            for i, s in enumerate(b["slaves"]):
                r = ranges.get(s)
                base = (sbase >> (i * aw)) & ((1 << aw) - 1)
                size = 1 << ((sbits >> (i * 8)) & 0xFF)
                checked += 1
                if r is None:
                    mism.append(f"{b['id']} slave {i} ({s}): no range in the diagram's address map")
                elif (r["base"], r["size"]) != (base, size):
                    mism.append(f"{b['id']} slave {i} ({s}): the diagram says 0x{r['base']:08X}, {r['size']} bytes; the built RTL "
                                f"decodes 0x{base:08X}, {size} bytes")
    return {"ranges_checked": checked, "mismatches": mism}


# ------------------------------------------------------------------------------------------------------------- all
def check(g: dict, hier: list[dict], gen_modules: set, pins: list[dict] | None = None, top_rtl: str | None = None) -> dict:
    """The full check. ``gen_modules``: the modules of the generated RTL that was built; ``pins``: annotate.tcl's
    connectivity (absent in records made before it was added: then links are not compared, and the result says so);
    ``top_rtl``: the generated top that was built (for the address map)."""
    a = check_instances(g, hier, gen_modules)
    out = {"matched": a["matched"], "expected": a["expected"], "netlist_required": a["netlist_required"],
           "mismatches": list(a["mismatches"])}
    if pins is not None:
        e = check_links(g, hier, pins)
        out.update({k: e[k] for k in ("edges_matched", "edges_expected", "edges_not_visible")})
        out["mismatches"] += e["mismatches"]
    if top_rtl is not None:
        m = check_addrmap(g, top_rtl)
        out["ranges_checked"] = m["ranges_checked"]
        out["mismatches"] += m["mismatches"]
    out["pass"] = not out["mismatches"]
    return out


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def built_rtl(ddir: Path, record: dict) -> tuple[dict, list[str]]:
    """The generated RTL files the build used: {name: text}, and a mismatch per file changed since the build."""
    gen = Path(ddir) / "gen" / "rtl"
    files = {p.name: p.read_text() for p in sorted(gen.glob("*.sv"))}
    want = record.get("rtl_sha256") or {}
    bad = [f"gen/rtl/{n} changed since the build (SHA-256 differs from the build record)" for n, t in files.items()
           if n in want and want[n] != sha256(t)]
    bad += [f"gen/rtl/{n} was built but no longer exists" for n in want if n not in files]
    return files, bad


def check_record(ddir: Path, g: dict, record: dict) -> dict:
    """Check a graph against a build record (results/blockdesign/<name>/build.json, or annotate.tcl's raw JSON plus the
    record's ``rtl_sha256``)."""
    files, bad = built_rtl(ddir, record)
    top = files.get(f"{g['top']}.sv")
    res = check(g, record["hier"], modules_in(list(files.values())), record.get("pins"), top)
    res["mismatches"] = bad + res["mismatches"]
    res["pass"] = not res["mismatches"]
    return res


def check_files(ddir: Path, record: Path) -> dict:
    g = json.loads((Path(ddir) / "gen" / "graph.json").read_text())
    r = json.loads(Path(record).read_text())
    return check_record(ddir, g, r if isinstance(r, dict) else {"hier": r})
