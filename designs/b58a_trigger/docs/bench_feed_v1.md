# Bench Feed v1: a mock market-data and order format

Our own small binary format for a **mock trading path on a bench**. It is not any exchange's protocol and
carries no real market data. It is used only on a bench loop between our own board and our own PC program; there is no
real exchange, broker or data. The prices and sizes are stimulus values made by our own traffic sources (the mock venue
`host/mock_venue.py`, our own program, and `rtl/feed_gen.sv`).

Everything is big-endian. Prices are unsigned 32-bit numbers of hundredths (101.25 is 10125). One UDP datagram
carries one packet.

## Transport (the bench loop)

| Layer | Value |
|---|---|
| Ethernet II | destination: the board's address (locally administered, default `02:00:00:00:58:0a`); EtherType 0x0800. No VLAN tag. |
| IPv4 | version 4, IHL 5 (no options), not fragmented (MF 0, offset 0), protocol 17; header checksum checked by the board |
| UDP | destination port 5800 (default); the UDP checksum is not checked (the FCS covers the frame) |

The board also answers ARP requests for its own IPv4 address. Anything else is dropped and counted
(`docs/register_map.md`, counters).

## Packet

| Offset | Size | Field |
|---|---|---|
| 0 | 2 | magic 0x4246 |
| 2 | 1 | version 1 |
| 3 | 1 | message count N, 1..91 |
| 4 | 4 | sequence number of the first message; message k has sequence + k |
| 8 | 16 x N | messages |

The UDP payload must hold all N messages (8 + 16N bytes at least); bytes after the last message are ignored.
91 messages fill a 1500-byte IP datagram's room to 1492 bytes; a 1518-byte frame needs 8 more bytes after them.

## Market-data message (16 bytes)

| Offset | Size | Field |
|---|---|---|
| 0 | 1 | type: 1 ADD, 2 MODIFY, 3 CANCEL, 4 TRADE |
| 1 | 1 | side: 0 bid, 1 ask (bit 0) |
| 2 | 2 | instrument |
| 4 | 4 | price |
| 8 | 4 | size |
| 12 | 4 | reference (the mock venue's own number; not used by the board) |

The feed is a **top-of-book feed**: each message gives the best bid or the best ask of one instrument; there is no
deeper book.

| Type | Effect on that side's best level |
|---|---|
| ADD | becomes (price, size) |
| MODIFY | becomes (price, size); a price different from the current best is counted as a mismatch |
| CANCEL | removed: the side is empty (price 0, size 0) |
| TRADE | the last trade price becomes `price`; at the best price the size falls by `size` (the side empties at 0); at any other price, a mismatch |

The field order is chosen for the fast path: type, side and instrument arrive first (the book entry is read while
the price is still arriving), and the price is complete 8 bytes into the message, which is where the board decides.

## Sequence numbers

The board expects each packet's sequence to equal the previous good packet's sequence plus its count. A packet
that does not is a gap (counted). A frame that fails its FCS is discarded, so the next packet shows the gap, as a
lost packet would. With halt-on-gap set, a gap stops all orders until the host clears it.

## Orders (board to venue)

The board answers with the same packet layout, one message, sent to the venue's address and UDP port 5801
(defaults; the template is in registers):

| Offset | Size | Field |
|---|---|---|
| 0 | 1 | type: 0x10 NEW_ORDER, 0x11 CANCEL_ORDER |
| 1 | 1 | side: 0 buy, 1 sell |
| 2 | 2 | instrument |
| 4 | 4 | price |
| 8 | 4 | quantity |
| 12 | 4 | order id (1, 2, ... from reset) |

The packet header's sequence counts every order and cancel frame the board sends. A CANCEL_ORDER repeats the order
it cancels, with type 0x11. The response frame is 66 bytes plus the FCS: IPv4 with DF set, TTL 64, identification 0,
UDP checksum 0.

## Speculation

The board acts on a message before the frame's FCS has arrived. If the FCS then fails:

- an order still waiting to be sent is dropped;
- an order still on the wire has its FCS inverted, so the venue's network card discards it;
- an order already sent is followed by a CANCEL_ORDER.

An order whose frame is known to be bad before it starts is dropped. In safe mode the board sends nothing until the
FCS is good (this adds the rest of the frame plus the 4-byte FCS to the latency). A dropped, cancelled or poisoned
order still counts toward the position limit, so the limit is never understated.

## Where the design comes from

The format follows a general topic checklist, restated in our own words from a conference talk's list of topics:
message types, sequence numbers and gaps, instrument identifiers, a price representation, several messages in one
datagram. No exchange specification was read or copied; the layout, names and values are our own.
