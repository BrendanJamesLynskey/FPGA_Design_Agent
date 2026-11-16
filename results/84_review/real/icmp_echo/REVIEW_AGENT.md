# REVIEW (agent) icmp_echo id=icmp_echo schema=1 design_sha=93ab8705e205 mode=review (read-only)
top: formal_icmp; clocks: clk; scope: rtl
checks: lint=fail, standards=fail, resets=not_run, methodology=not_run, axi=pass | not run: resets, methodology
summary: icmp_echo answers ICMP echo requests for one IPv4 address on a byte-wide AXI-Stream link. It stores each received frame in a RAM (block or LUT RAM) while checking the Ethernet, IP and ICMP fields and both checksums. If the frame is a valid echo request and the buffer is free, it replays the stored frame with addresses swapped, a fixed TTL, ICMP type 0 and RFC 1624 incrementally updated checksums. 

FINDINGS id | sev | cat | where | conf | src | title | fix
F-5117d0 | minor | verification | formal/formal_icmp.sv:53 | high | judge | Formal reply-content check covers one byte and one RAM variant | Use a solver-chosen byte if it can be made to converge (for example with a small BUF and k-induction), or add a second instance with RAM=bram. Add mid-stream re
F-5f28ce | minor | timing | rtl/icmp_echo.sv:112 | medium | judge | Long combinational path from the checksum compare into the RAM write enable | Register `ok` in a stage after fin, and block a new frame's first byte by a conservative flag (for example fin&&echo_me&&f_store) or a delayed start. Pipeline t
F-bd4754 | minor | functional | rtl/icmp_echo.sv:113 | medium | judge | Ethernet destination MAC is not checked | Add a check on bytes 0..5 against own_mac or broadcast. Alternatively, document that the upstream MAC must filter.
F-809e1d | minor | functional | rtl/icmp_echo.sv:170 | medium | judge | Runt frames after a ping raise a spurious ev_bad (stale header registers) | Clear the captured fields, or a per-frame 'seen typ/dst' flag, when first is true. Alternatively gate echo_me with f_len > 37.
F-a6996d | minor | verification | tb/icmp_cocotb.py:97 | medium | judge | Testbench corners not exercised | Add directed cases for datagram length exactly BUF_BYTES-14 and BUF_BYTES-13, TTL=1, runt frames after a request, and a reset during a reply. Also check that ev

QUESTIONS
- Does the upstream MAC filter frames by destination MAC, so this block need not?
- Should a ping to the broadcast address or from a broadcast/multicast source be answered or suppressed?

TEST GAPS
- Reset in flight.
- Datagram length exactly at the buffer limit.
- TTL=1.
- Runt frames after a request (stale fields).
- Formal coverage of the bram variant and of reply bytes other than 13.
- Behaviour on frames addressed to another MAC.

RULES: this review did not edit the design; fixes are separate, opt-in work. Re-run the checks after any change.