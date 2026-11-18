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
    (0x01C, "TXPPM", "RW", "0", "TX phase-interpolator ppm controller (brief 96C), driven into the GT's TXPIPPMEN, TXPIPPMSEL and TXPIPPMSTEPSIZE ports (UG576 v1.7.1 Table 3-33): bits 4:0 TXPIPPMSTEPSIZE (bit 4 = 1 increments the PI code, 0 decrements; bits 3:0 the amount, 0 to 15), bit 5 TXPIPPMEN (hold at 1 while an offset is wanted), bit 6 TXPIPPMSEL (must be 1 when the controller is used). Reset 0 (off). In the ppm_* builds (ppm.xdc sets TXPI_PPM = 1 and TXPI_SYNFREQ_PPM = 7) UG576 Equation 3-3 predicts 61.04 ppm a step; which direction is faster against the core clock, and whether TXUSRCLK2 follows the shifted line rate (then the two user clocks stay together), are measured by the board run from the frequency counter (RXV27, RXV28), never assumed. Written values cross to TXUSRCLK (322 MHz) as one static bus."),
    (0x020, "GT_BUF", "RO", "-", "GT buffer status (brief 96C): bits 1:0 TXBUFSTATUS now, bits 4:2 RXBUFSTATUS now, bits 6:5 TXBUFSTATUS seen (OR) since the last clear, bits 9:7 RXBUFSTATUS seen (OR) since the last clear; that is {rxbuf_seen[2:0], txbuf_seen[1:0], rxbuf[2:0], txbuf[1:0]}. The seen fields restart from the present value on CMD bit 0. A non-zero seen field after the link was up means a GT buffer error (the bit meanings are AMD's, UG576; this register only shows them). A GT reset sets them, so clear after the link locks."),
    (0x018, "CMD", "W", "0", "Write-only commands: bit 0 clear the counters and the order number (which counters: see \"What clears what\" below); bit 1 start the generator run (held back 200 clocks so the configuration has crossed); bit 2 take a snapshot of the counter and timestamp vectors (reads of 0x100 and 0x200 are from the snapshot)."),
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
    (0x100, 29, "RXV", "Receive-side snapshot, 29 words (RXV0 is 0x100): the PCS counters are from the receive clock, the MAC, trade and rate-match counters from the core (transmit) clock. See the table below."),
    (0x200, 26, "TXV", "Transmit-domain snapshot, 26 words (TXV0 is 0x200). See the table below."),
]
RXV = ["lock (bit 0: PCS block lock now)", "bit slips", "lock losses", "lock events", "invalid sync headers (in lock)", "unknown block types (in lock)",
       "ordered sets", "frames ended (good + bad)", "frames with good FCS", "frames with bad FCS", "frames cut by an error character",
       "orders fired by the rule", "rule hits blocked (disarmed, kill or TRADE_EN off)", "frames too long to act on (IPv4 length above 60)",
       "length of the last frame in bytes, FCS included", "clocks from RX reset release to the first block lock (this link-up)",
       "order_ok: returned order frames that matched what the rule decided (content, 66-byte length, good FCS)",
       "order_bad: returned order frames that did not (a wrong field, a wrong length, a bad FCS, or cut by an error character)",
       "rate match: blocks written into the elastic buffer (receive clock)", "rate match: blocks dropped because the buffer was full (receive clock; must be 0)",
       "rate match: idle blocks inserted (core clock)", "rate match: idle blocks deleted (core clock)",
       "rate match: clocks with nothing to output inside a frame (a one-clock bubble, nothing lost)", "rate match: blocks output (data, inserted idles)",
       "rate match: blocks discarded while the block lock was low", "rate match: smallest visible fill at an output slot since the clear (blocks)",
       "rate match: largest visible fill at an output slot since the clear (blocks)",
       "frequency counter: receive-clock cycles counted in the last full window of 2^24 core clocks (ppm = (value - 16777216) / 16777216 x 1e6; positive: the receive clock is faster than the core clock; valid when RXV28 is at least 2 and no GT restart fell in the window)",
       "frequency counter: windows completed since the core came out of reset"]
TXV = ["order frames sent", "feed frames sent", "probe frames sent", "test frames sent", "orders sent with a wrong FCS (poisoned)",
       "orders dropped (frame source busy)", "MAC underruns", "orders whose FCS verdict had not arrived at their last word",
       "orders whose live fields were not settled (sequence mismatch)", "go pulses seen (the order count the transmit side expects)", "timestamp: TX start of the last feed frame",
       "timestamp: TX start of the last probe frame", "timestamp: TX start of the last order", "timestamp: RX start of the last feed frame",
       "timestamp: RX start of the last probe frame", "timestamp: RX start of the last order frame", "echo E: last (probe RX start - probe TX start)",
       "E minimum", "E maximum", "E count", "loop L: last (order RX start - feed TX start)", "L minimum", "L maximum", "L count",
       "D': last (order TX start - feed RX start), both in the TX clock", "free-running TX-clock counter at the snapshot"]


