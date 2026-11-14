"""The reset check (brief 71): the house reset rules, from AMD's reports first and our own netlist scan for the rest.

House rule (owner, 2026-11-13; fpga_agent_house_rules.md): resets are synchronous. An asynchronous reset appears only in
a reset or CDC synchroniser (asynchronous assert, synchronous release, as XPM does) or where an external device's reset is
asynchronous. The rules, their rationale and the waiver policy are in ``flow/hdl_rules.yaml`` (HDL-RST-01 to HDL-RST-05);
the background and the fixes are in the KB skills ``reset-strategy`` and ``control-sets-resets-and-enables``.

Three parts, each reported separately (a part that cannot run says why; the check is never a pass on a part that did not
run):

- **source**: the sources of build.yaml, elaborated by Yosys with the slang (SystemVerilog) and ghdl (VHDL) plugins (brief
  71B; ``flow/checks/elab.py``: no text scanner, and a design the tool cannot read is PARTIAL, never a pass). RST-ASYNC-01: a
  flip-flop or latch with an asynchronous control, outside a recognised synchroniser module and not reset by a declared
  external input. RST-POL-02: one root reset signal used in both polarities.
- **amd**: AMD's own rule rows from the stage's ``report_methodology``, ``report_drc`` and ``report_cdc`` (Vivado 2026.1
  ids, verified against ``get_methodology_checks``/``get_drc_checks``: results/71_check_suite/rule_catalogue_2026_1.tsv):
  LUTAR-1 (a LUT drives an asynchronous reset), DPIR-1/-2 and DPIR-3/DPOR-1..3 (asynchronous registers next to a DSP),
  RMIR-1, RMOR-1, RROR-1 (multiplier and RAM registers with an asynchronous reset; Advisory, so reported, not counted by
  the lint ruleset), ROAS-1 (both asynchronous set and reset), and report_cdc's asynchronous-reset rows.
- **netlist**: ``reset_scan.tsv`` (flow/checks/vivado_checks.tcl: one row per register with a reset pin that is not
  tied off, its root driver traced through buffers and LUT1 cells). RST-ASYNC-01 (an FDCE/FDPE outside a recognised
  synchroniser, not reset by a declared external asynchronous input), RST-POL-01 (one root reset used in both
  polarities), RST-DSPRAM-01 (an FDCE/FDPE whose D comes from, or whose Q feeds, a DSP or block RAM), RST-CDC-01 (a
  reset made by a register on one clock resets registers on another, or a device pin resets registers through no
  synchroniser), RST-LUT-01 (a LUT drives an asynchronous reset pin).

Recognised synchronisers: ``xpm_cdc_async_rst``, ``xpm_cdc_sync_rst``, the shell's ``reset_sync``, and the modules in
``architecture.yaml`` ``reset.synchronisers``. Declared external asynchronous inputs: ``architecture.yaml``
``reset.async_inputs`` (top-level port names). Vendor IP internals (cells under an IP core, a debug core or any
``xpm_`` macro other than the reset synchronisers) are not ours to change and are left out, except for RST-LUT-01 when
the LUT itself is outside the IP.
"""

from __future__ import annotations

import csv
import os
import re
import shutil
from pathlib import Path
from typing import Any

from flow.checks.elab import ASYNC_PRIMS, DDR_PRIMS

RECOGNISED = ("xpm_cdc_async_rst", "xpm_cdc_sync_rst", "reset_sync")
#: vendor hierarchy: AMD's XPM macros by their exact names, and the build's IP cores (build/<variant>/ip/<name>, passed in as
#: ``ip_names``) and everything generated under them. A user module is never vendor by its name alone (review fix).
XPM = re.compile(r"^xpm_(cdc_(single|array_single|gray|handshake|pulse|sync_rst|async_rst|low_latency_handshake)|"
                 r"fifo_(sync|async|axis|axif|axil|base|rst|reg_bit|reg_vec|counter_updn)|memory_\w+)$")
