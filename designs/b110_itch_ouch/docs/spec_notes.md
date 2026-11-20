# Specification notes: what the RTL implements, and where each field comes from

The four public Nasdaq documents below were downloaded on 2026-11-20 from `nasdaqtrader.com` and read; the PDFs are **not** committed
(the repository holds field layouts in our own words, each with the document and section it comes from). A fact that was read in the
document is stated plainly. A fact that is recalled, or assumed because the document is silent, is marked **UNCONFIRMED**.

| Protocol | Version read | Revision marker in the document | Used for |
|---|---|---|---|
| Nasdaq TotalView-ITCH | 5.0 | last revision entry 28 April 2023 | the market-data messages |
| MoldUDP64 | V 1.00 | last version-control entry 8/2/24 | the transport of ITCH messages in UDP |
| OUCH | 5.0 | "Updated October, 2025", revision 1.05 (10/7/2025) | the order-entry message |
| SoupBinTCP | Version 3.00 (the brief said 4.0: the public document is 3.00) | last revision entry 02/22/2017 | the framing of OUCH on TCP |

## 1. MoldUDP64 V 1.00 (hardware: `rtl/mold_rx.sv`)

| Field | Offset | Length | Section | Hardware |
|---|---|---|---|---|
| Session | 0 | 10 | "Downstream Packet Header" | locked on the first accepted packet; another session is dropped and counted (`sess`) |
| Sequence Number | 10 | 8 | same | the first message's number; the next messages are implied (+1 each) |
| Message Count | 18 | 2 | same | 0 is a heartbeat, 0xFFFF an end of session (read in "Message Count"); neither carries blocks |
| Message Length | block start | 2 | "Message Block" | the number of bytes after the field; the block is length plus 2 |
| Message Data | block start + 2 | length | same | the ITCH message |

Read in the document: all numbers are big endian; the first block starts at byte 20; a heartbeat "contains the next expected Sequence
Number" (section "Heartbeats"), as does an end-of-session packet; a message of zero bytes is legal in the protocol ("can be zero length").
The receiver flow chart in "Receiver Example" aborts on a session mismatch (step 3) and sends a request on a gap (step 5).
- The hardware **does not send** the request (phase 1: counted and flagged only; the request packet of "Request Packet" is not built).
- A block shorter than 12 bytes is not an ITCH 5.0 message (the shortest, System Event and Market-Wide Circuit Breaker Status, are 12 bytes
  in the ITCH document) and the hardware refuses it (`badlen`): this is **our rule**, not the protocol's. The Mold document allows shorter blocks.
- Sequence arithmetic is exact for 64 bits in the comparison and for 32 bits in the overlap distance (**our simplification**: a distance of
  2^32 messages or more is a duplicate or a gap, never an overlap).

## 2. Nasdaq TotalView-ITCH 5.0 (hardware: `rtl/itch_dec.sv`)

All integers are big endian; alpha fields are left justified and space padded; Price(4) has four implied decimals (section "Data Types").
Every message starts with the type (offset 0, 1 byte), Stock Locate (1, 2 bytes), Tracking Number (3, 2 bytes), Timestamp (5, 6 bytes; the
hardware does not use the tracking number or the timestamp).

| Type | Message | Section | Length | Fields the hardware uses (offset, bytes) |
|---|---|---|---|---|
| S | System Event | 1.1 | 12 | event code (11, 1); stored, nothing else is done |
| R | Stock Directory | 1.2.1 | 39 (last field Inverse Indicator at 38) | stock (11, 8) matched against the watch list; the locate maps to the instrument |
| A | Add Order, no MPID | 1.3.1 | 36 | order reference (11, 8), buy/sell (19, 1), shares (20, 4), stock (24, 8), price (32, 4) |
| F | Add Order with MPID | 1.3.2 | 40 | as A; the attribution (36, 4) is not kept |
| E | Order Executed | 1.4.1 | 31 | order reference (11, 8), executed shares (19, 4); match number (23, 8) not used |
| C | Order Executed With Price | 1.4.2 | 36 | order reference (11, 8), executed shares (19, 4); the execution price (32, 4) and the printable flag are not used |
| X | Order Cancel | 1.4.3 | 23 | order reference (11, 8), cancelled shares (19, 4) |
| D | Order Delete | 1.4.4 | 19 | order reference (11, 8) |
| U | Order Replace | 1.4.5 | 35 | original reference (11, 8), new reference (19, 8), shares (27, 4), price (31, 4) |

Read in the document: the lengths follow from the offsets in the tables (computed from each table's last field, and the hardware checks the
Mold length against them); "executions ... are cumulative" and an order "reaches zero ... is dead" (section 1.4); a Replace keeps the side,
stock and attribution of the original (section 1.4.5); the Stock Locate is "a low lying integer ... array index" assigned in the Stock
Directory and stable for the day (introduction), and it is `0` in messages that are not stock dependent (section 1.1).
- E, C, X reduce the order's displayed shares; C's different execution price does not change the displayed price of the order: our reading
  of "executed ... at a price different from the initial display price" (section 1.4.2). This matches the cumulative rule of 1.4, and is
  **UNCONFIRMED** against Nasdaq's own book-building guidance, which the document does not give.
