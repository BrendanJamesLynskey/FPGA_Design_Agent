# TCP plan: carrying the OUCH frame to an exchange port (phase 2 and after)

Phase 1 stops at the 64-bit frame on `o_*` ([itch_ouch.md](itch_ouch.md)). OUCH is carried by SoupBinTCP 3.00, which is carried by TCP
([spec_notes.md](spec_notes.md) section 4): a real order needs a TCP connection, a SoupBinTCP login, client heartbeats, and handling of the
sequenced responses. This page compares the ways to get there, with the trade-offs, and says what phase 2 would build. **It is a plan, not a
measurement**: nothing below was built or timed, and statements about other products are recalled, not verified (marked UNCONFIRMED).

## What the order path needs from TCP

1. A connection set up and kept up by something (three-way handshake, window, retransmission, keep-alive, orderly close).
2. For each order: a segment with the right Ethernet, IPv4 and TCP headers: sequence number (the byte count sent so far), acknowledgement
   number and window as last seen, IP total length, IP header checksum, TCP checksum over the pseudo-header, headers and payload.
3. To know the segment arrived: the peer's acknowledgements, and a retransmission of the segment if they do not come.
4. SoupBinTCP on top: Login Request first, Client Heartbeat after one second of silence, Sequenced Data in (OUCH responses: accepted, rejected,
   executed), all in the same byte stream as the orders, so **any segment sent by a second agent moves the same sequence number**.

Only the first of the per-order items is time critical, and for one order of 59 bytes it is **one segment**: 54 bytes of headers (Ethernet 14, IPv4 20,
TCP 20, no options) in front of the 59-byte frame, 113 bytes on the wire without the FCS.

## Options

| | A. Software TCP, hardware fast path for pre-built segments | B. TCP offload engine in the fabric | C. Licensed TCP core | D. Minimal one-connection TCP written for the job |
|---|---|---|---|---|
| Who owns the connection | the processing system (Linux TCP on the K26's Arm cores, or a user-space stack) | the fabric | the fabric (vendor core) | the fabric |
| Order latency | header and payload leave from the fabric: close to the fabric's own latency; the PS is out of the path | the same | the same, plus the core's internal pipeline (vendor figures, UNCONFIRMED) | the same |
| Slow path (login, heartbeat, retransmit, close) | PS, the full TCP stack | engine | core | very restricted: a retransmit timer and a reset only |
| Fabric to build | segment template memory; sequence, acknowledgement and window tracking; incremental checksums; a way to tell the PS what was sent | the whole of TCP: state machine, timers, retransmit buffer, receive reassembly, window and congestion control | integration only | state machine, one retransmit buffer, receive of ACKs only |
| Verification effort | moderate: tracking and checksums against a software model and captures | very large (corner cases of the protocol) | small plus licence terms | moderate to large |
| Resources | small | large (buffers for retransmission and reassembly) | medium to large | small to medium |
| Cost and risk | PS and fabric must agree on the sequence space; a bug here corrupts the stream | the highest development risk | licence cost, closed source, may not run at 161 MHz on this part, a vendor lock | interoperability with an exchange's stack is the risk (it must behave like TCP) |
| Fit to a long-lived connection with small messages | the usual structure of low-latency order entry (a software stack for the connection, a bypass for the sends; the Onload "delegated send" interface and similar ones work this way: UNCONFIRMED) | overkill for one or two connections | fits, if the evaluation licence allows a simulation and a bench build | possible, but then every TCP feature that is left out is a latent failure |

Known open implementations of a fabric TCP stack exist (for example an HLS stack from a university group aimed at 10G; its licence, current
state and fit to this part were **not checked**: UNCONFIRMED). The AMD/Xilinx catalogue lists TCP/IP offload cores as licensed products
(UNCONFIRMED which, and whether any is available for the K26).

## Recommendation: A for phase 2

Software TCP on the processing system with a hardware fast path for pre-built segments. Reasons: there is one long-lived connection with small
messages (the case this structure fits); the PS stack already does everything slow (handshake, retransmission, login, heartbeats) and is the
mature part; the fabric does what it is good at (a fixed-latency send of a known frame); verification can be done against Linux's own TCP with
captures; and it reuses what is built (the frame, the abort, the stub port). A full offload engine (B) or a licensed core (C) would be the answer
to a different question (many connections, or no PS in the path); D is a trap: the risk is not the sends, it is the cases left out.

## What phase 2 would build for A

1. **A way to take over the sequence space.** The PS opens the connection, logs in (SoupBinTCP `L`), reads Login Accepted, then hands the fabric
   the connection's addressing (MACs, IPs, ports), the next sequence number, the last acknowledgement number and the peer's window, and the
   current IP identification. While the fabric owns the send side, the PS must not send on the connection except through the fabric
   (a ring in shared memory, the fabric sends and returns an acknowledgement of the send).
2. **A segment template** in block RAM: the 54 header bytes with the fields that never change filled in (addresses, ports, flags PSH+ACK, TTL,
   DF) and the partial checksums of those fields precomputed by the PS.
3. **The send engine.** For each order it forms: sequence number (previous plus the payload length), IP total length (fixed: 113), the IP header
   checksum and the TCP checksum, by adding the changed 16-bit words to the precomputed partial sums (one's-complement arithmetic, end-around
   carry). The payload's contribution is computed from the order's fields (reference, quantity, symbol, price), which are known at the moment the
   candidate is seen, in a few clocks with a small adder tree; the header is 6.75 words long, so the checksum field (wire offset 50) has to be ready
   by the seventh word: **the arithmetic fits inside the header's own transmission time**, and the frame can leave before the risk verdict in the way
   `ouch_enter` already does. This is a claim about timing to be measured in phase 2, not a result.
4. **Acknowledgement tracking.** A receive-side parser for the segments of the connection: update the last acknowledged byte and the window, and
   refuse to send when the window would be exceeded (a counted refusal). The PS sees the same segments (the fabric mirrors them) so that its stack
   stays consistent; a retransmission, if one is needed, is done by the PS from the ring, never by the fast path.
5. **Poisoning.** A frame cancelled by `o_abort` must not reach the peer: the MAC's poisoned-FCS request (`s_poison` of `mac64_tx`) makes the
   receiver's MAC drop it, so the sequence number is **not** consumed (the fast path restores the pre-send value; the PS never learns of it).
   The bench must show the peer's TCP state unchanged after an aborted frame. This is why the order number is assigned at commit.
6. **The SoupBinTCP layer stays in software** for phase 2: login, heartbeats (one per second when the fast path was silent), logout, and the
   decoding of Sequenced Data (responses). The order frame's own fields (the OUCH `UserRefNum` and the ClOrdID) need no software.
7. **Tests.** A software exchange on the host PC: a TCP server that accepts the login, checks each Unsequenced Data packet against the model's
   frame, replies with Accepted, and records the arrival time; scapy or `tcpdump` captures compared with the template's checksums for every
   order; fault injection (a dropped ACK, a zero window, a reset, an aborted frame); then the same on the board bench with the board's own
   timestamps.

## What this plan does not settle

- Whether any real exchange port accepts a connection from this design: that is a matter of the exchange's certification and agreements, and
  no order is ever sent to one here.
- The latency of the PS-side steps (login, retransmission): they are off the critical path by construction.
- Whether a fabric TCP stack (B or C) would be better once several connections are needed.
