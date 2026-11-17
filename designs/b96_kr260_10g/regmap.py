"""The register map of kr260_10g (brief 96) as data; `python3 designs/b96_kr260_10g/regmap.py --write` regenerates docs/register_map.md.

The host reaches the registers over the JTAG cable (BSCANE2 USER4, designs/b58a_trigger/rtl/jtag_bus.sv): 32-bit words, byte addresses,
12-bit address. Unmapped addresses read 0 and ignore writes; reserved bits read 0 and are ignored on write; reads have no side effects.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: (address, name, access, reset, description)
REGS = [
    (0x000, "ID", "RO", "0x96A00001", "Design identifier."),
    (0x004, "BUILD", "RO", "build stamp", "BUILD_STAMP generic (the flow sets it from the source hash)."),
    (0x008, "FEATURES", "RO", "variant", "bit 0 always 1; bit 1 NEAR_END (near-end PMA loopback selected at reset: variant a); bit 2 TRADE (trading path enabled at reset: variant b)."),
    (0x00C, "GT_CTRL", "RW", "0x008 (variant a: 0x00A)", "bits 2:0 LOOPBACK (000 normal, 001 near-end PCS, 010 near-end PMA, 100 far-end PMA; entering or leaving a loopback needs an RX datapath reset); bit 3 TX_DISABLE (1 = laser off; polarity on this carrier unconfirmed); bit 4 TX_POLARITY; bit 5 RX_POLARITY; bit 6 RX_LPM (1 = low-power equaliser)."),
    (0x010, "GT_RESET", "W", "0", "Write 1 to start an 8-clock reset pulse: bit 0 all, bit 1 TX PLL and datapath, bit 2 RX PLL and datapath, bit 3 TX datapath, bit 4 RX datapath. Reads 0."),
    (0x014, "GT_STAT", "RO", "-", "bit 0 TX_DONE, 1 RX_DONE, 2 GT power good, 3 CDR lock, 4 TX PMA reset done, 5 RX PMA reset done, 8 CDR stable, 9 PCS BLOCK_LOCK, 10 MOD_ABS (1 = no module, if the SFF polarity holds), 11 RX_LOS, 12 TX_FAULT."),
    (0x018, "CMD", "W", "0", "Write-only commands: bit 0 clear all counters and the order number; bit 1 start the generator run (held back 200 clocks so the configuration has crossed); bit 2 take a snapshot of the counter and timestamp vectors (reads of 0x100 and 0x200 are from the snapshot)."),
    (0x040, "MY_MAC_LO", "RW", "0x00000002", "Our MAC address, bytes 3:0 in bits 31:0, first byte on the wire in bits 7:0. Default 02:00:00:00:58:0A."),
    (0x044, "MY_MAC_HI", "RW", "0x0A58", "Our MAC address bytes 5:4 in bits 15:0."),
    (0x048, "VENUE_MAC_LO", "RW", "0x00000002", "The venue's (or NIC's) MAC address, same layout. Default 02:00:00:00:58:0F. Orders go to it; frames addressed to it that come back round a loop are only classified."),
    (0x04C, "VENUE_MAC_HI", "RW", "0x0F58", "Venue MAC bytes 5:4."),
    (0x050, "MY_IP", "RW", "0xC0A83A0A", "Our IPv4 address, first octet in bits 31:24 (192.168.58.10)."),
    (0x054, "VENUE_IP", "RW", "0xC0A83A0F", "The venue's IPv4 address (192.168.58.15)."),
    (0x058, "PORTS_A", "RW", "0x16A816A8", "bits 15:0 UDP port of the feed (5800); 31:16 our source port for orders (5800)."),
    (0x05C, "PORTS_B", "RW", "0x16AA16A9", "bits 15:0 UDP port of the orders (5801); 31:16 UDP port of probe frames (5802)."),
    (0x060, "THRESHOLD", "RW", "9975", "The rule: fire when an ADD or MODIFY on the ask side has a price at or below this (hundredths: 9975 is 99.75)."),
    (0x064, "ORDER_QTY", "RW", "100", "Quantity of the order the rule sends."),
    (0x068, "TRADE_CTRL", "RW", "variant", "bit 0 ARM (reset 0), bit 1 KILL (blocks all orders), bit 2 TRADE_EN (reset = TRADE generic), bits 5:4 generator frame kind (0 order, 1 feed, 2 probe, 3 test; reset 2)."),
    (0x06C, "GEN_LEN_INST", "RW", "0x00010042", "bits 15:0 generator frame length in bytes without the FCS (66 to 1514, reset 66); 31:16 instrument number (reset 1)."),
    (0x070, "GEN_PRICE", "RW", "9950", "Price carried by generated feed frames (hundredths)."),
    (0x074, "GEN_INTERVAL", "RW", "2000", "Clocks (161.13 MHz) between generated frames."),
    (0x078, "GEN_COUNT", "RW", "1", "Frames per run; the run starts on CMD bit 1."),
    (0x080, "I2C", "RW", "0", "Bit-banged module I2C: bit 0 pull SCL low, bit 1 pull SDA low (open drain); read bits 8 SCL, 9 SDA as seen on the pins."),
    (0x090, "SYSMON_ADDR", "RW", "0", "SYSMON DRP address; a write starts a read."),
    (0x094, "SYSMON_DATA", "RO", "0", "bit 16 valid, 15:0 data (die temperature is register 0x00, 10-bit result in bits 15:6, T = result x 501.3743 / 1024 - 273.6777 degrees C; units conversion is the host's)."),
]
RANGES = [
    (0x100, 16, "RXV", "Receive-domain snapshot, 16 words (RXV0 is 0x100). See the table below."),
    (0x200, 26, "TXV", "Transmit-domain snapshot, 26 words (TXV0 is 0x200). See the table below."),
]
RXV = ["lock (bit 0: PCS block lock now)", "bit slips", "lock losses", "lock events", "invalid sync headers (in lock)", "unknown block types (in lock)",
       "ordered sets", "frames ended (good + bad)", "frames with good FCS", "frames with bad FCS", "frames cut by an error character",
       "orders fired by the rule", "rule hits blocked (disarmed, kill or TRADE_EN off)", "frames too long to act on (IPv4 length above 60)",
       "length of the last frame in bytes, FCS included", "clocks from RX reset release to the first block lock (this link-up)"]
TXV = ["order frames sent", "feed frames sent", "probe frames sent", "test frames sent", "orders sent with a wrong FCS (poisoned)",
       "orders dropped (frame source busy)", "MAC underruns", "orders whose FCS verdict had not arrived at their last word",
       "orders whose live fields were not settled (sequence mismatch)", "go pulses seen", "timestamp: TX start of the last feed frame",
       "timestamp: TX start of the last probe frame", "timestamp: TX start of the last order", "timestamp: RX start of the last feed frame",
       "timestamp: RX start of the last probe frame", "timestamp: RX start of the last order frame", "echo E: last (probe RX start - probe TX start)",
       "E minimum", "E maximum", "E count", "loop L: last (order RX start - feed TX start)", "L minimum", "L maximum", "L count",
       "D': last (order TX start - feed RX start), both in the TX clock", "free-running TX-clock counter at the snapshot"]


def render() -> str:
    o = ["# kr260_10g register map (generated by regmap.py; do not edit)", "",
         "32-bit registers on the JTAG register bus (designs/b58a_trigger/rtl/jtag_bus.sv), byte addresses. **Unmapped addresses** read 0 and ignore writes. "
         "**Reserved bits** read 0 and are ignored on write. **Reads have no side effects.** **Write-only registers read as 0.** The counters and timestamps are read from a "
         "**snapshot** taken by CMD bit 2, so a multi-word read is coherent; every counter is cleared only by CMD bit 0 (a link restart does not clear them).", "",
         "| Address | Name | Access | Reset | Description |", "|---|---|---|---|---|"]
    for a, n, acc, rst, d in REGS:
        o.append(f"| 0x{a:03X} | {n} | {acc} | {rst} | {d} |")
    for a, n, name, d in RANGES:
        o.append(f"| 0x{a:03X} to 0x{a + 4 * (n - 1):03X} | {name}0 to {name}{n - 1} | RO | 0 | {d} |")
    o += ["", "## RXV words (receive clock domain, RXUSRCLK2)", "", "| Word | Address | Content |", "|---|---|---|"]
    o += [f"| RXV{i} | 0x{0x100 + 4 * i:03X} | {t} |" for i, t in enumerate(RXV)]
    o += ["", "## TXV words (transmit clock domain, TXUSRCLK2; timestamps in its clocks, 6.2058 ns each)", "", "| Word | Address | Content |", "|---|---|---|"]
    o += [f"| TXV{i} | 0x{0x200 + 4 * i:03X} | {t} |" for i, t in enumerate(TXV)]
    o += ["", "Timestamps: one free-running 32-bit counter in the TX clock. A TX start is stamped by the MAC's start strobe (the clock at which the "
          "preamble word is in the MAC's output register). An RX start crosses to the TX domain through an `xpm_cdc_pulse`: its stamp is late by the pulse's fixed latency "
          "(measured in simulation, docs/what_we_found.md) plus up to one TX clock of phase on the board.", ""]
    return "\n".join(o)


if __name__ == "__main__":
    out = Path(__file__).parent / "docs" / "register_map.md"
    if "--write" in sys.argv:
        out.write_text(render())
        print("wrote", out)
    else:
        print(render())
