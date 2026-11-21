# The software side of the TCP fast path

Brief 119 builds two things in Python besides the hardware: a **TCP owner** (the host's side of the connection that the fast path sends on) and a
**software exchange** (an OUCH/SoupBinTCP server to test against). Both are in [model/softtcp.py](../model/softtcp.py), with the packet layouts in
[model/soup.py](../model/soup.py), the segment and checksum reference in [model/tcpref.py](../model/tcpref.py), and an untimed stand-in for the block in
[model/hwmodel.py](../model/hwmodel.py). They run in the pure-Python tests (`tests/test_b119_model.py`) against the stand-in and in the cocotb bench against the
real block.

## Why an own TCP endpoint

The fast path writes into the same byte stream as the host's TCP stack. An operating system's stack cannot be told that another agent has used part of its
sequence space, so the connection is modelled honestly in user space: a minimal TCP endpoint that is used for both ends. (Whether a kernel socket can be
made to cooperate, for example by setting its sequence number from outside, was not tried and is not claimed: UNCONFIRMED.)

`Endpoint` implements: active and passive open with the MSS option, cumulative acknowledgements, out-of-order reassembly (a segment past `RCV.NXT` is held
and the gap is acknowledged repeatedly), a retransmission timer with back-off (oldest unacknowledged segment first), checksum verification on receive (a
frame with a bad IP or TCP checksum is dropped and counted), the connection check on addresses and ports, and RFC 793's acceptability rule for ACK-only
segments (a pure ACK whose sequence number is behind `RCV.NXT` is dropped, unanswered, so two endpoints cannot ping-pong).

Not implemented, so not claimed: congestion control, selective acknowledgement, delayed ACKs, window scaling, timestamps, FIN and orderly close, zero-window
probes, IP fragmentation and options, keep-alive. Time is a number of ticks (clocks in the bench); the retransmission timeout and the heartbeat interval are
given in ticks and are scaled down from a second.

## The owner

`Owner` is `Endpoint` plus the hand-over to the block. Its life cycle:

1. `connect`: SYN with the MSS option, SYN-ACK, ACK (all by software, through its own transmit path).
2. Login: a Login Request (`L`) as ordinary data; wait for Login Accepted (`A`) or Login Rejected (`J`). A rejected login stops the session before the block is armed.
3. `handoff`: write the connection's static fields, SND_NXT, IP_ID, STALE_LIMIT, then the live fields, then arm and wait for the valid bit.
4. While armed, `service` (called once a tick) does everything the contract of [section 3 of the datasheet](tcp_fast.md) asks:
   - absorbs the block's records into its bookkeeping (an unexpected sequence number raises an error: the sequence space is corrupted);
   - processes frames from the peer and, if SND_UNA, SND_WND, RCV_NXT or RCV_WND changed, writes the live registers;
   - sends pure ACKs for received data with the sequence number read from the block when it is idle;
   - rewrites a live register at half the stale limit so the block's age counter does not run out;
   - retransmits the oldest unacknowledged segment from its record when the timer expires (software's own headers; SND_NXT does not move);
   - sends a Client Heartbeat (`R`) when nothing has been sent for the heartbeat interval: `take` (disarm, wait for idle, absorb the last record, compare SND_NXT with the block's), send, `give` (write SND_NXT, refresh, rearm).
5. The records and software's own sends go into one log (`sent_log`), which the tests use to check that the sequence space is gapless across both senders.

## The exchange

`Exchange` is a passive `Endpoint` with a SoupBinTCP 3.00 server and an OUCH 5.0 handler. It accepts a Login Request with a known user and password
(Login Accepted with the session and next sequence number, or Login Rejected `A` for a bad one), handles Unsequenced Data, Client Heartbeat and Logout
Request, and sends a Server Heartbeat when silent for the heartbeat interval. For an Enter Order it replies with a Sequenced Data packet carrying:
- an **Order Accepted** (`A`, 64 bytes, OUCH 5.0 section 3.2) echoing the order, with order state Live and a day-unique order reference; or
- an **Order Rejected** (`J`, 31 bytes, section 3.8) with a reason from Appendix C: 0x0013 invalid quantity (zero or one million and over), 0x0017 invalid symbol (not in its list), 0x001D invalid price (zero), 0x0006 fat finger (quantity above its limit).

A UserRefNum not above the last processed is ignored and counted, as OUCH 5.0 section 1.2 says ("assuming they are retransmissions"). The layouts were read from the
Nasdaq documents for this brief; the fields the exchange fills with invented values (timestamp, order reference) are not meaningful, and no behaviour of any real
port beyond the documents is claimed.

## Network model

`World` delivers frames after a fixed latency in ticks with a drop hook (`drop(frame, destination, index)`), so a test can lose one specific segment. The
bench forwards every unpoisoned frame the block emits to the exchange and drops a poisoned one, as the receiver's MAC would.

## What the tests show

See [tcp_fast.md](tcp_fast.md) and the README: byte-exact segments against the reference, abort at every offset, refusal paths, register semantics, a dropped
fast-path segment retransmitted by software from the record, heartbeats that take and give back the sequence space, and a mixed run through login, orders,
acknowledgements and replies against the exchange.
