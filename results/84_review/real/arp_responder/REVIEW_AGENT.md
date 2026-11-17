# REVIEW (agent) arp_responder id=arp_responder schema=1 design_sha=2a00846313f2 mode=review (read-only)
top: formal_arp; clocks: clk; scope: rtl
checks: lint=fail, standards=fail, resets=not_run, methodology=not_run, axi=pass | not run: resets, methodology
summary: arp_responder is a single-clock ARP (RFC 826) block for one IPv4 address. It parses byte-wide Ethernet frames, replies to requests for own_ip, learns sender MACs into a small fully-associative cache with round-robin replacement, and answers next-hop lookups. On a miss it sends a rate-limited broadcast request. It flags address conflicts (RFC 5227) through ev_conflict and never caches the conflicti

FINDINGS id | sev | cat | where | conf | src | title | fix
F-e7dddd | major | functional | rtl/arp_responder.sv:93 | low | judge | Parsed fields not cleared between frames; stale fields can validate a frame | Low priority. Note it in the documentation, or clear the fields at tlast.
F-ac4c95 | minor | verification | formal/formal_arp.sv:25 | medium | both | Formal wrapper uses axis_rules module that is not in the file set; checks are bounded only | Ship or reference axis_rules. Say which bit of viol is excluded and why.
F-f0e294 | minor | verification | rtl/arp_responder.sv:120 | medium | both | Conflict detection suppresses a self-originated frame only by MAC; ev_conflict is not in the formal  | Count ev_conflict in the bench and connect it in the formal wrapper.
F-0b8ec9 | minor | timing | rtl/arp_responder.sv:140 | high | judge | Cache lookup combinational compare limits Fmax; 16 entries miss 125 MHz | Pipeline the compare or the known/free search, as the README next steps already note. Mention in the parameter table that 16 fails 125 MHz.
F-d00469 | minor | functional | rtl/arp_responder.sv:151 | medium | judge | Holdoff misses a different address: single holdoff slot, and an ask is suppressed while a request is | Document that the holdoff covers only the most recent address, or add a small holdoff table.
F-5b0c2d | minor | functional | rtl/arp_responder.sv:154 | medium | judge | Lookup during a learn or flush is not coherent; a hit can be reported for a just-flushed entry | State in the README that a lookup in the flush clock may hit. Optionally mask lk_h with flush.
F-4a7bcc | minor | verification | rtl/arp_responder.sv:220 | low | judge | ev_drop and a reply collision: request arriving at the same clock as start_rep | Add a directed test of back-to-back requests where the second arrives at the clock of start_rep.
F-f177d5 | info | style | rtl/arp_responder.sv:57 | high | both | initial block with $error used for parameter guard | Optionally use a generate-if with $error, which is the cleaner elaboration-time form.

QUESTIONS
- Is own_ip/own_mac guaranteed static while frames are in flight?
- What is the intended behaviour for a lookup issued in the same clock as flush?

TEST GAPS
- ev_conflict is not counted in the main bench.
- Lookup concurrent with flush or learn.
- Alternating-address holdoff.
- Frames longer than 63 bytes (saturating k).
- Reset in flight during transmit or receive.
- A request arriving exactly at start_rep.
- Two requests where the sender is unknown, with a full cache and a simultaneous lookup hit.

RULES: this review did not edit the design; fixes are separate, opt-in work. Re-run the checks after any change.