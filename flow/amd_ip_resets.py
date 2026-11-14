#!/usr/bin/env python3
"""How AMD's own IP treats resets, and what a design that uses it must provide (brief 70).

    python3 flow/amd_ip_resets.py designs/<d> [more paths]    # the IP found in scripts, block designs and RTL, with its reset notes
    python3 flow/amd_ip_resets.py --all                        # every IP the survey covers

The table is `MAP`: one entry per IP, in our own words, from three sources that the entry names: the unencrypted HDL of the
Vivado 2026.1 install (read, never copied: results/70_resets/survey), the synthesised netlist of the IP's default configuration
(records/ip_netlists.tsv) and, for the Processor System Reset, a black-box simulation (records/psr_sequence.json). The product
guides' own requirements are quoted as requirements ("held at least N clocks"), with the guide's number. The numbers that come
from a record are read from it when the notes are built, so the table cannot drift from the measurement; `flow/tests/
test_70_resets.py` checks the rest against the survey record.

A note is advice for the engineer or the agent, not a rule that holds for every configuration: one configuration of each IP
was looked at, and the notes say where the product guide is the only source.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REC = ROOT / "results" / "70_resets" / "records"

#: IP catalogue name -> entry. ``port``: its reset port and polarity; ``style``: how it uses the reset; ``needs``: what the design
#: must provide; ``source``: where the entry comes from.
MAP: dict[str, dict] = {
    "proc_sys_reset": {
        "title": "Processor System Reset",
        "port": "ext_reset_in (polarity set by C_EXT_RESET_HIGH; the generated IP's default is active HIGH, the HDL entity's default is active low), "
                "aux_reset_in (active high), mb_debug_sys_rst (active high), dcm_locked (high = locked)",
        "style": "fully synchronous: each input crosses into slowest_sync_clk through a four-stage xpm_cdc_single and a low-pass filter; "
                 "the five output groups are plain flip-flops with no reset pin (they start asserted from their INIT value); "
                 "no asynchronous reset anywhere",
        "outputs": "bus_struct_reset and peripheral_reset (active high), interconnect_aresetn and peripheral_aresetn (active low), "
                   "mb_reset (active high); all synchronous to slowest_sync_clk",
        "needs": "drive slowest_sync_clk with the slowest clock of the logic it resets; hold ext_reset_in for at least C_EXT_RST_WIDTH "
                 "clocks (default 4: shorter pulses are ignored, measured); one instance per clock domain",
        "source": "survey + netlist + simulation (psr_sequence.json)",
    },
    "axi_gpio": {"title": "AXI GPIO", "port": "s_axi_aresetn (active low)",
                 "style": "one inverter makes an internal active-high reset; every register reset is synchronous; no asynchronous reset",
                 "needs": "a synchronous aresetn in the s_axi_aclk domain", "source": "survey + netlist"},
    "axi_uartlite": {"title": "AXI UART Lite", "port": "s_axi_aresetn (active low)",
                     "style": "as AXI GPIO: inverted once, synchronous resets only",
                     "needs": "a synchronous aresetn in the s_axi_aclk domain", "source": "survey + netlist"},
    "axi_timer": {"title": "AXI Timer", "port": "s_axi_aresetn (active low)",
                  "style": "as AXI GPIO: inverted once, synchronous resets only",
                  "needs": "a synchronous aresetn in the s_axi_aclk domain", "source": "survey + netlist"},
    "axi_intc": {"title": "AXI Interrupt Controller", "port": "s_axi_aresetn (active low)",
                 "style": "uses the active-low reset directly in its processes (no inversion); synchronous resets only",
                 "needs": "a synchronous aresetn in the s_axi_aclk domain", "source": "survey + netlist"},
    "axi_iic": {"title": "AXI IIC", "port": "s_axi_aresetn (active low)",
                "style": "inverted once to an internal active-high reset; synchronous resets only",
                "needs": "a synchronous aresetn in the s_axi_aclk domain", "source": "survey + netlist"},
    "axi_quad_spi": {"title": "AXI Quad SPI", "port": "s_axi_aresetn (active low), plus a soft-reset register",
                     "style": "synchronous resets in both clocks; the reset crosses into the SPI clock through xpm_cdc_single "
                              "synchronisers (many of them), so the SPI domain sees its own synchronised reset",
                     "needs": "a synchronous aresetn in the s_axi_aclk domain", "source": "survey + netlist"},
    "axi_dma": {"title": "AXI DMA", "port": "axi_resetn (active low, one per core; synchronised to s_axi_lite_aclk)",
                "style": "synchronous resets in each clock domain, the reset crossing between them through xpm_cdc_sync_rst; "
                         "most internal tests are active low, some active high (the IP mixes polarities inside)",
                "needs": "axi_resetn synchronised to s_axi_lite_aclk and held at least 16 of the slowest clocks (PG021)",
                "source": "survey + netlist + PG021"},
    "axi_cdma": {"title": "AXI CDMA", "port": "s_axi_lite_aresetn (active low)",
                 "style": "as AXI DMA: synchronous resets, xpm_cdc_sync_rst between clocks, mixed polarities inside",
                 "needs": "a synchronous aresetn in the lite clock domain", "source": "survey"},
    "axi_register_slice": {"title": "AXI Register Slice", "port": "aresetn (active low)",
                           "style": "the readable source registers the reset once and uses it as an ASYNCHRONOUS clear (assertion immediate) in the "
                                    "shift registers that track each channel's reset state: an asynchronous reset outside a synchroniser, driven "
                                    "from a register. The default configuration's synthesised netlist (records/ip_netlists.tsv) holds no asynchronous "
                                    "flip-flop, so this shows in the source and in some configurations only",
                           "needs": "aresetn synchronous to aclk; do not drive other block-RAM control pins from a copy of it",
                           "source": "survey + netlist"},
    "fifo_generator": {"title": "FIFO Generator", "port": "rst (asynchronous, independent clocks; active high) or srst (synchronous, common clock)",
                       "style": "the synthesisable source is encrypted: what is recorded is the netlist of the default configurations "
                                "(records/ip_netlists.tsv). The product guide requires an asynchronous reset pulse of at least "
                                "3 or C_SYNCHRONIZER_STAGE slowest clocks (PG057) and a reset window of the reset length plus 60 slowest clocks",
                       "needs": "see PG057; reset both ports' domains together", "source": "netlist + PG057"},
    "xpm_fifo": {"title": "XPM FIFO (xpm_fifo_sync, xpm_fifo_async)", "port": "rst (active high)",
                 "style": "xpm_fifo_sync takes a synchronous reset; xpm_fifo_async synchronises its reset into each clock "
                          "through xpm_cdc_sync_rst; the macro's readable source uses synchronous registers",
                 "needs": "hold rst for several clocks of the slower side (the macro's own wr_rst_busy / rd_rst_busy outputs say when it is safe to use)",
                 "source": "survey + netlist"},
    "xpm_cdc": {"title": "XPM CDC macros", "port": "src_arst (xpm_cdc_async_rst), src_rst (xpm_cdc_sync_rst)",
                "style": "xpm_cdc_async_rst is the one AMD reset synchroniser: asynchronous assert, synchronous release, "
                         "DEST_SYNC_FF stages; xpm_cdc_sync_rst is a pure synchronous stage chain",
                "needs": "RST_ACTIVE_HIGH set to the polarity wanted at dest_arst; DEST_SYNC_FF at least 2",
                "source": "survey + netlist"},
    "smartconnect": {"title": "SmartConnect", "port": "aresetn (active low, one per clock)",
                     "style": "encrypted source: only the guide and the block-design netlist are known; the guide requires that when "
                              "one connected device is reset all connected devices are reset together (PG247)",
                     "needs": "reset every device on the interconnect together, synchronised to its clock", "source": "block design + PG247"},
    "axi_interconnect": {"title": "AXI Interconnect", "port": "aresetn on every SI, MI and crossbar clock (active low)",
                         "style": "encrypted source: the guide says the core does not resynchronise any aresetn, partial reset is unsupported "
                                  "(every interface must be reset, overlapping), and the cores deassert valid and ready after aresetn is sampled active (PG059)",
                         "needs": "each aresetn synchronised to its aclk; all interfaces reset together, at least 16 clocks of the slowest",
                         "source": "block design + PG059"},
}
KNOWN = {n.lower(): n for n in MAP}
#: names that appear in scripts and block designs for the same IP
ALIASES = {"axi_gpio": "axi_gpio", "axi_uartlite": "axi_uartlite", "axi_timer": "axi_timer", "axi_intc": "axi_intc",
           "axi_iic": "axi_iic", "axi_quad_spi": "axi_quad_spi", "axi_dma": "axi_dma", "axi_cdma": "axi_cdma",
           "axi_register_slice": "axi_register_slice", "fifo_generator": "fifo_generator", "proc_sys_reset": "proc_sys_reset",
           "smartconnect": "smartconnect", "axi_interconnect": "axi_interconnect"}
VLNV = re.compile(r"xilinx\.com:ip:(\w+):", re.I)
CREATE = re.compile(r"create_ip\b[^\n]*?-name\s+(\w+)\b[^\n]*?-vendor\s+xilinx\.com", re.I)
CREATE2 = re.compile(r"create_ip\b[^\n]*?-vendor\s+xilinx\.com[^\n]*?-name\s+(\w+)\b", re.I)
SUFFIX = {".tcl", ".xdc", ".v", ".sv", ".vhd", ".yaml", ".yml", ".md", ".json"}


def _psr() -> dict | None:
    try:
        return json.loads((REC / "psr_sequence.json").read_text())["default"]
    except (OSError, ValueError, KeyError):
        return None


def notes_for(name: str) -> list[str]:
    e = MAP[name]
    out = [f"port: {e['port']}", f"inside: {e['style']}", f"you provide: {e['needs']}"]
    if name == "proc_sys_reset":
        d = _psr()
        if d:
            pu, st = d["power_up_release_cycle"], d["stimuli"].get("ext_8") or d["stimuli"].get("ext_5")
            out.append("measured sequence (Vivado 2026.1 simulation, default settings): outputs start asserted; with no request the "
                       f"bus and interconnect resets release at clock {pu['bus_struct_reset']}, peripheral at {pu['peripheral_reset']}, "
                       f"the core (mb_reset) at {pu['mb_reset']}; after a request the outputs assert {st['bus_struct_reset']['asserted_after']} "
                       f"clocks after it begins and release {st['bus_struct_reset']['released_after_end']}, {st['peripheral_reset']['released_after_end']} "
                       f"and {st['mb_reset']['released_after_end']} clocks after it ends (bus and interconnect, peripheral, core)")
    return out


def ips_in(text: str) -> set[str]:
    names = {n.lower() for n in VLNV.findall(text) + CREATE.findall(text) + CREATE2.findall(text)}
    return {ALIASES[n] for n in names if n in ALIASES}      # the XPM macros are not scanned for: every design has them


def scan(paths) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for p in paths:
        p = Path(p)
        files = [p] if p.is_file() else sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in SUFFIX
                                              and "build" not in f.parts and f.stat().st_size < 2_000_000)
        for f in files:
            try:
                text = f.read_text(errors="ignore")
            except OSError:
                continue
            for n in ips_in(text):
                found.setdefault(n, []).append(str(f))
    return found


def main(argv: list[str]) -> int:
    if argv[:1] == ["--all"]:
        names = sorted(MAP)
        found = {}
    else:
        found = scan(argv or ["."])
        names = sorted(found)
    for n in names:
        print(f"{MAP[n]['title']} ({n})" + (f"  [{', '.join(found[n][:2])}]" if n in found else ""))
        for ln in notes_for(n):
            print("  - " + ln)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
