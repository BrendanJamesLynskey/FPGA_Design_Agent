# Brief 50A: debug on the board from a plain-English request

Nexys A7-100T (xc7a100tcsg324-1), design T1 (`designs/t1_dimmer_counter`), Vivado 2026.1 on the Basic licence tier,
2026-11-12. How it works: [docs/debug.md](../../docs/debug.md).

**Five known-answer requests, written in plain English, each went to a plan, a debug build, a capture on the board and an
answer; all five answers matched the known answer and what the shell read back.** Each request was parsed by
`openai/gpt-6-luna` through OpenRouter for 0.00011 to 0.00028 USD (provider-reported). Every capture ran inside the
recommended operating conditions with no XADC alarm.

| Request (file) | Trigger as planned | Known answer | Seen (from the capture) | Build | Program + capture |
|---|---|---|---|---|---|
| [t1_count_write](t1_count_write/) | `win_wr == 1 AND addr == 0x80` | COUNT 0x0003 before the write, 0x1234 on the next clock, one write strobe; shell reads 0x1234 | count 0x0003 to cycle 0, 0x1234 from cycle 1; win_wr high 1 cycle at 0; readback 0x00001234 | `ad3b58a920a1` (new) | 64.7 s |
| [t1_pwm_period](t1_pwm_period/) | `phase == 0x00` | with DUTY 0x40, LEDs lit DUTY x 4 = 256 of 1024 clocks, lit value = COUNT 0x8421 | led 0x8421 for cycles 1 to 256, 0x0000 otherwise; readback DUTY 0x40, COUNT 0x8421 | `a6a9590e41ad` (new) | 63.8 s |
| [t1_sync_byte](t1_sync_byte/) | `rx_valid rises AND rx_data == 0xA5` | every shell request starts with the sync byte 0xA5 | rx_data 0xA5 at the rising edge of rx_valid (rx_data 0xA5 from cycle -868: one bit time, 868 clocks) | `7b2af61c97ae` (new) | 48.3 s |
| [t1_or_flags](t1_or_flags/) | `win_wr rises OR press_clear rises` | no button is pressed, so the DUTY write (300 ms after arming) triggers it; duty becomes 0x22 | win_wr 1, press_clear 0 at cycle 0; duty 0x40 to cycle 0, 0x22 from cycle 1 | `5786d4f73d78` (new, see below) | 62.1 s |
| [t1_reuse_rise](t1_reuse_rise/) | `win_wr rises` | COUNT written 0x0042; shell reads 0x0042 | count 0x0000 to cycle 0, 0x0042 from cycle 1; readback 0x00000042 | reused `ad3b58a920a1` (no rebuild) | 58.0 s |

Every answer is in `<run>/answer.txt`, generated from the capture alone; `check.json` holds the known-answer comparison
and the number check (no number in any answer that is not in its capture). The plans are in `<run>/plan.txt` (as shown
before building) and `plan.json`; the model's replies in `llm_replies.json`; the captures in `capture.json` (the common
format) and `capture.vcd`; `view.html` opens the capture in the static viewer; `ila/` holds the raw ILA CSV, the probe
maps, the trigger set-up (`plan.tcl`) and the XADC readings.

## Debug builds

One build per probe set, each one build, not repeated ([builds.json](builds.json)); all gates passed, the QoR assessment
gate is absent on the Basic tier (brief 48).

| Probe set | Probes (bits) | Ports | Build ID | Wall | Scope peak | WNS | LUT / FF / BRAM tiles |
|---|---|---|---|---|---|---|---|
| ad3b58a920a1 | win_wr, addr, count (25) | 2 | d2b75378 | 418.1 s | 5,243 MiB | 3.060 ns | 1606 / 2403 / 1 |
| a6a9590e41ad | phase, led (24) | 1 | ff89fe4c | 432.2 s | 5,262 MiB | 3.770 ns | 1557 / 2352 / 1 |
| 7b2af61c97ae | rx_valid, rx_data, uart_rx_pin (10) | 2 | 5cf65f69 | 444.2 s | 5,263 MiB | 3.947 ns | 1562 / 2325 / 0.5 |
| adcf8c7d382b | win_wr, press_clear, count, duty (26) | 2 | b4ad323a | 531.8 s | 5,231 MiB | 3.870 ns | 1599 / 2408 / 1 |
| 5786d4f73d78 | the same, one port per OR term (26) | 3 | a6f3c5d2 | 505.1 s | 5,257 MiB | 3.869 ns | 1641 / 2454 / 1 |

The first build ran at 4 Vivado threads, the others at 2 (another session's Vivado job held the other slot), so the wall
times are not comparable with each other as a speed measure. `report_power` on every build: 0.160 to 0.161 W total,
confidence Low, junction 42.9 C estimated at 40 C ambient; within the board's 2.0 W and 85 C limits.

## A Basic-tier refusal, measured: OR on one port

The first OR build (`adcf8c7d382b`) packed both 1-bit trigger signals into one port. Vivado 2026.1 refused to arm it
([or_flags_same_port_refused/ila/ila_capture.stdout.txt](or_flags_same_port_refused/ila/ila_capture.stdout.txt)):

```
ERROR: [Labtools 27-3239] Trigger needs too many comparators for ILA port(index=0). Port has 1 comparators available, but 2 are needed
ERROR: [Labtools 27-3241] Unable to fit compare values for hw_ila 'hw_ila_1'. Multiple compare values for the same ILA trigger
port, can only be merged into the same comparator if 1) the overall trigger condition is 'AND', 'NAND' and 2) the compare value
operator for multi-bit hw_probes is 'eq'.
```

The planner now gives each OR term its own port (`5786d4f73d78`, 3 of 5 ports), and that build triggered correctly: not
at arming, but on the DUTY write 300 ms later, with the condition true at cycle 0. The rising-edge compare (`R`) worked in
three runs (sync byte, OR, reuse).

## Operating conditions

The XADC was read through JTAG at programming, when the ILA was armed and after the upload, for every run (in each
`capture.json` under `conditions`). Over all five runs: die temperature 24.7 to 26.9 C (latched maximum 27.68 C), VCCINT
1.006 V (latched 1.0042 to 1.0071 V), VCCAUX 1.793 to 1.794 V, VCCBRAM 1.006 V; no alarm flag; verdict "inside ROC" (VCCINT
and VCCBRAM 0.95 to 1.05 V, VCCAUX 1.71 to 1.89 V, Tj at most 85 C). Board on wall power. The XADC cannot see nanosecond
supply droop.

## What is not shown here

- One design and five requests: the parser and resolver were not measured on a held-out set of requests or designs.
- The agent tools were tested in CI only (no agent run used them on the board).
- No XADC samples on the capture timeline (read at arm and done only).
- One run each; captures were not repeated for variance.

Reproduce: `python -m debug_core.demo_t1` (live parse) or `--replay` (recorded replies), with the debug builds made first
(`python -m debug_core build <plan.json>` under a heavy slot) and `board.lock` free.
