# REVIEW (agent) ipv4_udp_tx id=ipv4_udp_tx schema=1 design_sha=1b322337aa42 mode=review (read-only)
top: formal_udp_tx; clocks: clk; scope: rtl
checks: lint=fail, standards=fail, resets=not_run, methodology=not_run, axi=pass | not run: resets, methodology
summary: ipv4_udp_tx is a store-and-forward UDP/IPv4/Ethernet transmitter. It accepts one byte-wide AXI-Stream payload into a RAM (block or LUT RAM), sums the payload as 16-bit words while it arrives, and drops anything longer than MAX_PAYLOAD (ev_too_long). A single-cycle S_CALC state computes the IPv4 header checksum and the UDP checksum (an all-zero result is sent as 0xFFFF; CSUM=0 sends 0). The 42 head

FINDINGS id | sev | cat | where | conf | src | title | fix
F-328efe | minor | documentation | README.md:66 | high | judge | Variant table claims II=1 although only one datagram is handled at a time | Describe II as per byte, or state the per-datagram interval as n + 45 clocks (payload in, calc, frame out).
F-c8022f | minor | verification | formal/formal_udp_tx.sv:19 | medium | judge | Verification gaps: formal covers only lutram at depth 4; edge cases not exercised | Add MAX_PAYLOAD=1 and a power-of-two depth point to the bench. Add a reset-mid-frame test. Run the formal wrapper for both RAM values and add a checksum asserti
F-36788b | minor | functional | rtl/ipv4_udp_tx.sv:41 | medium | both | RAM address width exceeds memory depth; header-phase reads are out of range | Use a depth of 2**AW, or gate rd_en with j >= 42 so no out-of-range read occurs. Size AW as $clog2(MAX_PAYLOAD) with a minimum of 1.
F-cd020d | minor | functional | rtl/ipv4_udp_tx.sv:128 | medium | judge | own_mac / own_ip are used live, not captured per datagram | Either latch own_mac and own_ip at the same time as the other header fields, or document that they must be static while the block is busy.
F-951980 | minor | timing | rtl/ipv4_udp_tx.sv:153 | high | judge | Checksum and critical path: both sums are computed in one cycle (documented limit) | Split the sum into two or three registered stages inside S_CALC, then update the latency figure and the bench's LATENCY constant.
F-8dc109 | minor | tb-defect | tb/udp_tx_cocotb.py:31 | medium | judge | Bench silently skips the independent scapy check when scapy is absent | Fail, or at least log a prominent warning and mark the test as degraded, when scapy is missing in CI.

QUESTIONS
- Is own_mac/own_ip guaranteed static while the block is busy (the ARP/MAC integration)?
- Is s_dst_* guaranteed valid on the first beat only, or does the caller hold it for the whole payload?

TEST GAPS
- MAX_PAYLOAD=1 and power-of-two depths in the bench
- Reset during a frame or during S_CALC
- Identification wrap at 65536 datagrams
- Config (own_ip/own_mac) changing mid-frame
- Formal for the bram variant; no formal on checksum values
- Sustained long runs; scapy check silently skipped if scapy is missing

RULES: this review did not edit the design; fixes are separate, opt-in work. Re-run the checks after any change.