def render() -> str:
    o = ["# kr260_10g register map (generated by regmap.py; do not edit)", "",
         "32-bit registers on the JTAG register bus (designs/b58a_trigger/rtl/jtag_bus.sv), byte addresses. **Unmapped addresses** read 0 and ignore writes. "
         "**Reserved bits** read 0 and are ignored on write. **Reads have no side effects.** **Write-only registers read as 0.** The counters and timestamps are read from a "
         "**snapshot** taken by CMD bit 2, so a multi-word read is coherent. Which counters a clear or a restart resets is stated under \"What clears what\".", "",
         "| Address | Name | Access | Reset | Description |", "|---|---|---|---|---|"]
    for a, n, acc, rst, d in REGS:
        o.append(f"| 0x{a:03X} | {n} | {acc} | {rst} | {d} |")
    for a, n, name, d in RANGES:
        o.append(f"| 0x{a:03X} to 0x{a + 4 * (n - 1):03X} | {name}0 to {name}{n - 1} | RO | 0 | {d} |")
    o += ["", "## RXV words (receive clock domain, RXUSRCLK2)", "", "| Word | Address | Content |", "|---|---|---|"]
    o += [f"| RXV{i} | 0x{0x100 + 4 * i:03X} | {t} |" for i, t in enumerate(RXV)]
    o += ["", "## TXV words (transmit clock domain, TXUSRCLK2; timestamps in its clocks, 6.2058 ns each)", "", "| Word | Address | Content |", "|---|---|---|"]
    o += [f"| TXV{i} | 0x{0x200 + 4 * i:03X} | {t} |" for i, t in enumerate(TXV)]
    o += ["", "## What clears what", "",
          "- **CMD bit 0 (clear)** clears every event counter: RXV1 to RXV13, `order_ok` and `order_bad` "
          "(RXV16, RXV17) and the rate-match counters RXV18 to RXV24 (the fill minimum and maximum, RXV25 and RXV26, restart too); TXV0 to TXV9 (the sent, poisoned, dropped, underrun, late, `stale` and `go` counts) and the E and L minimum, maximum and count words "
          "(TXV17 to TXV19, TXV21 to TXV23); and it restarts the order number on both sides. It does **not** clear the last-value words and timestamps "
          "(RXV14, RXV15, RXV27, RXV28, TXV10 to TXV16, TXV20, TXV24, TXV25). Before brief 97C it left `stale` and `go` running and cleared only the receive side's order number, "
          "which put the two sides out of step (every later order was stale, late and poisoned).",
          "- **A restart of the RX datapath** (GT_RESET bit 2, 4 or 0, or the receive side losing its done level) holds the receive PCS, MAC and decision logic in reset "
          "and clears the order number and RXV15; the receive event counters keep their values.",
          "- **A restart of the TX datapath** (GT_RESET bit 1, 3 or 0) clears every transmit counter, timestamp and the order count.",
          "- **Order number and order count stay in step (97C).** The receive side numbers the orders it fires (1, 2, ...); the transmit side counts the go pulses it "
          "receives and compares that count with the number on the live field bus (`stale` counts a mismatch; the order then leaves with a wrong FCS). Both restart "
          "to 0 on a CMD clear and on any restart of either side: a GT_RESET write, or either side's done level changing, sends a restart pulse to both clock domains. "
          "The two restarts arrive a few clocks apart, so a restart while an order is in flight can flag that order stale; that is the fail-safe direction, and no "
          "order is in flight while the link restarts.",
          "- **Order-content check (97C).** The receive side compares every returned order frame (UDP port = ORDER port) with the decision it took: the Bench Feed v1 template "
          "bytes, sequence number, type NEW_ORDER (0x10), side BUY (0), instrument, price, quantity and reference; the length must be 66 bytes plus the FCS, the FCS good and "
          "no error character. `order_ok` counts frames that pass all of it, `order_bad` the rest. It holds the latest decision only: an order that comes back after the next "
          "decision is counted bad, so keep the generator interval above the loop time. The logic reads the receive words in parallel with the decision and is not on "
          "the path from a received price to the order's first word, so the tick-to-trade clock count does not change (measured in simulation, results/b97c).", "",
          "- **Which clock owns which word (brief 96C).** RXV0 to RXV6, RXV15, RXV18 and RXV19 are counted in the receive clock and cleared by the clear command's copy in that clock; the rest "
          "of RXV in the core clock. Both are snapshotted together by CMD bit 2 only to within the handshake's few clocks: counters in the two clocks are not mutually exact "
          "(`rm_wr` and `rm_out` can differ by the blocks in flight, at most about 20).",
          "- **Rate matching (brief 96C)** inserts or deletes idle blocks between frames only; see docs/design.md section 9 for the policy and its limits.", "",
          "Timestamps: one free-running 32-bit counter in the TX clock. A TX start is stamped by the MAC's start strobe (the clock at which the "
          "preamble word is in the MAC's output register). Since brief 96C the MAC and the decision logic run in the TX clock behind the elastic buffer, so an RX start is "
          "stamped in the same clock by the MAC's start strobe: no crossing, no phase term; its latency includes the elastic buffer (6 to 7 clocks in simulation, "
          "which varies by a clock with the gearbox pause and the buffer's read cadence).", ""]
    return "\n".join(o)


if __name__ == "__main__":
    out = Path(__file__).parent / "docs" / "register_map.md"
    if "--write" in sys.argv:
        out.write_text(render())
        print("wrote", out)
    else:
        print(render())
