# Independent usefulness rating (human-check substitute)

One Sonnet sub-agent, given written criteria (real, important, actionable, severity, missed problems, overall 1 to 5) and not given
the benchmark truth, rated every critical, major and minor finding in six reviews: three benchmark designs (r1 of a held-out design with
a planted defect, a control, a verification-environment case) and three real blocks (`ipv4_udp_rx`, `igmp_join`, `arp_responder`). These
are the rater's ratings, not scores from the benchmark; they stay out of the headline table.

| | Benchmark (3 reviews, 14 findings) | Real blocks (3 reviews, 21 findings) |
|---|---|---|
| Real: yes / no / unsure | 14 / 0 / 0 | 12 / 5 / 4 |
| Overall usefulness (1 to 5) | 5, 3, 4 | 3, 2, 3 |

Totals (35 findings): real yes 26, no 5, unsure 4; important high 4, medium 15, low 16; actionable yes 32, no 3; severity too high 4,
too low 0.

What the rater found wrong or missing on the real blocks:
- two reviews claimed a formal module was missing from the file set; the block's `.sby` file lists it. The review sees only the design
  directory text it is given and cannot resolve what the proof scripts include.
- a timing shortfall at 125 MHz and a documented behaviour were reported at major or minor although the README already states them.
- one substantive weakness the review did not raise: a constant LFSR seed in `igmp_join`, reset on every reset, so identical hosts draw
  identical report delays. Recorded as a finding for the block's next revision, not fixed here.
- on one benchmark design a minor testbench-stimulus point was rated too high.
The rater's reading: strong on small seeded defects; on real blocks about a third of the findings restate documented facts or are wrong
about files, and it missed the one real RTL weakness the rater could see.
