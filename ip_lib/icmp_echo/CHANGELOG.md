# icmp_echo changelog

## 0.2.0 (2026-11-16)

- Pipelined to meet 125 MHz out of context on xc7a100t-1 (brief 88; Vivado 2026.1, single runs). Behaviour is unchanged apart from latency: see the status line and the latency entry in ip.yaml. Same-clock races between a frame's verdict and free-running inputs (a tick, a flush, a lookup, an output handshake) resolve one clock later than in 0.1.0; no bench reaches them. Seeded faults re-expressed for the new RTL.
- The LUT RAM buffer at 16 KB still misses 125 MHz (104 MHz); use the block RAM buffer.

## 0.1.0 (2026-11-12)

- Initial version: simulated against a Python model, seeded faults caught, formal checks (bounded except where the
  README says proved), out-of-context cost on an Artix-7 (Vivado 2026.1); not run on a board. See README.md.
