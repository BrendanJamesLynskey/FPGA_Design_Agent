# ipv4_udp_tx: handover (produced by review)

> Produced by review `ipv4_udp_tx` on design content `1b322337aa42`. Nothing here was measured. Read `review.json` for the findings.

## What it does

ipv4_udp_tx is a store-and-forward UDP/IPv4/Ethernet transmitter. It accepts one byte-wide AXI-Stream payload into a RAM (block or LUT RAM), sums the payload as 16-bit words while it arrives, and drops anything longer than MAX_PAYLOAD (ev_too_long). A single-cycle S_CALC state computes the IPv4 header checksum and the UDP checksum (an all-zero result is sent as 0xFFFF; CSUM=0 sends 0). The 42 header bytes and the payload then go out through a two-stage read pipeline. I traced the length, checksum and handshake logic by hand and found no functional defect. The findings are minor: a live-config hazard, RAM address width, documentation and testbench weaknesses, and verification gaps.

## Interfaces

s_axis: 8-bit AXI-Stream slave, one payload per frame. s_axis_tready is high only in S_IN. s_dst_mac, s_dst_ip, s_src_port and s_dst_port are sampled with the first beat. m_axis: 8-bit AXI-Stream master carrying an Ethernet frame without FCS, 42 + n bytes, with registered tvalid, tdata and tlast. config: own_mac and own_ip are plain level inputs. events: ev_sent and ev_too_long are one-cycle pulses.

| Port | Direction | Width |
|---|---|---|
| `clk` | input | 1 |
| `s_axis_tdata` | input | [7:0] |
| `s_axis_tvalid` | input | 1 |
| `s_dst_mac` | input | [47:0] |
| `s_dst_ip` | input | [31:0] |
| `s_src_port` | input | [15:0] |
| `m_axis_tready` | input | 1 |

## Clocks and resets

One clock (clk) and one synchronous active-high reset (rst). There are no clock crossings and no asynchronous resets. Control state, counters, the checksum accumulator, the captured header fields and the output registers are reset. RAM contents and rq are not, which matches the house convention. rq is only consumed after a read that follows reset.

Clock domains found in the code: clk.

## Architecture

A three-state FSM: S_IN, S_CALC, S_OUT. In S_IN the payload is written at address n and p_acc accumulates the word sum, with the byte placed in the high or low half according to n[0]. In S_CALC the two checksums are computed in one cycle from wide adder chains. In S_OUT, j indexes frame bytes 0 to n+41. A read stage (rj, rv, rq) feeds the output register. rd_en = more && (take || !rv) keeps rq stable while the output is stalled. Bytes 0..41 come from hdr_byte and the rest from the RAM. The final output beat returns the FSM to S_IN and increments ident.

## Files

- rtl: `formal/formal_udp_tx.sv`, `rtl/ipv4_udp_tx.sv`
- tests: `tb/udp_tx_cocotb.py`
- constraints: none
- docs: `CHANGELOG.md`, `README.md`

## Open critical and major findings

- none

## Known gaps and limits

- no synthesis, implementation or timing result exists in this handover
- no simulation was run by the review; the tests' coverage is the reviewer's reading
- MAX_PAYLOAD=1 and power-of-two depths in the bench
- Reset during a frame or during S_CALC
- Identification wrap at 65536 datagrams
- Config (own_ip/own_mac) changing mid-frame
- Formal for the bram variant; no formal on checksum values
- Sustained long runs; scapy check silently skipped if scapy is missing

## Next steps

- fix the critical and major findings, then re-run the review and the check suite at scope synth after a build
- answer the open questions below

## Open questions

- Is own_mac/own_ip guaranteed static while the block is busy (the ARP/MAC integration)?
- Is s_dst_* guaranteed valid on the first beat only, or does the caller hold it for the whole payload?