#: the AMD rule ids the reset check reads (verified on Vivado 2026.1, see the module docstring)
AMD_METHODOLOGY = ("LUTAR-1", "DPIR-1", "DPIR-2", "RMIR-1", "RMOR-1", "RROR-1", "ROAS-1")
AMD_DRC = ("DPIR-3", "DPOR-1", "DPOR-2", "DPOR-3")
AMD_CDC = ("CDC-7", "CDC-8")
FIX = {
    "RST-ASYNC-01": "make the register's reset synchronous (if (rst) inside always_ff @(posedge clk)); keep asynchronous "
                    "resets only inside a reset synchroniser, or declare the external input in architecture.yaml reset.async_inputs",
    "RST-POL-01": "use one polarity for each reset inside the design (active high, inverted once at the port or synchroniser)",
    "RST-POL-02": "test the reset in one polarity only; invert it once where it enters the module",
    "RST-DSPRAM-01": "give the DSP or block-RAM registers a synchronous reset (or none), so they pack into the primitive",
    "RST-CDC-01": "synchronise the reset into each clock domain (xpm_cdc_async_rst or reset_sync per domain)",
    "RST-LUT-01": "drive asynchronous resets only from a register (a synchroniser output) or a pin, never from logic",
}
CODE_RULE = {"RST-ASYNC-01": "HDL-RST-01", "RST-POL-01": "HDL-RST-02", "RST-POL-02": "HDL-RST-02",
             "RST-DSPRAM-01": "HDL-RST-03", "RST-CDC-01": "HDL-RST-04", "RST-LUT-01": "HDL-RST-05"}
#: every code the reset check can raise, by the hdl_rules.yaml tool key it belongs to
CODES = {"resets": tuple(CODE_RULE), "vivado": AMD_METHODOLOGY + AMD_DRC + AMD_CDC}


