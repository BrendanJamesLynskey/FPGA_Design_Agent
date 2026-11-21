"""The ITCH path's registers (brief 127, build rm_gp_itch) as data: `python3 designs/b96_kr260_10g/rm_gp_itch/regmap_itch.py --write` regenerates docs/register_map.md of the variant.

The variant keeps every register of designs/b96_kr260_10g/regmap.py (same addresses, same meaning) and adds FEATURES bit 7, the configuration window 0x300 to 0x37C and the
counter window 0x400 to 0x57C. The layout of the two vectors (word index = (address - base) / 4) is rtl/itch_pkg2.sv; tests/test_b127_regmap.py checks the two agree.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2]))
from designs.b96_kr260_10g import regmap as base        # noqa: E402

CFG_BASE, STAT_BASE = 0x300, 0x400
#: (word index, name, access, reset, description); the address is CFG_BASE + 4 * index
CFG = [
    (0, "IT_CTRL", "RW", "0x00000010", "bit 0 EN (the adapter forwards matching UDP frames to the Mold receiver; 0: every frame is dropped and counted `drop_off`), bit 1 ARM (orders may be sent), bit 2 KILL (blocks every order; counted `rej_kill`), bit 3 SPEC (start the order frame when the candidate is seen, before the risk verdict; the frame is poisoned if the verdict is a refusal), bit 4 HALT_ON_GAP (refuse orders while a sequence gap is flagged; reset 1), bit 5 STRICT (poison every order whose trigger frame's FCS verdict was not known and good by the order's last word; reset 0 = cut-through). Reserved bits read 0."),
    (1, "IT_THR", "RW", "1000000", "Candidate rule: a new SELL order (ITCH Add or Add with MPID) of a watched instrument at or below this price (Price(4): 1000000 is 100.0000) is a candidate to buy at that price."),
    (2, "IT_QTY", "RW", "100", "Quantity of the order sent."),
    (3, "IT_MAXQTY", "RW", "500", "Risk: largest quantity (also: zero and 1,000,000 or more are refused)."),
    (4, "IT_MAXPOS", "RW", "1000", "Risk: largest position (quantity SENT per instrument since IT_CMD CLR_POS; no fills are processed)."),
    (5, "IT_BAND", "RW", "20000", "Risk: an order price may be at most this far (Price(4)) above the best bid; with no bid the candidate is refused."),
    (6, "IT_PXOFF", "RW", "0", "Added to the candidate's price to give the order price."),
    (7, "IT_MINQTY", "RW", "0", "OUCH MinQty option value."),
    (8, "IT_ORDF0", "RW", "0x4E505933", "OUCH order fields, ASCII: bits 7:0 time in force (reset '3'), 15:8 display (Y), 23:16 capacity (P), 31:24 intermarket sweep eligibility (N)."),
    (9, "IT_ORDF1", "RW", "0x00004E4E", "bits 7:0 cross type (N), 15:8 customer type (N); bits 31:16 reserved (read 0)."),
] + [(10 + 2 * i + h, f"IT_WATCH{i}_{'HI' if h else 'LO'}", "RW", ("0x%08X" % (0x20202020 if not h else 0x41414120 + 0x01010100 * i)),
      f"Watched symbol {i}: 8 ASCII characters, space padded, first character in bits 31:24 of the _HI word.") for i in range(4) for h in (0, 1)] + [
    (18, "IT_FEED_IP", "RW", "0xC0A83A0A", "Destination IPv4 address the feed is sent to (first octet in bits 31:24). A 224.0.0.0/4 address selects the multicast MAC 01:00:5E:xx:xx:xx of the group as the accepted destination MAC; any other address needs the destination MAC to be MY_MAC."),
    (19, "IT_FEED_PORT", "RW", "5810", "UDP destination port of the feed (bits 15:0; bits 31:16 read 0)."),
    (20, "IT_TCP_SEQ", "RW", "1", "TCP sequence number of the next order segment; takes effect on IT_CMD TCP_LOAD, then advances by 59 for every segment that left unpoisoned. Stand-in header only (see docs/itch_integration.md section 8)."),
    (21, "IT_TCP_ACK", "RW", "1", "TCP acknowledgement number in every order segment (stand-in header)."),
    (22, "IT_CMD", "W", "0", "Commands, bits executed ONCE per write (several bits together are fine): 0 CLR_CNT (every counter of STAT2 except the timestamps; also the latency statistics), 1 CLR_FLAGS (gap, untrusted, end of session, session lock, expected sequence number), 2 CLR_BOOK (book and order table; the book is ready again some 300 clocks later), 3 CLR_POS (position per instrument), 4 CLR_REF (order reference counter back to 1), 5 RP_START (play the replay memory from word 0), 6 TCP_LOAD (IT_TCP_SEQ becomes the next sequence number), 7 LAT_CLR (latency statistics only), 8 CAP_CLR (forget the captured frames), 9 RP_STOP (stop the replay). Writes closer than 1 microsecond may lose a command (the register crosses to the core clock as one coherent vector). A READ returns the number of commands written so far in bits 23:16 (a counter that wraps at 256); IT_STAT word S_CMD_ECHO shows how many the core executed."),
    (23, "RP_WADDR", "RW", "0", "Replay memory word address of the next write (bits 7:0, 256 words)."),
    (24, "RP_WLO", "RW", "0", "Low 32 bits of the next replay word (staged, no effect until RP_WHI is written)."),
    (25, "RP_WHI", "RW", "0", "High 32 bits of the replay word; WRITING it commits {RP_WHI, RP_WLO} to the memory at RP_WADDR (once). The address does NOT auto-increment. A read returns the last value written; bits 23:16 of RP_WADDR's read show the number of commits. Wait until IT_STAT RP_STAT bits 7:0 equal that count (or 1 microsecond) before the next commit."),
    (26, "CAP_ADDR", "RW", "0", "Capture read address: bits 6:4 slot (0 to 7), bits 3:0 entry: 0 to 11 are words 3 to 14 of a captured TCP frame (bytes 24 to 119: IP checksum, addresses, TCP header, payload, FCS), 12 is the slot's meta word {bit 17 valid, bit 16 FCS good, bits 15:0 frame length with FCS}, 13 to 15 read 0. The data appears in the counter window (CAP_LO, CAP_HI) after the next snapshot; CAP_ECHO shows the address it belongs to."),
    (27, "TCPF_ADDR", "RW", "0", "Software bus of brief 119's tcp_fast (only meaningful when that block replaces order_seg; reads 0 in this build): bits 4:0 write address, bits 12:8 read address; a read returns the count of TCPF_WDATA writes in bits 23:16."),
    (28, "TCPF_WDATA", "RW", "0", "Writing it commits {data} to the tcp_fast register at TCPF_ADDR[4:0] (once). Stand-in build: no effect."),
    (29, "RP_CFG", "RW", "0", "bits 15:0 passes over the replay memory per IT_CMD RP_START (0 or 1: one pass). At the end of a pass the replay waits the `gap` field of the end-marker header word, then starts again from word 0; bits 31:16 reserved (read 0)."),
]
STAT_NAMES = (
    ["itch.pkt", "itch.msg", "itch.gap", "itch.missing", "itch.dup", "itch.ovlp", "itch.sess", "itch.hb", "itch.eos", "itch.short", "itch.trunc", "itch.badlen", "itch.pkt_err",
     "itch.m_a", "itch.m_f", "itch.m_e", "itch.m_c", "itch.m_x", "itch.m_d", "itch.m_u", "itch.m_s", "itch.m_r", "itch.m_skip", "itch.m_bad", "itch.unwatch", "itch.omiss", "itch.odup",
     "itch.oovf", "itch.lvovf", "itch.lvmiss", "itch.oover", "itch.evdrop", "itch.cand", "itch.fire", "itch.rej_arm", "itch.rej_kill", "itch.rej_gap", "itch.rej_stale", "itch.rej_size",
     "itch.rej_pos", "itch.rej_band", "itch.rej_busy", "itch.abort", "itch.late_abort", "itch.spec"]
    + ["us.frames", "us.fwd", "us.drop_off", "us.drop_mac", "us.drop_type", "us.drop_frag", "us.drop_proto", "us.drop_dip", "us.drop_port", "us.drop_len", "us.drop_ipck",
       "us.bad_fcs", "us.cut", "us.orphan", "us.cap_n"]
    + ["ord.sent", "ord.pz_abort", "ord.pz_bad", "ord.pz_strict", "ord.unverified", "ord.drop", "ord.fifo_ofl", "ord.pz_unres", "ord.late",
       "rp.frames", "rp.stat", "lat.last", "lat.min", "lat.max", "lat.count", "lat.neg"]
    + [f"lat.hist{2 * i}_{2 * i + 1}" for i in range(8)]
    + ["ts.eof", "ts.go", "ts.sop", "ts.rxsop", "flags", "cap.lo", "cap.hi", "cap.echo", "tcpf.rdata", "tcpf.echo", "cmd.echo", "ord.refused"])
assert len(STAT_NAMES) == 96

STAT_DOC = {
    "ord.sent": "order frames that left with a good FCS (the unverified ones below are included)",
    "ord.pz_abort": "order frames poisoned because risk refused the candidate or the book did not confirm it (abort) before the frame's last word",
    "ord.pz_bad": "order frames poisoned because the trigger frame's FCS was bad (or any frame's was while this one was in flight)",
    "ord.pz_strict": "order frames poisoned in STRICT mode because the trigger frame's verdict was not known by the last word",
    "ord.unverified": "order frames that left with a good FCS while the trigger frame's verdict was still missing (the cut-through risk window; subset of ord.sent)",
    "ord.drop": "order frames dropped whole because the MAC was owned by the generator or the replay when the first word arrived (already fired and counted by the risk logic)",
    "ord.fifo_ofl": "order FIFO overflows and watchdog releases (never seen)",
    "ord.pz_unres": "order frames poisoned because a speculative frame had no risk verdict by its last word",
    "ord.late": "aborts that found no order frame in flight",
    "rp.frames": "replay frames sent", "rp.stat": "bits 7:0 replay writes committed and executed; bit 8 replay busy; bits 31:16 replay frames skipped for a bad length (rp_err)",
    "lat.last": "last order latency in clocks: MAC start strobe of the order frame minus the clock of the last payload word at the Mold receiver's input (s_eof of udp_strip); negative when the order started before its packet ended",
    "lat.min": "smallest non-negative latency since the clear", "lat.max": "largest", "lat.count": "orders measured", "lat.neg": "orders that started before their packet ended",
    "ts.eof": "core-clock stamp of the last packet end at the Mold receiver's input", "ts.go": "stamp of the last order `go`", "ts.sop": "stamp of the last order's MAC start strobe",
    "ts.rxsop": "stamp of the last received frame's start (the RX start strobe, as TXV13 to TXV15 of the base map)",
    "flags": "bits 15:0 flags of brief 110 (0 gap seen, 1 untrusted, 2 end of session, 3 session locked, 4 book ready, 5 order path busy, 8 to 11 instrument inexact), bit 16 replay busy, bit 17 order frame holds the MAC, bit 18 order in flight (poison tracker), bit 19 EN",
    "cap.lo": "low half of the capture word at CAP_ADDR", "cap.hi": "high half", "cap.echo": "the CAP_ADDR the two words belong to (compare with what you wrote)",
    "tcpf.rdata": "tcp_fast software read data (0 in this build)", "tcpf.echo": "TCPF_WDATA writes executed", "cmd.echo": "IT_CMD writes executed",
    "ord.refused": "orders the segment builder refused before making a word (0 in this stand-in; tcp_fast: not armed, stale state, closed window, MSS)",
}
HIST_DOC = "latency histogram: 16-bit saturating counters, bin n = latency n clocks (bin 15 = 15 or more), two bins a word: the low half is the even bin"
US_DOC = {
    "us.frames": "frames started (start blocks seen by the MAC)", "us.fwd": "frames forwarded to the Mold receiver",
    "us.drop_off": "frames dropped because IT_CTRL.EN is 0", "us.drop_mac": "dropped: destination MAC", "us.drop_type": "dropped: not IPv4 with header length 5 (EtherType, version, IHL)",
    "us.drop_frag": "dropped: fragmented (MF or offset)", "us.drop_proto": "dropped: protocol not UDP", "us.drop_dip": "dropped: destination address", "us.drop_port": "dropped: UDP port",
    "us.drop_len": "dropped: UDP length under 9 or IP total length not UDP length + 20", "us.drop_ipck": "dropped: IPv4 header checksum",
    "us.bad_fcs": "forwarded frames whose FCS was bad or that were shorter than their IP length (their payload was already delivered; see itch.pkt_err)",
    "us.cut": "forwarded frames cut by an error character or a lost block lock", "us.orphan": "verdicts that matched no frame (never seen)", "us.cap_n": "TCP frames captured (the ring keeps the last 8)",
}


def render() -> str:
    o = [base.render().replace("# kr260_10g register map (generated by regmap.py; do not edit)", "# kr260_10g register map, build rm_gp_itch (brief 127; generated by rm_gp_itch/regmap_itch.py; do not edit)", 1), "",
         "## Added by build rm_gp_itch (brief 127)", "",
         "Everything above is the register map of the base design, unchanged, with two differences: **FEATURES bit 7** reads 1 (the ITCH path is built in), and this build has "
         "RATE_MATCH = 1 always (the ITCH path runs in the transmit clock behind the elastic buffer), no eye scan (the 0x024 to 0x03C and 0x084 registers read 0) and no GT bypass. "
         "CMD bit 2 (snapshot) also snapshots the counter window below.", "",
         "The two windows follow the same rules as the base map: **unmapped addresses** (0x378 to 0x37C and 0x578 to 0x5FC and everything else between) read 0 and ignore writes; **reserved bits** read 0 and "
         "are ignored on write; **reads have no side effects**; write-only effects are stated per register. The configuration registers cross to the core clock as ONE coherent 1024-bit vector "
         "(a few dozen clocks after a write, the same handshake as the base configuration), so **a write takes effect together with every earlier write**, never half of one.", "",
         "| Address | Name | Access | Reset | Description |", "|---|---|---|---|---|"]
    for i, n, acc, rst, d in CFG:
        o.append(f"| 0x{CFG_BASE + 4 * i:03X} | {n} | {acc} | {rst} | {d} |")
    o.append(f"| 0x378 to 0x37C | - | - | 0 | reserved: read 0, writes ignored. |")
    o.append(f"| 0x{STAT_BASE:03X} to 0x{STAT_BASE + 4 * 95:03X} | ISTAT0 to ISTAT95 | RO | 0 | Counter and status snapshot of the ITCH path, 96 words (table below), taken together with the base snapshot by CMD bit 2. All counters are 32 bit and clear with IT_CMD CLR_CNT. |")
    o += ["", "## ISTAT words (core clock domain, TXUSRCLK2)", "", "| Word | Address | Name | Content |", "|---|---|---|---|"]
    for i, n in enumerate(STAT_NAMES):
        d = STAT_DOC.get(n) or US_DOC.get(n) or ("counter of brief 110's ITCH path (docs of designs/b110_itch_ouch/docs/itch_ouch.md section 1)" if n.startswith("itch.") else HIST_DOC if n.startswith("lat.hist") else "")
        o.append(f"| ISTAT{i} | 0x{STAT_BASE + 4 * i:03X} | {n} | {d} |")
    o += ["", "## What clears what (ITCH path)", "",
          "- **IT_CMD CLR_CNT** clears every counter of ISTAT0 to ISTAT68 and the latency statistics; it does not clear the stamps, the flags, the replay counters (they restart with the replay), the capture ring or the book.",
          "- **A restart of the TX datapath** (GT_RESET bit 1, 3 or 0, or the transmit done level dropping) resets the whole ITCH path, including book, position, counters and the replay engine (the replay memory and the configuration registers keep their contents).",
          "- **Order reference numbers** start at 1 after reset or CLR_REF; the order number is assigned when a candidate passes the risk checks, so refused candidates use none.",
          "- **The capture ring** keeps the last 8 TCP frames (IPv4 protocol 6) the receiver saw, whatever their addresses; CAP_CLR forgets them.", ""]
    return "\n".join(o)


if __name__ == "__main__":
    out = HERE / "docs" / "register_map.md"
    if "--write" in sys.argv:
        out.write_text(render())
        print("wrote", out)
    else:
        print(render())
