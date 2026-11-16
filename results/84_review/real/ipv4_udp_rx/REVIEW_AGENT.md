# REVIEW (agent) ipv4_udp_rx id=ipv4_udp_rx schema=1 design_sha=3da95ae853c9 mode=review (read-only)
top: formal_udp_rx; clocks: clk; scope: rtl
checks: lint=fail, standards=fail, resets=not_run, methodology=not_run, axi=pass | not run: resets, methodology
summary: ipv4_udp_rx is a byte-wide AXI-Stream IPv4/UDP receiver. It parses Ethernet frames without FCS and checks the IPv4 header (version, IHL, checksum, length), fragments, protocol, destination address and UDP length. It optionally verifies the UDP checksum including the pseudo-header, and picks the lowest enabled matching destination port. Payload bytes stream out with a one-byte holdback so tlast can

FINDINGS id | sev | cat | where | conf | src | title | fix
F-3d044d | minor | verification | faults.yaml:4 | medium | judge | Seeded-fault set misses key checks | Add faults such as fold(ip_acc) compare removed, `ulen <= tl-hl` loosened, `k+1 < u_end` off by one, f_bad ignored, `ucs != 0` removed, and ev_empty/ev_no_port 
F-81b523 | minor | verification | formal/formal_udp_rx.sv:21 | medium | both | Formal proof covers only protocol rules, one parameter point, and depends on an external module | State the BMC depth in the README. Assert, or document why you ignore, viol[4:3]. Add formal properties for tlast and tuser, for example that tlast appears exac
F-167a7b | minor | other | rtl/ipv4_udp_rx.sv:50 | medium | both | Parameter guards are in an initial block, so synthesis may not enforce them | Use `generate if (...) $error(...)` elaboration-time checks, which both tools evaluate at elaboration.
F-b75054 | minor | documentation | rtl/ipv4_udp_rx.sv:64 | high | judge | README/ip.yaml claim 'Registered outputs: yes' but s_axis_tready is combinational from m_axis_tready | Document the combinational tready path, or add a skid register on the output to break it.
F-c898d8 | minor | documentation | rtl/ipv4_udp_rx.sv:87 | medium | judge | Header comment says total length >= header+8 is checked as a bad-IP condition; code differs | Reword the comment, and state in the README which event each length error raises.
F-7d8ff7 | minor | timing | rtl/ipv4_udp_rx.sv:111 | high | judge | Timing fails at 125 MHz; verdict path is a long combinational cone | Register the folded IP and UDP checksum results, and the hdr_ok, len_ok and port_hit flags, in extra cycles. Use the one-clock `fin` gap, or add a verdict stage
F-e3bf46 | minor | verification | tb/udp_rx_cocotb.py:68 | medium | judge | Tests never exercise reset in flight, mid-frame tuser, or all parameter combinations | Add a reset-mid-frame test (check the next frame is clean, no spurious tvalid). Add runt frames and a mid-frame tuser. Sweep BCAST and MCAST independently.

QUESTIONS
- Is ev_* intended to pulse for frames dropped with s_axis_tuser set when the datagram is not for us? The code and model both stay silent there; confirm this is intended.
- What BMC depth was used for the formal runs? The result files are not provided.

TEST GAPS
- Reset during a frame or during an output stall.
- s_axis_tuser asserted mid-frame, not just on the last beat.
- Frames shorter than 14 bytes, and back-to-back frames with m_axis stalled at tlast.
- Config changes during traffic.
- Full parameter cross product (CHECK_UDP=0 with ACCEPT_BCAST=1, BCAST/MCAST independence).
- Frames above Ethernet size, with k saturation.
- Timing at 125 MHz; no board run.

RULES: this review did not edit the design; fixes are separate, opt-in work. Re-run the checks after any change.