- Messages of every other type (H, Y, L, V, W, K, J, h, P, Q, B, I, N, O and any later addition) are skipped by their Mold length (`m_skip`).
- Only the first 36 bytes of a message are kept (our choice: the longest field used ends at 36).
- Hardware validity rules that are **ours**: a known type with another length, a side letter other than B or S, and a zero share count
  in A, F, E, C, X, U are counted as malformed (`m_bad`) and dropped.

## 3. OUCH 5.0 (hardware: `rtl/ouch_enter.sv`), section 2.1 Type O Enter Order

| Field | Offset | Length | Value in the hardware |
|---|---|---|---|
| Type | 0 | 1 | `O` |
| UserRefNum | 1 | 4 | order number, 1, 2, ... (day unique and strictly increasing, "Data Types") |
| Side | 5 | 1 | `B` (buy; the rule only buys) |
| Quantity | 6 | 4 | `cfg_qty`; "greater than zero and less than 1,000,000" (the risk check enforces it) |
| Symbol | 10 | 8 | the watch-list symbol, left justified, space padded |
| Price | 18 | **8** | the order price, Price(4) in an 8 byte field (see below) |
| Time In Force | 26 | 1 | `cfg_tif` (default `3` = IOC) |
| Display | 27 | 1 | `cfg_display` (default `Y`) |
| Capacity | 28 | 1 | `cfg_capacity` (default `P`) |
| InterMarket Sweep Eligibility | 29 | 1 | `cfg_ise` (default `N`) |
| CrossType | 30 | 1 | `cfg_cross` (default `N`, continuous market) |
| ClOrdID | 31 | 14 | `FDA110` then the order number as eight upper-case hex digits |
| Appendage Length | 45 | 2 | 9 |
| Optional Appendage | 47 | 9 | TagValue MinQty (tag 3, 4 bytes) then TagValue CustomerType (tag 4, 1 byte) |

Read in the document: the fixed part is 47 bytes; **the price is an 8 byte field in this revision** (the table in 2.1 gives offset 18, length 8;
the "Data Types" section gives the maximum price as $199,999.9900 = 0x7735939C, which fits 4 bytes: earlier OUCH 5.0 documents used 4 bytes;
the revision list of this document does not say when the field grew, so **UNCONFIRMED** which revision changed it and whether older ports expect 4 bytes);
the brief's field list named a "token": OUCH 4.2 had a 14-byte order token; **5.0 has UserRefNum instead** (section 2.1);
options go in the appendage as TagValue elements: Length (1), OptionTag (1), OptionValue ("Data Types"); the option tags are in Appendix A
(the document points to "Appendix B" for them: a document inconsistency, noted).
- **UNCONFIRMED:** whether a TagValue's Length counts the tag byte (we assume it does, "remaining length of the TagValue element" after the
  length byte: MinQty is then 1 + 4 = 5, CustomerType 1 + 1 = 2, giving the 9 byte appendage).
- MinQty is sent as 0 by default ("no minimum", Appendix A default); a non-zero value "must be a round lot". CustomerType `N` is "not retail
  designated (default)".
- The "intermarket sweep" and "cross type" fields are set to the common values for a continuous-market limit order; whether the port accepts
  them depends on the participant's agreement with the exchange, which this repository does not have (no order is ever sent anywhere).

## 4. SoupBinTCP 3.00 (hardware: `rtl/ouch_enter.sv`), sections 1.1 and 2.3.2

An Unsequenced Data Packet is: Packet Length (2 bytes, "the length of the payload plus the length of the packet type - which is 1"), Packet
Type `U`, then the message. For the 56 byte Enter Order the length is 57 = 0x0039 and the packet is 59 bytes. Read in the document: logical
packets "may be broken apart or aggregated by the TCP/IP stack"; the client must send a Login Request (`L`) first and a Client Heartbeat
(`R`) after one second of silence; the server sends Login Accepted (`A`) with the session and the next sequence number; Sequenced Data
(`S`) carries the OUCH responses. **None of the login, heartbeat or response handling is built here** (docs/tcp_plan.md).

## 5. Where this repository's own choices differ from the documents

| Choice | Document says | Why |
|---|---|---|
| Blocks under 12 bytes refused | Mold allows any length | no ITCH 5.0 message is shorter; the framing logic relies on it |
| ClOrdID `FDA110` + hex | "alphanumeric and non-binary" | a reproducible value without a decimal converter |
| Position counts the quantity sent | the exchange tracks fills | OUCH responses are not processed in phase 1 |
| Replace does not trigger an order | n/a | the side of the replaced order is known one clock after the other triggers |
| Locate lookup by comparison | the locate is "an array index" | a few instruments only; a direct index would need 2^16 entries |
