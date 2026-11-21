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
    (0x008, "FEATURES", "RO", "variant", "bit 0 always 1; bit 1 NEAR_END (near-end PMA loopback selected at reset: variant a); bit 2 TRADE (trading path enabled at reset: variant b); bit 3 RATE_MATCH (the build has brief 96C's elastic buffer on the receive path; 0 in the default build, which has the 97C path); bit 4 EYESCAN (the build has brief 96D's DRP access, eye-scan sequencer and TX drive registers; 0 in the default build, where those registers read 0 and ignore writes); bit 5 RM_OWN (brief 96E: the elastic buffer is our own gray-pointer one, rtl/rate_match_gp.sv, instead of the one on AMD's xpm_fifo_async; 1 only when bit 3 is 1; 0 in the default build); bit 6 GT_BYPASS (brief 96F1: build rm_gp_bypass, both GT elastic buffers bypassed, see GT_BUF bits 15:10; 0 in every other build)."),
    (0x00C, "GT_CTRL", "RW", "0x008 (variant a: 0x00A)", "bits 2:0 LOOPBACK (000 normal, 001 near-end PCS, 010 near-end PMA, 100 far-end PMA; entering or leaving a loopback needs an RX datapath reset); bit 3 TX_DISABLE (1 = laser off; polarity on this carrier unconfirmed); bit 4 TX_POLARITY; bit 5 RX_POLARITY; bit 6 RX_LPM (1 = low-power equaliser)."),
    (0x010, "GT_RESET", "W", "0", "Write 1 to start an 8-clock reset pulse: bit 0 all, bit 1 TX PLL and datapath, bit 2 RX PLL and datapath, bit 3 TX datapath, bit 4 RX datapath. Reads 0."),
    (0x014, "GT_STAT", "RO", "-", "bit 0 TX_DONE, 1 RX_DONE, 2 GT power good, 3 CDR lock, 4 TX PMA reset done, 5 RX PMA reset done, 8 CDR stable, 9 PCS BLOCK_LOCK, 10 MOD_ABS (1 = no module, if the SFF polarity holds), 11 RX_LOS, 12 TX_FAULT."),
    (0x01C, "TXPPM", "RW", "0", "TX phase-interpolator ppm controller (brief 96C), driven into the GT's TXPIPPMEN, TXPIPPMSEL and TXPIPPMSTEPSIZE ports (UG576 v1.7.1 Table 3-33): bits 4:0 TXPIPPMSTEPSIZE (bit 4 = 1 increments the PI code, 0 decrements; bits 3:0 the amount, 0 to 15), bit 5 TXPIPPMEN (hold at 1 while an offset is wanted), bit 6 TXPIPPMSEL (must be 1 when the controller is used). Reset 0 (off). In the ppm_* builds (ppm.xdc sets TXPI_PPM = 1 and TXPI_SYNFREQ_PPM = 7) UG576 Equation 3-3 predicts 61.04 ppm a step; which direction is faster against the core clock, and whether TXUSRCLK2 follows the shifted line rate (then the two user clocks stay together), are measured by the board run from the frequency counter (RXV27, RXV28), never assumed. Written values cross to TXUSRCLK (322 MHz) as one static bus."),
    (0x020, "GT_BUF", "RO", "-", "GT buffer status (brief 96C): bits 1:0 TXBUFSTATUS now, bits 4:2 RXBUFSTATUS now, bits 6:5 TXBUFSTATUS seen (OR) since the last clear, bits 9:7 RXBUFSTATUS seen (OR) since the last clear; that is {rxbuf_seen[2:0], txbuf_seen[1:0], rxbuf[2:0], txbuf[1:0]}. The seen fields restart from the present value on CMD bit 0. A non-zero seen field after the link was up means a GT buffer error (the bit meanings are AMD's, UG576; this register only shows them). A GT reset sets them, so clear after the link locks. Bits 15:10 exist only in build rm_gp_bypass (brief 96F1; they read 0 elsewhere): bit 10 TX buffer-bypass controller done, 11 RX controller done (the controllers' own levels, as the Wizard drives them), 12 TX controller error seen and 13 RX controller error seen since the last clear (CMD bit 0), 14 TX controller error now, 15 RX controller error now (an error is PHALIGNDONE not high when the alignment ends). Bits 29:16 (brief 96F1b; build rm_gp_bypass only, 0 elsewhere) report each controller's alignment timeout and retry: bits 19:16 TX retries and bits 23:20 RX retries in the current GT reset sequence (0 to 3; the count restarts from 0 when the reset helper's done drops), bit 24 TX gave up and bit 25 RX gave up (every attempt timed out: 30 ms for TX, 130 ms for RX, three retries; stays set until the next GT reset sequence), bits 26 and 27 the same two flags seen since the last clear, bits 28 (TX) and 29 (RX) a retry seen since the last clear (CMD bit 0 restarts the seen bits from the present values; core reset clears them). The retry counts cross from the user clock to the 100 MHz clock as a plain 4-bit value (not gray coded: they change only at timeouts, milliseconds apart), so a read within a few clocks of a change, or of the clear at a new reset sequence, can return a transient value: read them after the link is up, or twice. A gave-up flag means the link cannot come up in that direction until a GT reset; a retry that then succeeds is recorded, not an error. A controller error (bits 12 to 15) is never retried. In that build TX_DONE and RX_DONE (GT_STAT bits 0 and 1) mean the GT reset helper is done AND the controller has restarted and finished for this sequence with no error; the TXBUFSTATUS and RXBUFSTATUS fields above are not meaningful with the buffers bypassed (UNCONFIRMED against UG576: record them, do not judge them)."),
    (0x018, "CMD", "W", "0", "Write-only commands: bit 0 clear the counters and the order number (which counters: see \"What clears what\" below); bit 1 start the generator run (held back 200 clocks so the configuration has crossed); bit 2 take a snapshot of the counter and timestamp vectors (reads of 0x100 and 0x200 are from the snapshot)."),
    (0x024, "DRP_ADDR", "RW", "0", "EYESCAN builds only (brief 96D; reads 0 and ignores writes otherwise): bits 9:0 the GT channel's DRP address for the next raw access."),
    (0x028, "DRP_DATA", "RW", "0", "EYESCAN builds only: a write sets the data for the next raw DRP write (bits 15:0); a READ returns the data of the last raw or sequencer DRP READ, never what was last written (a DRP write does not change it)."),
    (0x02C, "ES_CMD", "W", "0", "EYESCAN builds only; reads 0. Bit 0 one raw DRP read of DRP_ADDR, bit 1 one raw DRP write of DRP_DATA to DRP_ADDR, bit 2 start one eye-scan point from ES_POINT, bit 3 clear the sticky flags (drp_tmo, rejected). Bits 0 and 1 together: the write is ignored and the read runs; bit 2 with bit 0 or 1: the raw access wins and the start is dropped. A command that arrives while a point or a raw access is running is IGNORED and sets ES_STAT bit 4 (rejected)."),
    (0x030, "ES_STAT", "RO", "0", "EYESCAN builds only: bit 0 busy (a raw access or a point is running), bit 1 point done (set when a point ends, cleared by the next start), bit 2 point timed out (the status poll hit ES_TMO; the results read 0 and the run bit was cleared), bit 3 DRP timeout (an access got no DRDY within 256 clocks; sticky until ES_CMD bit 3; a point aborts at once: no further DRP write except clearing the run bit if it may have been set, results 0, bit 2 set), bit 4 rejected (sticky until ES_CMD bit 3); bits 11:8 es_control_status as the sequencer last read it (0101 = END); bits 15:12 the sequencer step; bits 31:16 points completed since reset."),
    (0x034, "ES_POINT", "RW", "0", "EYESCAN builds only: the next point (latched when the point starts: writing it or ES_TMO during a point has no effect on that point). Bits 11:0 ES_HORZ_OFFSET field (UG576 Table 4-20: [10:0] two's complement counts, [11] phase unification = 1 for negative counts), bits 18:12 RX_EYESCAN_VS_CODE (magnitude), bit 19 RX_EYESCAN_VS_NEG_DIR, bit 20 RX_EYESCAN_VS_UT_SIGN, bits 22:21 RX_EYESCAN_VS_RANGE, bits 27:23 ES_PRESCALE (the point runs 2^(1+value) times 65535 cycles at most)."),
    (0x038, "ES_TMO", "RW", "500000000", "EYESCAN builds only: the status poll of a point is abandoned after this many clk cycles (100 MHz: the reset value is 5 s). Must exceed the run time of the prescale used (about 0.42 s at prescale 10, 13.3 s at 15, at 10.3125 Gb/s)."),
    (0x03C, "ES_RES", "RO", "0", "EYESCAN builds only: the last finished point's es_sample_count in bits 31:16 and es_error_count in bits 15:0 (both saturate at 65535; both are cleared to 0 when a point starts and stay 0 after a timeout). Bits examined = samples x 2^(1+ES_PRESCALE) x 32."),
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
    (0x084, "GT_DRIVE", "RW", "0x018", "EYESCAN builds only (the other builds drive the same constants): bits 4:0 TXDIFFCTRL (reset 11000 = 873 mVppd, UG576 Table 3-35; [0] is unused by the GT), bits 9:5 TXPRECURSOR, bits 14:10 TXPOSTCURSOR (reset 0 and 0: no emphasis), bit 16 RXDFELPMRESET (level; pulse it after changing RX_LPM so the equaliser re-adapts). The ports are asynchronous to the GT. The optical module's input is protected by choosing values at or below the reset swing; this register does not limit them."),
    (0x090, "SYSMON_ADDR", "RW", "0", "SYSMON DRP address; a write starts a read."),
    (0x094, "SYSMON_DATA", "RO", "0", "bit 16 valid, 15:0 data (die temperature is register 0x00, 10-bit result in bits 15:6, T = result x 501.3743 / 1024 - 273.6777 degrees C; units conversion is the host's)."),
]
RANGES = [
    (0x100, 29, "RXV", "Receive-side snapshot, 29 words (RXV0 is 0x100): the PCS counters are from the receive clock, the MAC, trade and rate-match counters from the core (transmit) clock. See the table below. In a build with RATE_MATCH = 0 (the default) the words only brief 96C's elastic buffer drives, RXV18 to RXV28 (the rate-match counters and the frequency counter), read 0; RXV0 to RXV17 are the 97C words, unchanged."),
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
          "- **Rate matching (brief 96C)** inserts or deletes idle blocks between frames only; see docs/design.md section 9 for the policy and its limits.",
          "- **Eye scan and DRP (brief 96D), EYESCAN builds only.** The GT's DRP port is driven by one sequencer (rtl/es_ctrl.sv) in the 100 MHz clock: one access at a time. "
          "A raw access (ES_CMD bits 0 and 1) and a point (bit 2) cannot overlap: a command that arrives while busy is ignored and sets `rejected`. A point does read-modify-write on "
          "three DRP words (0x04F ES_HORZ_OFFSET, 0x097 RX_EYESCAN_VS_*, 0x03C ES_CONTROL and ES_PRESCALE), keeping every other bit of those words, polls es_control_status (0x253) "
          "for the END state, reads es_error_count (0x251) and es_sample_count (0x252), and clears the run bit; it does NOT restore the horizontal offset, the vertical word or the "
          "prescale it wrote: the host saves and restores them (flow/eyescan/hw.py). The static eye-scan attributes (ES_QUALIFIER, ES_QUAL_MASK, ES_SDATA_MASK) are written by the "
          "host with raw accesses. ES_EYE_SCAN_EN and ES_ERRDET_EN are set in the bitstream (es.xdc), not through the DRP. A DRP read has no side effect on the GT; a DRP write "
          "changes the attribute at once. In a build without EYESCAN the registers 0x024 to 0x03C and 0x084 read 0 and ignore writes, and the GT's DRP port and drive ports are "
          "tied to the constants the design always used.", "",
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
