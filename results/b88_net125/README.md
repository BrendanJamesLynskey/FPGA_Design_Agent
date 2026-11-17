# Net blocks to 125 MHz (brief 88)

Vivado 2026.1, out-of-context runs of each block at an 8 ns clock (one run per point; the Fmax figures are estimates, not
guarantees). The records of every agent run are in the folders named below; the baseline and final measurements are the
`char/*.json` of each `ip_lib/<block>`.

## Baseline (library 0.1.0) and final (0.2.0), Fmax estimate in MHz (WNS in ns)

| Block, point | xc7a100t-1 before | xc7a100t-1 after | xck26-2LV before | xck26-2LV after |
|---|---|---|---|---|
| icmp_echo bram 2 KB / 16 KB | 116 / 114 (-0.59 / -0.74) | 138 / 139 (+0.77 / +0.79) | 177 / 210 | 236 / 259 |
| icmp_echo lutram 2 KB / 16 KB | 106 / 89 | 130 (+0.31) / **104 (-1.6, still misses)** | 217 / 149 | 236 / 163 |
| ipv4_udp_rx 4 / 8 ports | 75 / 81 (-5.4 / -4.3) | 134 / 133 (+0.51 / +0.46) | 168 / 166 | 244 / 216 |
| ipv4_udp_tx bram 1472 / 8972 | 82 / 78 | 149 / 142 (+1.28 / +0.97) | 155 / 148 | 309 / 264 |
| ipv4_udp_tx lutram 1472 / 8972 | 80 / 74 | 143 / 125.1 (+1.0 / **+0.005**) | 168 / 164 | 272 / 215 |
| igmp_join 4 / 8 groups | 80 / 71 (-4.5 / -6.0) | 128 / 128 (+0.20 / +0.17) | 164 / 155 | 238 / 232 |
| arp_responder 4 / 16 entries | 128 (+0.21) / 116 (-0.65) | 151 / 127 (+1.39 / **+0.15**) | 198 / 213 | 288 / 228 |

The KR260 part already met 125 MHz out of context before this brief; so no agent run was made there. WHS was at least +0.04 ns
at every final point. Pulse width never bound (WPWS at least 2.75 ns).

## Latency (clocks, declared in each ip.yaml and asserted exactly by the benches)

icmp_echo reply 4 -> 5; ipv4_udp_tx first header byte 4 -> 7; arp_responder reply 3 -> 4; ipv4_udp_rx last payload beat 2 -> 6 after
the frame's last input beat (and the input is held 5 clocks after each frame, was 1); igmp_join a frame starts 3 clocks after the
pick and a query or report is acted on 1 clock later. Stated budgets before the runs: icmp +4, udp_tx +4, arp +3, udp_rx +6, igmp +4.

## Agent runs (xc7a100t-1, joint closure loop, 6 iterations, luna model, cost from provider usage)

| Run | Result | Cost |
|---|---|---|
| `xc7_icmp_echo_k1` | not closed: -0.59 -> -0.369 ns | $0.0208 |
| `xc7_icmp_echo_k2` (playbook fix on) | point 0 met (+0.099 ns, iteration 4); sign-off failed: 16 KB point misses, and a G1 re-run failed (shared sim build directory, since fixed) | $0.0170 |
| `xc7_ipv4_udp_rx_k1` / `_cont` (continuation from k1's best) | not closed: -0.145 ns both | $0.0198 / $0.0231 |
| `xc7_igmp_join_k1` | timing met, sign-off failed (adversarial bench) | $0.0266 |
| `xc7_ipv4_udp_tx_k1` | **closed and signed off** (+1.28 ns, 2 iterations) | $0.0063 |
| `xc7_arp_responder_k1` (16 entries) | **closed and signed off** (+0.146 ns, 1 iteration) | $0.0036 |

k = 1 per block (k = 2 for icmp as the before/after). No k = 3 repeats: each run is a single sample and says little about the rate.
Sign-off lists the seeded faults that no longer apply to the new text (`signoff_invalid_faults.txt`); these were re-expressed by hand.

## Hand baselines (the executor, time-boxed), `hand_rtl/`

icmp_echo (verdict registered one clock, buffer protection decided on byte 12, checksum add split in two): +0.77 ns.
igmp_join (checksums over two stages, verdict, random delay and Max Response Time registered): +0.17 ns at 8 groups.
ipv4_udp_rx (the agent's accepted checksum pipeline plus the header verdict taken one byte early and one more fold register): +0.51 ns.
ipv4_udp_tx and arp_responder are the agent's own result. The promoted RTL in `ip_lib/` is: icmp_echo, igmp_join, ipv4_udp_rx by hand;
ipv4_udp_tx and arp_responder by the agent.

## Not shown

In-context timing behind eth_mac_rgmii; the Nexys design was re-simulated (43 tests pass) but not rebuilt; no board; single runs at one seed.

## Records

Per agent run: `<case>/` (`history.jsonl`, `summary.json`, `closure_actions.jsonl`, `llm_calls.jsonl`, `task.json` (the task text's hash; the text itself is in the private knowledge repository), `rtl_final/`) and `<case>.log`; hand runs `hand_*` (build only); `faults_*.json` and `faults_reexpressed.json` (seeded faults after the change); `nexys_design_tests.log`, `full_tests.log` (local test runs); `hand_rtl/` (the hand RTL); `run.sh`, `chainB.sh`, `chainC.sh` (how the runs were started). Measurements: `ip_lib/<block>/char/*.json`.

## Reproduce

Needs Vivado 2026.1, Icarus, and a Python environment with pytest, cocotb 2.0.1, scapy and openai (and an OpenRouter key for the agent runs):
`results/b88_net125/run.sh <block> <extra-latency> xc7 <k> [point]` runs the agent loop (set `EXTRA=--scan-multiply` for the fixed playbook);
`python3 -m flow.ipchar <blocks> [--part xck26-sfvc784-2LV-c]` repeats the characterisation; `python3 -m pytest flow/net/tests/test_63d_*_rtl.py` the benches;
`python3 flow/net/faults.py` the seeded faults.

## Known gaps and limits

Single out-of-context runs at one clock; no in-context or board result; thin passes (+0.005, +0.08, +0.15 ns) are inside run-to-run noise; the 16 KB LUT RAM
icmp buffer still misses; k = 1 agent runs (k = 2 for icmp). The sign-off of agent runs does not cover the hand versions' same-clock race windows (see each block's CHANGELOG).
