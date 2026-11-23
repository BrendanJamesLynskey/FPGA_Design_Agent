# KB note proposal (brief 186): how AMD defines GTF latency, for comparison with our numbers

Proposal only; no KB PR opened (task 2 measured nothing). Suggested claims, each with its source, for the family matrix (UltraScale+ GTF versus GTH) and the latency skill:
1. AMD's GTF base latency on the UL3524 (RAW 2.34 ns, MAC 5.44 ns) is the one-way transceiver block only: start = TX data latched by the GTF on TXUSRCLK, stop = the RXUSRCLK edge where the GTF launches RX data into fabric; near-end loopback; clocks about 644 MHz 180 degrees apart; excludes framing, PL and package. Source: Alveo-Cards `ul3524` branch, `GTF_Latency/README.md`, commit 5e124a2.
2. It is a minimum over repeated runs and varies with the TX/RX clock phase after each reset, and (MAC mode) with the 33-cycle gearbox position. Same source.
3. It must never be compared with a link-trip figure (ours: E, L - E) without stating the different paths. Our `docs/latency_definitions.md`.
4. Vivado 2026.1 Basic licence: `xcvu2p-fsvj2104-3-e` is refused for project creation and synthesis, and xsim Basic refuses any design above 50,000 instances: `GTF_CHANNEL` plus `GTF_COMMON` alone is 61,854. Source: results/186_ul3524/licence.md and sim_attempt/.
