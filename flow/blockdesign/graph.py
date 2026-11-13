"""The viewer's graph: the elaborated block design as plain data (``gen/graph.json``).

One ``level`` per design level (the top, and one per hierarchy instance, keyed by its path). Each block carries what a
click on it shows: component, ip_lib variant, every parameter with where its value came from, its ports and
interfaces, the predicted and measured cost of its variant (``flow/ipvariants``) and, after a build, its share of the
utilisation, its worst slack and its power (``annotate.py``). Links carry the bus type and widths; crossings name the
synchroniser that makes them safe.

``rtl_path`` is the instance path in the generated RTL (``u_tone/u_dds``): ``hiercheck.py`` looks for each one in the
synthesised hierarchy.
"""
from __future__ import annotations

from flow.blockdesign import addrmap, model as M

KIND_LABEL = {"axi4lite": "AXI4-Lite", "axi4": "AXI4", "axis": "AXI4-Stream", "window": "register window",
              "conduit": "signal", "interrupt": "interrupt"}


def _cost(b: M.Box, part: str) -> dict | None:
    c = b.comp
    if c is None or c.source != "ip_lib":
        return None
    out = {"note": "", "variant": b.variant, "predicted": None, "measured": None}
    if c.variants:
        from flow import ipvariants
        params = {k: v for k, v in b.params.items() if k != c.variant_param and isinstance(v, int)}
        rows = ipvariants.variant_costs(c.name, params, part)
        row = next((r for r in rows if r["variant"] == b.variant), None)
        if row:
            out["predicted"] = row["predicted"]["uses"] if row["predicted"] else None
            m = row["measured"]
            if m:
                out["measured"] = {k: m.get(k) for k in ("lut", "ff", "lutram", "bram_tiles", "dsp", "wns_ns", "fmax_mhz", "clock_ns", "exact")}
                out["measured"]["power_w"] = (m.get("power_w") or {}).get("total")
                out["measured"]["tool"] = m.get("tool")
            out["alternatives"] = [{"variant": r["variant"], "summary": r["summary"], "valid": r["valid"],
                                    "cost": {k: v for k, v in r["cost"].items()}} for r in rows]
        out["note"] = ("measured out of context at this parameter point" if out["measured"] and out["measured"]["exact"]
                       else "measured out of context at the nearest characterised point" if out["measured"] else "not characterised")
    else:
        import yaml
        y = yaml.safe_load((M.C.IP / c.name / "ip.yaml").read_text())
        out["note"] = " ".join(str(y.get("cost_table", "not measured")).split())
    return out


def _shown(E: M.Elab, name: str, v, origin: str):
    """How a parameter value is written for the reader: hex stays hex when the design file gives it as hex, and the
    packed values the address editor makes are shown in hex too. ``None`` means the plain value is fine."""
    import re
    if isinstance(v, bool) or not isinstance(v, int):
        return None
    if origin == "the address editor":
        return f"0x{v:X}"
    try:
        txt = E.path.read_text()
    except OSError:
        return None
    m = re.search(rf"\b{re.escape(name)}\s*:\s*(0[xX][0-9A-Fa-f_]+)\b", txt)
    return m.group(1) if m and int(m.group(1).replace("_", ""), 16) == v else None


def _slice(name: str, bits: list | None) -> str:
    if not bits:
        return name
    return f"{name} bit {bits[0]}" if bits[0] == bits[1] else f"{name} bits {bits[0]}:{bits[1]}"


def _block(E: M.Elab, b: M.Box, prefix: str, rtl_prefix: str, part: str, dom_freq: dict) -> dict:
    kind = {"component": "block", "wrapped": "block", "hierarchy": "hierarchy", "interconnect": "interconnect",
            "reset_sync": "reset"}[b.kind]
    comp = b.comp.name if b.comp else (b.sub.name if b.sub else "")
    blk = {"id": f"{prefix}{b.name}", "name": b.name, "kind": kind, "component": comp,
           "component_top": b.comp.top if b.comp else None,
           "source": b.comp.source if b.comp else "hierarchy", "summary": b.comp.summary if b.comp else (b.sub.data.get("summary", "") if b.sub else ""),
           "variant": b.variant, "variants": b.comp.variants if b.comp else [], "module": b.module,
           "rtl_path": f"{rtl_prefix}u_{b.name}", "domain": b.domain, "freq_mhz": dom_freq.get(b.domain),
           "generated": b.generated, "note": b.note,
           "params": [{"name": k, "value": (v if isinstance(v, (int, str)) else str(v)), "origin": b.origin.get(k, "default"),
                       **({"shown": sh} if (sh := _shown(E, k, v, b.origin.get(k, "default"))) else {})}
                      for k, v in b.params.items() if not (isinstance(v, str) and v.startswith(("'", "{")))],
           "ports": [{"name": p.name, "dir": p.dir, "width": p.width, "kind": p.kind,
                      **({"async_ok": True} if p.async_ok else {})} for p in b.ports.values()
                     if not any(p.name in i.ports.values() for i in b.ifaces.values() if i.kind in M.BUS)],
           "ifaces": [{"name": i.name, "kind": i.kind, "role": i.role, "addr_w": i.addr_w, "data_w": i.data_w}
                      for i in b.ifaces.values() if i.kind in M.BUS],
           "cost": _cost(b, part), "build": None}
    if b.wrap and b.kind == "wrapped":
        blk["wrapper"] = {"kind": b.wrap["kind"], "module": b.module,
                          "inner": [f"{rtl_prefix}u_{b.name}/u_ip"] + [f"{rtl_prefix}u_{b.name}/{'u_win' if b.wrap['kind'] == 'window' else 'u_regs'}"]}
    if b.kind == "interconnect":
        blk["masters"] = b.wrap["masters"]
        blk["slaves"] = b.wrap["slaves"]
    return blk