def reset_config(design: Path) -> dict[str, Any]:
    import yaml
    try:
        arch = yaml.safe_load((design / "architecture.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        arch = {}
    r = arch.get("reset") or {}
    return {"synchronisers": set(RECOGNISED) | set(r.get("synchronisers") or []),
            "declared": set(r.get("synchronisers") or []), "async_inputs": set(r.get("async_inputs") or [])}


def _f(file: str, line: int, code: str, msg: str, where: str | None = None, count: int = 1) -> dict[str, Any]:
    return {"tool": "resets", "code": code, "rule": CODE_RULE[code], "severity": "error", "file": file, "line": line,
            "where": where or f"{file}:{line}", "message": msg, "count": count, "fix": FIX[code]}


# ---- source (by elaboration, brief 71B) ----------------------------------------------------------------------------
#: the shell's own synchroniser, exempt by its file (not by its module name: review round 2)
SHELL_SYNCS = ("shell/rtl/reset_sync.sv",)
_RSTNAME = re.compile(r"(?i)rst|reset|clr|clear")
ASYNC_CELLS = ("$adff", "$adffe", "$aldff", "$aldffe", "$dffsr", "$dffsre", "$adlatch", "$dlatchsr")
SYNC_CELLS = ("$sdff", "$sdffe", "$sdffce")
_NOT = ("$not", "$_NOT_", "$logic_not")
_PASS = ("$buf", "$pos", "$_BUF_")


def _f(file: str, line: int, code: str, msg: str, where: str | None = None, count: int = 1) -> dict[str, Any]:
    return {"tool": "resets", "code": code, "rule": CODE_RULE[code], "severity": "error", "file": file, "line": line,
            "where": where or f"{file}:{line}", "message": msg, "count": count, "fix": FIX[code]}


def _str(v: Any) -> str:
    """A yosys JSON string parameter (an ASCII bit string) decoded, or the string itself."""
    v = str(v)
    if v and set(v) <= {"0", "1"} and len(v) % 8 == 0:
        return bytes(int(v[i:i + 8], 2) for i in range(0, len(v), 8)).decode("latin1")
    return v


def _bit(v: Any) -> int:
    """A yosys JSON parameter value (a binary string or an int) as an int."""
    if isinstance(v, int):
        return v
    try:
        return int(str(v), 2)
    except ValueError:
        return 0


class _Net:
    """The elaborated hierarchy (yosys JSON): drivers, names, and a root-signal trace through the hierarchy."""

    def __init__(self, modules: dict[str, Any], top: str):
        self.m, self.top = modules, top
        self._drv: dict[str, dict[Any, tuple[str, str, int]]] = {}
        self._nm: dict[str, dict[Any, str]] = {}

    def is_inst(self, cell: dict[str, Any]) -> bool:
        t = cell["type"]
        return t in self.m and "blackbox" not in self.m[t].get("attributes", {})

    def drivers(self, mod: str) -> dict[Any, tuple[str, str, int]]:
        if mod not in self._drv:
            d = {}
            for cn, c in self.m[mod]["cells"].items():
                pd = c.get("port_directions", {})
                for port, bits in c["connections"].items():
                    if pd.get(port) == "output":
                        for i, b in enumerate(bits):
                            if isinstance(b, int):
                                d[b] = (cn, port, i)
            self._drv[mod] = d
        return self._drv[mod]

    def name(self, mod: str, bit: Any) -> str:
        return self._name(mod, bit) or "<unnamed net>"

    def _name(self, mod: str, bit: Any) -> str:
        if mod not in self._nm:
            nm: dict[Any, str] = {}
            for n, v in self.m[mod]["netnames"].items():
                if n.startswith("$"):
                    continue
                for i, b in enumerate(v["bits"]):
                    if isinstance(b, int) and (b not in nm or len(n) < len(nm[b].split("[")[0])):
                        nm[b] = n if len(v["bits"]) == 1 else f"{n}[{i}]"
            self._nm[mod] = nm
        return self._nm[mod].get(bit, "")

    def root(self, frames: list[tuple[str, str]], bit: Any) -> tuple[str, str, int]:
        """(kind, name, inverted) of the signal that ultimately drives ``bit`` seen from the module at frames[-1]
        (frames: (module, instance name in the parent)): kind is const, port (a top-level port), reg (a storage cell's
        output), blackbox, logic or undriven. Buffers and inverters are looked through, and so are module ports."""
        frames = list(frames)
        inv = 0
        for _ in range(400):
            if not isinstance(bit, int):
                return "const", str(bit), inv
            mod = frames[-1][0]
            d = self.drivers(mod).get(bit)
            path = ".".join(f[1] for f in frames[1:])
            if d:
                cn, port, idx = d
                c = self.m[mod]["cells"][cn]
                t = c["type"]
                a = c["connections"].get("A", [])
                if t in _PASS + _NOT and idx < len(a) and (t != "$logic_not" or len(a) == 1):
                    inv ^= int(t in _NOT)
                    bit = a[idx]
                    continue
                if t in ("$reduce_or", "$reduce_and", "$reduce_bool", "$reduce_xor") and len(a) == 1:
                    bit = a[0]
                    continue
                if t in ("$eq", "$eqx", "$ne", "$nex"):          # r == 1'b0, r === 1'b1, r != 1'b0 ... on a one-bit signal
                    ab, bb = c["connections"].get("A", []), c["connections"].get("B", [])
                    for sig, k in ((ab, bb), (bb, ab)):
                        if len(sig) == 1 and len(k) == 1 and k[0] in ("0", "1") and isinstance(sig[0], int):
                            inv ^= int((k[0] == "0") == (t in ("$eq", "$eqx")))
                            bit = sig[0]
                            break
                    else:
                        return "logic", (path + "." if path else "") + self.name(mod, bit), inv
                    continue
                if self.is_inst(c):
                    cm = self.m[t]
                    frames.append((t, cn))
                    bit = cm["ports"][port]["bits"][idx]
                    continue
                nm = (path + "." if path else "") + self.name(mod, bit)
                kind = "reg" if (t.startswith("$") and ("dff" in t or "latch" in t)) or t in ASYNC_PRIMS else \
                    "logic" if t.startswith("$") else "blackbox"
                return kind, nm, inv
            ports = self.m[mod]["ports"]
            hit = next(((p, i) for p, pv in ports.items() if pv["direction"] != "output"
                        for i, b in enumerate(pv["bits"]) if b == bit), None)
            if hit is None:
                return "undriven", (path + "." if path else "") + self.name(mod, bit), inv
            if len(frames) == 1:
                pn = hit[0]
                return "port", pn if len(ports[pn]["bits"]) == 1 else f"{pn}[{hit[1]}]", inv
            inst = self.m[frames[-2][0]]["cells"][frames[-1][1]]
            frames.pop()
            cb = inst["connections"].get(hit[0], [])
            if hit[1] >= len(cb):                    # the port is left unconnected at this instance
                return "undriven", (path + "." if path else "") + self.name(mod, bit), inv
            bit = cb[hit[1]]
        return "logic", "?", inv

    def leaves(self, mod: str, bits: list[Any], depth: int = 12) -> set[str]:
        """Names of the signals in the combinational cone of ``bits`` (stops at registers, ports and instances)."""
        seen: set[Any] = set()
        names: set[str] = set()
        stack = [(b, 0) for b in bits]
        drv = self.drivers(mod)
        while stack:
            b, k = stack.pop()
            if not isinstance(b, int) or b in seen:
                continue
            seen.add(b)
            names.add(self.name(mod, b))
            d = drv.get(b)
            if not d or k > depth:
                continue
            c = self.m[mod]["cells"][d[0]]
            if c["type"].startswith("$") and "dff" not in c["type"] and "latch" not in c["type"]:
                pd = c.get("port_directions", {})
                for port, bs in c["connections"].items():
                    if pd.get(port) == "input":
                        stack += [(x, k + 1) for x in bs]
        return names


_YOSYS_CWD = [Path.cwd()]      # the folder the front end ran in: its src paths are relative to it (set by source_findings)


def _src(attrs: dict[str, Any]) -> tuple[str, int]:
    """(absolute file, first line) of a yosys src attribute ('a.sv:3.2-3.9|b.sv:1.1')."""
    s = str(attrs.get("src", "")).split("|")[0]
    m = re.match(r"^(.*?):(\d+)(?:\.\d+)?(?:-\d+(?:\.\d+)?)?$", s)
    f, ln = (m.group(1), int(m.group(2))) if m else (s, 0)
    if f and not Path(f).is_absolute():
        f = os.path.normpath(_YOSYS_CWD[0] / f)
    return f, ln


def _modname(m: str) -> str:
    return m.split("$")[0]


def elab_findings(el: Any, design: Path, cfg: dict[str, Any], root: Path, parts: dict[str, str]) -> list[dict[str, Any]]:
    """The findings of the elaborated design (the source part): every storage cell with an asynchronous control, a latch with
    a reset in its cone, and one root reset signal used in both polarities, outside a recognised synchroniser."""
    net = _Net(el.modules, el.top)
    out: dict[tuple[str, int, str], dict[str, Any]] = {}
    declared = cfg.get("declared", set())
    shell = {(root / x).resolve() for x in SHELL_SYNCS}
    top = net.top

    def add(rel: str, ln: int, code: str, msg: str) -> None:
        k = (rel, ln, code)
        if k in out:
            out[k]["count"] += 1
        else:
            out[k] = _f(rel, ln, code, msg)

    pol: dict[tuple[str, str], dict[int, tuple[str, int]]] = {}
    for mname, mod in net.m.items():
        if "blackbox" in mod.get("attributes", {}):
            continue
        base = _modname(mname)
        if base in el.stubbed:
            continue                              # a module the tool declared for a blackbox (XPM, IP): not user source
        mfile = _src(mod.get("attributes", {}))[0] or cfg.get("vhdl_files", {}).get(base.lower(), "")
        mfile_abs = (Path(mfile) if Path(mfile).is_absolute() else root / mfile).resolve() if mfile else None
        if (base in RECOGNISED or XPM.match(base)) and base not in declared and mfile_abs not in shell:
            cfg.setdefault("impostors", set()).add(base)
            out[(mfile, _src(mod["attributes"])[1], "impostor")] = _f(
                _rel(Path(mfile), design), _src(mod["attributes"])[1], "RST-ASYNC-01",
                f"{'entity' if mfile.lower().endswith(('.vhd', '.vhdl')) else 'module'} {base} takes the name of a recognised synchroniser or XPM macro; the "
                "netlist rules would exempt it: rename it, or declare it in architecture.yaml reset.synchronisers")
        if base in declared and not _has_sync_content(net, mname):
            out[(mfile, 0, "declared")] = _f(_rel(Path(mfile), design) if mfile else base, _src(mod["attributes"])[1],
                                             "RST-ASYNC-01", f"module {base} is declared a reset synchroniser but has no "
                                             "ASYNC_REG register and no xpm_cdc instance: a synchroniser exempts its whole "
                                             "subtree, so it must be one")
    # walk the instance tree from the top (a module may be reached more than once)
    visited: set[tuple[str, tuple[str, ...], bool]] = set()

    def walk(net: _Net, mname: str, frames: list[tuple[str, str]], exempt: bool, post: bool) -> None:
        key = (mname, tuple(f[1] for f in frames), post)
        if key in visited or len(frames) > 60:
            return
        visited.add(key)
        mod = net.m[mname]
        base = _modname(mname)
        mfile = _src(mod.get("attributes", {}))[0]
        mfile_abs = (Path(mfile) if Path(mfile).is_absolute() else root / mfile).resolve() if mfile else None
        here = exempt or (base in cfg["synchronisers"] and (base in declared or mfile_abs in shell)
                          and base not in cfg.get("impostors", set()) - declared)
        for cn, c in mod["cells"].items():
            t = c["type"]
            if net.is_inst(c):
                walk(net, t, frames + [(t, cn)], here, post)
                continue
            if (t in SYNC_CELLS) != post:
                continue                    # asynchronous pins from the netlist before opt_dff, synchronous ones after it
            rel_f, ln = _src(c.get("attributes", {}))
            if not rel_f:
                rel_f, ln = _src(mod.get("attributes", {}))
            if not rel_f:
                rel_f = cfg.get("vhdl_files", {}).get(base.lower(), "")
            rel = _rel(Path(rel_f), design) if rel_f else mname
            cc = c["connections"]
            pars = c.get("parameters", {})
            pins: list[tuple[str, Any, int]] = []        # (kind, bit, active-high polarity)
            what = "latch" if "latch" in t else "flip-flop"
            if t in ASYNC_CELLS:
                if t in ("$adff", "$adffe", "$adlatch"):
                    pins = [("async", b, _bit(pars.get("ARST_POLARITY", "1"))) for b in cc.get("ARST", [])]
                elif t in ("$aldff", "$aldffe"):
                    pins = [("async", b, _bit(pars.get("ALOAD_POLARITY", "1"))) for b in cc.get("ALOAD", [])]
                else:                                      # $dffsr, $dffsre, $dlatchsr
                    pins = [("async", b, _bit(pars.get("SET_POLARITY", "1"))) for b in cc.get("SET", [])]
                    pins += [("async", b, _bit(pars.get("CLR_POLARITY", "1"))) for b in cc.get("CLR", [])]
            elif t in SYNC_CELLS:
                pins = [("sync", b, _bit(pars.get("SRST_POLARITY", "1"))) for b in cc.get("SRST", [])]
            elif t in ASYNC_PRIMS:
                for p in ASYNC_PRIMS[t]:
                    inv = _bit(pars.get(f"IS_{p}_INVERTED", "0"))
                    pins += [("async", b, 0 if inv else 1) for b in cc.get(p, [])]
                what = f"{t} primitive ({cn})"
            elif t == "$dlatch":
                if not here:
                    add(rel, ln, "RST-ASYNC-01", f"module {base}: a latch (an LDCE/LDPE-style cell: its enable and data are "
                        "asynchronous controls): treated as an asynchronous element whatever its signals are called")
                continue
            elif t in DDR_PRIMS:
                sr = c.get("parameters", {}).get("SRTYPE")
                if sr is not None and "SYNC" in _str(sr) and "ASYNC" not in _str(sr):
                    continue
                pins = [("async", b, 1) for p_ in DDR_PRIMS[t] for b in cc.get(p_, [])]
                what = f"{t} primitive ({cn})"
            else:
                continue
            for kind, b, hi in pins:
                kd, nm, inv = net.root(frames, b)
                if kd == "const" and nm in ("0", "1"):
                    continue                              # tied off
                if kd == "const":                         # x or z: an undriven signal reaching a reset pin
                    kd, nm = "undriven", "(an undriven signal)"
                eff = hi ^ inv
                if kind == "async" and not here:
                    if kd == "port" and re.sub(r"\[\d+\]$", "", nm) in cfg["async_inputs"] and len(frames) >= 1:
                        pass                                  # a declared external asynchronous input (top-level port)
                    else:
                        add(rel, ln, "RST-ASYNC-01", f"module {base}: {what} has an asynchronous reset or set from {kd} "
                            f"{nm}: an asynchronous reset outside a recognised synchroniser")
                if not here and kd != "undriven":
                    pol.setdefault((kd, nm), {}).setdefault(eff, (rel, ln))
    for nt, post in ((net, False), (_Net(el.sync_modules, el.top), True)):
        inst = {c["type"] for mod in nt.m.values() for c in mod["cells"].values() if nt.is_inst(c)}
        roots = el.tops or sorted(m for m, v in nt.m.items() if "blackbox" not in v.get("attributes", {}) and m not in inst)
        for r_ in roots:
            if r_ in nt.m:
                walk(nt, r_, [(r_, "")], False, post)
    for (kd, nm), p in sorted(pol.items()):
        if len(p) == 2:
            (r1, l1), (r0, l0) = p[1], p[0]
            out[(r0, l0, "pol" + nm)] = _f(r0, l0, "RST-POL-02", f"{nm} is used as an active-high reset ({r1}:{l1}) and as an "
                                                               f"active-low reset ({r0}:{l0})")
    return list(out.values())


def _has_sync_content(net: _Net, mname: str, depth: int = 0) -> bool:
    mod = net.m[mname]
    if any("ASYNC_REG" in v.get("attributes", {}) for v in mod["netnames"].values()):
        return True
    for c in mod["cells"].values():
        if _modname(c["type"]) in ("xpm_cdc_async_rst", "xpm_cdc_sync_rst") or "ASYNC_REG" in c.get("attributes", {}):
            return True
        if net.is_inst(c) and depth < 8 and _has_sync_content(net, c["type"], depth + 1):
            return True
    return False


def source_findings(design: Path, files: list[Path], cfg: dict[str, Any], root: Path | None = None,
                    top: str | None = None, parts: dict[str, str] | None = None,
                    defines: list[str] | None = None, unmatched: list[str] | None = None, ip_names: set[str] | None = None) -> list[dict[str, Any]]:
    """The source part by elaboration (brief 71B): Yosys + slang (SystemVerilog) and ghdl (VHDL) read every file of the build's
    source list, ``proc`` lowers the processes, and the storage cells are judged (see ``elab_findings``). Fails closed:
    ``parts['source']`` says "not run: ..." with the tool's message when the tool is missing, a file is not read, or the
    elaboration fails, and the check is then PARTIAL, never a clean pass. There is no text-scanner fallback."""
    from flow.checks import elab
    parts = parts if parts is not None else {}
    root = root or Path(__file__).resolve().parents[2]
    sv, vh, hdr, other = elab.classify(files)
    problems: list[str] = [f"no file matches build.yaml sources entry '{g}'" for g in unmatched or []]
    problems += [f"{_rel(f, design)} is not a file" for f in files if not f.is_file()]
    sv, vh, hdr = ([f for f in g if f.is_file()] for g in (sv, vh, hdr))
    if other:
        problems.append("file(s) of a kind the front end does not read: " + ", ".join(_rel(f, design) for f in other[:3]))
    if elab.find_tool() is None:
        problems.append("yosys (OSS CAD Suite) not found; set FDA_OSS_CAD or install it under ~/.local/opt/oss-cad-suite "
                        "(the sign-off netlist part is unaffected)")
        parts["source"] = "not run: " + "; ".join(problems)
        return []
    if not (sv or vh):
        parts["source"] = "not run: " + (problems[0] if problems else "no HDL source file in the build list")
        return []
    cfg["vhdl_files"] = {}
    for f in vh:
        for e in elab._vhdl_entities([f]):
            cfg["vhdl_files"][e.lower()] = str(f)
    work = elab.workdir()
    out: list[dict[str, Any]] = []
    try:
        els = []
        vh_tops = {m for m in elab._vhdl_entities(vh)} if vh else set()
        if sv:
            els.append(elab.run_sv(sv, hdr, top if top and top not in vh_tops else None, defines or [], work, cwd=root, ip_names=set(ip_names or ()) | vh_tops))
        if vh:
            els.append(elab.run_vhdl(vh, top, work, cwd=root))
        for el in els:
            problems += el.errors[:3]
            if el.ok:
                out += elab_findings(el, design, cfg, root, parts)
        if hdr and not sv:
            problems.append("header file(s) listed without any module source: " + ", ".join(_rel(f, design) for f in hdr[:3]))
        stubbed = sorted(set().union(*(e.stubbed for e in els)))
        cfg["blackboxes"] = stubbed                  # read as empty blackboxes (XPM, IP, unisims): not a part status
    finally:
        shutil.rmtree(work, ignore_errors=True)
    parts["source"] = ("not run: " + "; ".join(problems[:4]) + (f"; {len(problems) - 4} more" if len(problems) > 4 else "")) \
        if problems else "ran"
    return out


def _rel(f: Path, design: Path) -> str:
    try:
        return f.resolve().relative_to(design.resolve()).as_posix()
    except ValueError:
        try:
            return f.resolve().relative_to(Path(__file__).resolve().parents[2]).as_posix()
        except ValueError:
            return f.name


# ---- netlist (reset_scan.tsv) -----------------------------------------------------------------------------------------
def read_scan(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def _parts(hier: str) -> list[str]:
    return [p for p in (hier or "").split("/") if p]


def _in(hier: str, names: set[str]) -> bool:
    return any(p in names for p in _parts(hier))


def _vendor(hier: str, ip_names: set[str]) -> bool:
    parts = _parts(hier)
    return any((XPM.match(p) and p not in RECOGNISED) or p in ip_names for p in parts)   # exact names (review round 2)


def _clocks(s: str) -> set[str]:
    return {c for c in (s or "").split(",") if c}


def netlist_findings(rows: list[dict[str, str]], cfg: dict[str, Any], ip_names: set[str] = frozenset()) -> list[dict[str, Any]]:
    """Group the scan's rows into findings (one per rule and root/module, with a register count)."""
    syncs = cfg["synchronisers"] - cfg.get("impostors", set())     # a user module or entity named like one is not one
    groups: dict[tuple[str, str], dict[str, Any]] = {}

    def add(code: str, key: str, where: str, msg: str, cell: str) -> None:
        g = groups.setdefault((code, key), {"where": where, "msg": msg, "cells": []})
        g["cells"].append(cell)

    pol: dict[str, dict[int, list[str]]] = {}
    unknown: set[str] = set()
    for r in rows:
        hier, cell, ref = r.get("hier", ""), r["cell"], r["ref"]
        is_async = ref in ("FDCE", "FDPE", "LDCE", "LDPE", "IDDR", "ODDR")   # IDDR/ODDR rows are only written for SRTYPE ASYNC
        vendor = _vendor(hier, ip_names)
        # a module counts as a synchroniser by its name AND its structure (an xpm_cdc_*_rst instance or ASYNC_REG registers inside
        # it, column sync_struct, brief 71B); scans made before that column existed are judged by name alone
        in_sync = _in(hier, syncs if "sync_struct" not in r else syncs & set(_parts(r["sync_struct"])))
        root, kind, rref = r.get("root", ""), r.get("root_kind", ""), r.get("root_ref", "")
        mod = (_parts(hier) or ["<top>"])[0]
        if is_async and kind == "cell" and re.match(r"^LUT(?!1$)", rref) and not _vendor(r.get("root_hier", ""), ip_names):
            add("RST-LUT-01", root, root, f"{rref} {root} drives the {r['pin']} pin of registers", cell)
        if vendor:
            continue
        port_base = re.sub(r"\[\d+\]$", "", root)
        if is_async and not in_sync and not (kind == "port" and port_base in cfg["async_inputs"]):
            add("RST-ASYNC-01", f"{mod}|{root}", cell, f"asynchronous {r['pin']} from {kind} {root or '?'} on registers in "
                                                         f"{mod if mod != '<top>' else 'the top module'}", cell)
        if is_async and not in_sync and (re.match(r"^(DSP48|RAMB)", r.get("d_ref", "")) or
                                         re.search(r"(^|,)(DSP48|RAMB)", r.get("q_refs", ""))):
            add("RST-DSPRAM-01", f"{mod}|{root}", cell, f"registers next to a DSP or block RAM (D from {r.get('d_ref') or '-'}, "
                                                        f"Q to {r.get('q_refs') or '-'}) have an asynchronous {r['pin']}", cell)
        if not in_sync:
            rclk, clk = _clocks(r.get("root_clock", "")), _clocks(r.get("clock", ""))
            if kind == "cell" and rref.startswith("FD") and (not rclk or not clk):
                unknown.add(cell)
            if kind == "cell" and rref.startswith("FD") and rclk and clk and not (rclk & clk):
                add("RST-CDC-01", f"{root}|{','.join(sorted(clk))}", root,
                    f"reset made by {root} on {','.join(sorted(rclk))} resets registers on {','.join(sorted(clk))} "
                    f"without a synchroniser", cell)
            elif kind == "port" and "IBUF" in r.get("path", "") and not is_async:
                add("RST-CDC-01", f"{root}|pin", root, f"device pin {root} resets registers on {','.join(sorted(clk)) or '?'} "
                                                       f"without a synchroniser", cell)
        if kind in ("cell", "port"):
            eff = int(r.get("root_inverted", "0") in ("1", "true")) ^ int(r.get("pin_inverted", "0") in ("1", "true"))
            pol.setdefault(f"{kind}:{root}", {}).setdefault(eff, []).append(cell)
    for rid, p in pol.items():
        if len(p) == 2:
            add("RST-POL-01", rid, rid.split(":", 1)[1],
                f"reset {rid.split(':', 1)[1]} is used active high on {len(p[0])} and active low on {len(p[1])} registers "
                f"(two nets, two control sets)", p[1][0])
    out = []
    for (code, _), g in sorted(groups.items()):
        n = len(g["cells"])
        out.append({"tool": "resets", "code": code, "rule": CODE_RULE[code], "severity": "error", "where": g["where"],
                    "message": g["msg"] + f" ({n} register{'s' if n != 1 else ''}, e.g. {g['cells'][0]})", "count": n,
                    "fix": FIX[code], "file": None, "line": None})
    if unknown:              # not a finding, but the clock-domain rule could not be judged for these registers
        out.append({"tool": "resets", "code": "RST-CDC-01", "rule": CODE_RULE["RST-CDC-01"], "severity": "unknown",
                    "where": "netlist", "message": f"{len(unknown)} register(s) whose reset comes from a register with no "
                    f"timed clock on one side (e.g. {sorted(unknown)[0]}): the clock-domain rule was not judged; constrain "
                    "every clock", "count": len(unknown), "fix": "create_clock on every clock", "file": None, "line": None,
                    "incomplete": True})
    return out


def amd_findings(meth: list[dict[str, Any]] | None, drc: list[dict[str, Any]] | None,
                 cdc: dict[str, Any] | None, stage: str) -> list[dict[str, Any]]:
    """The reset-related rows of AMD's own reports (parsed by flow/gates.py's parsers)."""
    out = []
    for src, ids, rows in (("report_methodology", AMD_METHODOLOGY, meth), ("report_drc", AMD_DRC, drc),
                           ("report_cdc", AMD_CDC, (cdc or {}).get("rules"))):
        for r in rows or []:
            if r.get("rule") in ids:
                out.append({"tool": "vivado", "code": r["rule"], "severity": str(r.get("severity", "")),
                            "where": f"{src}@{stage}", "message": f"{r.get('description', '')} (x{r.get('count', 1)})",
                            "count": r.get("count", 1), "file": None, "line": None})
    return out