def _level(E: M.Elab, prefix: str, rtl_prefix: str, part: str, dom_freq: dict, out: dict):
    blocks = [_block(E, b, prefix, rtl_prefix, part, dom_freq) for b in E.boxes.values()]
    links = []
    for L in E.links:
        mb, sb = E.boxes[L.master[0]], E.boxes[L.slave[0]]
        mi = mb.ifaces[L.master[1]]
        si = sb.ifaces[L.slave[1]]
        label = KIND_LABEL.get(L.kind, L.kind)
        if L.kind in ("axi4lite", "axi4"):
            label += f", {mi.data_w}-bit data, {mi.addr_w}-bit address"
        links.append({"id": f"{prefix}{L.name}", "kind": L.kind, "from": f"{prefix}{L.master[0]}", "from_if": L.master[1],
                      "to": f"{prefix}{L.slave[0]}", "to_if": L.slave[1], "label": label,
                      "data_w": mi.data_w, "addr_w": mi.addr_w, "slave_addr_w": si.addr_w})
    agg: dict = {}
    for s in E.segs:
        if s.auto:
            continue
        src = f"{prefix}{s.src[1]}" if s.src and s.src[0] == "box" else (f"port:{s.src[1]}" if s.src else "const")
        dst = f"{prefix}{s.dst[1]}" if s.dst[0] == "box" else f"port:{s.dst[1]}"
        sname = s.src[2] if s.src and s.src[0] == "box" else (s.src[1] if s.src else str(s.const))
        dname = s.dst[2] if s.dst[0] == "box" else s.dst[1]
        k = (src, dst)
        e = agg.setdefault(k, {"id": f"{prefix}{src}->{dst}".replace("port:", "").replace(":", "_"), "kind": "conduit",
                               "from": src, "to": dst, "signals": [], "width": 0})
        e["signals"].append({"from": sname, "to": dname, "width": s.width,
                             **({"bits": [s.src_lsb + s.width - 1, s.src_lsb]} if s.src and M.port_of(E, s.src).width != s.width else {}),
                             **({"to_bits": [s.dst_lsb + s.width - 1, s.dst_lsb]} if M.port_of(E, s.dst).width != s.width else {}),
                             **({"invert": True} if s.invert else {})})
        e["width"] += s.width
    for e in agg.values():
        e["label"] = ("; ".join(f"{_slice(x['from'], x.get('bits'))}{' (inverted)' if x.get('invert') else ''} -> {_slice(x['to'], x.get('to_bits'))}"
                              for x in e["signals"]) + f" ({e['width']} bit{'s' if e['width'] > 1 else ''})")
        links.append(e)
    ports = [{"name": p.name, "dir": p.dir, "width": p.width, "kind": p.kind,
              **({"async": True} if E.port_meta.get(p.name, {}).get("async") else {})} for p in E.ports.values()]
    exports = [{"name": n, "inst": f"{prefix}{i}", "iface": f} for n, (i, f) in E.exports.items()]
    out[prefix.rstrip("/")] = {"name": E.name, "kind": E.kind, "blocks": blocks, "links": links, "ports": ports,
                               "exports": exports, "file": str(E.path.relative_to(M.ROOT))}
    for b in E.boxes.values():
        if b.sub is not None:
            _level(b.sub, f"{prefix}{b.name}/", f"{rtl_prefix}u_{b.name}/", part, {**dom_freq, "clk": dom_freq.get(b.domain)}, out)


def crossings(E: M.Elab, prefix: str = "") -> list[dict]:
    out = []
    for s in E.segs:
        if s.src is None or s.auto == "clock":
            continue
        sd = M._src_domain(E, s.src)
        dd, ok = M._dst_domain(E, s.dst)
        if s.dst[0] == "ext" or sd is None or dd is None or sd == dd:
            continue
        b = E.boxes[s.dst[1]]
        sync = (f"{b.comp.name} (its {s.dst[2]} input has its own synchroniser)" if ok and b.comp else None)
        if s.auto == "reset":
            sync = "reset_sync (asynchronous assert, synchronous release)"
            ok = True
        out.append({"from": f"{prefix}{M.ref_text(s.src)}", "to": f"{prefix}{M.ref_text(s.dst)}", "from_domain": sd,
                    "to_domain": dd, "synchroniser": sync, "safe": bool(ok)})
    for b in E.boxes.values():
        if b.sub is not None:
            out += crossings(b.sub, f"{prefix}{b.name}/")
    return out


def build(E: M.Elab) -> dict:
    part = E.data.get("part", "xc7a100tcsg324-1")
    dom_freq = {n: d.freq_mhz for n, d in E.domains.items()}
    levels: dict = {}
    _level(E, "", "", part, dom_freq, levels)
    am = addrmap.as_json(E)
    return {"schema": "fpga-design-agent/blockdesign-graph/v1", "design": E.name, "top": E.top, "part": part,
            "board": E.data.get("board", ""), "summary": " ".join(str(E.data.get("summary", "")).split()),
            "domains": [{"name": n, "freq_mhz": d.freq_mhz, "clock_port": d.clk, "reset_port": d.reset_port,
                         "reset_sync": f"rst_sync_{n}" if d.reset_port else None} for n, d in E.domains.items()],
            "levels": levels, "crossings": crossings(E),
            "address_map": {"ranges": [{k: v for k, v in r.items()} for r in am["ranges"]], "holes": am["holes"],
                            "addr_w": next((b.params["ADDR_W"] for b in E.boxes.values() if b.kind == "interconnect"), 32)},
            "diagnostics": [{"code": d.code, "severity": d.severity, "where": d.where, "msg": d.msg} for d in E.all_diags()],
            "build": None, "check": None}
