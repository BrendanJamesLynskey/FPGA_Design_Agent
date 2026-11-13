# Debug on the board from a plain-English request: results

What this is for: say what you want to see on the running FPGA, and get back a probe plan, an on-chip logic analyser
build, a capture and an answer in plain words. This run checked that path on one design (T1, a dimmer and counter behind a
UART register shell) with five requests whose right answer was known in advance. How it works and the terms used (ILA,
probe port, comparator, ROC): [docs/debug.md](../../docs/debug.md).

Board: Nexys A7-100T (xc7a100tcsg324-1), on wall power, not USB. Vivado 2026.1, free Basic licence tier. 2026-11-12.

**All five answers matched the known answer and, where a register was read back over the UART shell, what the shell
read.** Each request was read by `openai/gpt-6-luna` through OpenRouter for 0.00011 to 0.00027 USD (provider-reported).
Every capture ran inside the recommended operating conditions (ROC: the data sheet's supply and temperature ranges), with
no alarm from the chip's own monitor.

What this does not show: one design and five requests only; the parser and the name resolver were not measured on other
designs or on requests the authors had not seen; each capture ran once; no agent role is offered the debug tools yet
(they were tested in CI only). More under "What is not shown here".

| Request (files) | Trigger as planned | Known answer | Seen in the capture | Build | Programming and capture (s) |
|---|---|---|---|---|---|
| [t1_count_write](t1_count_write/) | `win_wr == 1 AND addr == 0x80` | COUNT 0x0003 before the write, 0x1234 on the next clock, one write strobe; shell reads 0x1234 | count 0x0003 to cycle 0, 0x1234 from cycle 1; win_wr high 1 cycle at 0; readback 0x00001234 | new | 64.7 |
| [t1_pwm_period](t1_pwm_period/) | `phase == 0x00` | with DUTY 0x40, LEDs lit DUTY x 4 = 256 of 1024 clocks, lit value = COUNT 0x8421 | led 0x8421 for cycles 1 to 256, 0x0000 otherwise; readback DUTY 0x40, COUNT 0x8421 | new | 63.8 |
| [t1_sync_byte](t1_sync_byte/) | `rx_valid rises AND rx_data == 0xA5` | every shell request starts with the sync byte 0xA5 | rx_data 0xA5 at the rising edge of rx_valid (rx_data 0xA5 from cycle -868: one bit time, 868 clocks) | new | 48.3 |
| [t1_or_flags](t1_or_flags/) | `win_wr rises OR press_clear rises` | no button is pressed, so the DUTY write (300 ms after arming) triggers it; duty becomes 0x22 | win_wr 1, press_clear 0 at cycle 0; duty 0x40 to cycle 0, 0x22 from cycle 1 | new (rebuilt, see below) | 62.1 |
| [t1_reuse_rise](t1_reuse_rise/) | `win_wr rises` | COUNT written 0x0042; shell reads 0x0042 | count 0x0000 to cycle 0, 0x0042 from cycle 1; readback 0x00000042 | reused (no rebuild) | 58.0 |

Each run's files: `answer.txt` (generated from the capture alone), `check.json` (the known-answer comparison and the
number check), `plan.txt` (as shown before building) and `plan.json`, `llm_replies.json` (the model's replies),
`capture.json` (the common capture format), `capture.vcd`, `view.html` (the capture in the static viewer), and `ila/`
(the raw ILA CSV and VCD, the probe maps, the trigger set-up `plan.tcl`, the supply and temperature readings). The Vivado
logs, hw_server logs and programming transcripts are not kept, because they name the programming cable; `program.json`
keeps what they showed (build ID read back over JTAG, conditions at programming, power check). The answer and plan texts
were regenerated from the same captures after a wording review; no capture changed.

Try it without a board: `python -m debug_core answer results/50a_nl_debug/t1_count_write/capture.json`.

## Debug builds

Each probe set was built once ([builds.json](builds.json)). All checks passed; the quality-of-results check is not
available on the Basic tier.

| Probe set | Probes (bits) | Ports | Build ID | Wall | Peak memory | Worst setup slack (WNS) | LUT / FF / BRAM tiles |
|---|---|---|---|---|---|---|---|
| ad3b58a920a1 | win_wr, addr, count (25) | 2 | d2b75378 | 418.1 s | 5,243 MiB | 3.060 ns | 1606 / 2403 / 1 |
| a6a9590e41ad | phase, led (24) | 1 | ff89fe4c | 432.2 s | 5,262 MiB | 3.770 ns | 1557 / 2352 / 1 |
| 7b2af61c97ae | rx_valid, rx_data, uart_rx_pin (10) | 2 | 5cf65f69 | 444.2 s | 5,263 MiB | 3.947 ns | 1562 / 2325 / 0.5 |
| adcf8c7d382b | win_wr, press_clear, count, duty (26), both OR terms on one port | 2 | b4ad323a | 531.8 s | 5,231 MiB | 3.870 ns | 1599 / 2408 / 1 |
| 5786d4f73d78 | win_wr, press_clear, count, duty (26), one port per OR term | 3 | a6f3c5d2 | 505.1 s | 5,257 MiB | 3.869 ns | 1641 / 2454 / 1 |

Builds took 7 to 9 minutes. The first build used 4 Vivado threads and the rest 2, so the times are not comparable as a
speed measure. `report_power` on every build: 0.160 to 0.162 W total, confidence Low, junction 42.9 C estimated at 40 C
ambient; within the board limits of 2.0 W and 85 C.

## A Basic-tier refusal, measured: OR on one port

Vivado's Basic tier gives each ILA port one comparator, so two separate compare values joined by OR cannot share a port.
The first OR build (`adcf8c7d382b`) packed both 1-bit trigger signals into one port, and Vivado 2026.1 refused to arm it
([or_flags_same_port_refused/ila/ila_capture.stdout.txt](or_flags_same_port_refused/ila/ila_capture.stdout.txt)):

```
ERROR: [Labtools 27-3239] Trigger needs too many comparators for ILA port(index=0). Port has 1 comparators available, but 2 are needed
ERROR: [Labtools 27-3241] Unable to fit compare values for hw_ila 'hw_ila_1'. Multiple compare values for the same ILA trigger
port, can only be merged into the same comparator if 1) the overall trigger condition is 'AND', 'NAND' and 2) the compare value
operator for multi-bit hw_probes is 'eq'.
```

The planner now gives each OR term its own port (`5786d4f73d78`, 3 of 5 ports), and that build triggered correctly: not
at arming, but on the DUTY write 300 ms later, with the condition true at cycle 0. A build whose OR terms share a port is
never reused for an OR plan. The rising-edge compare (`R`, a 0-to-1 edge, in the trigger pattern) worked in three runs:
sync byte, OR and reuse.

## The build-ID guard, checked on the board

Before arming, a capture now reads the bitstream's build ID over JTAG and arms only if it is the debug build's own. On
the board: a replayed capture armed on the expected build (d2b75378) and passed again, inside the recommended operating
conditions; a capture with `--no-program` against a different build (ff89fe4c) was refused before arming. Record and
conditions: [build_id_guard/](build_id_guard/README.md).

## Operating conditions

The chip's own monitor (XADC) was read through JTAG at programming, when the logic analyser was armed and after the
upload, for every run (in each `capture.json` under `conditions`). Over all five runs: die temperature 24.7 to 26.9 C
(latched maximum 27.68 C), VCCINT 1.006 V (latched 1.0042 to 1.0071 V), VCCAUX 1.793 to 1.794 V, VCCBRAM 1.006 V; no alarm
flag; all inside the recommended operating conditions (VCCINT and VCCBRAM 0.95 to 1.05 V, VCCAUX 1.71 to 1.89 V, junction
at most 85 C on this board). The monitor samples at about 1 MSPS, so it cannot see nanosecond supply droop.

## Records

| Path | What |
|---|---|
| `t1_count_write/`, `t1_pwm_period/`, `t1_sync_byte/`, `t1_or_flags/`, `t1_reuse_rise/` | one request each, with the files listed under the table (`answer.txt`, `check.json`, `plan.txt`, `capture.json`, `capture.vcd`, `view.html`, `ila/`) |
| `or_flags_same_port_refused/` | the OR build that Vivado refused to arm (the ILA capture log) |
| `build_id_guard/` | the build-ID guard check on the board (`pass`, `refused`, `guard.json`, its own README) |
| `builds.json` | the five debug builds: probe set, build ID, wall time, memory, slack and utilisation |
| `demo.json` | the five requests, the parse, the plan and the check, as the site demo reads them |
| `hero.json` | the capture the site's hero animation plots |
| `page_checks.json` | measured contrast ratios and layout checks of the site page at the phone and desktop widths |
| `summary.json` | the runs table and numbers the site page quotes |

## Known gaps and limits

- One design and five requests: the parser and resolver were not measured on other designs or on requests the authors
  had not seen.
- No agent role is offered the debug tools yet; the tools were tested in CI only, not used on the board by an agent.
- No supply or temperature samples on the capture timeline (read at programming, arm and after upload only).
- One run each; captures were not repeated for variance.
- The debug builds are on the Basic licence tier: the quality-of-results check is not available, and the Vivado and hw_server logs are not kept (they name the programming cable).
- The first build used 4 Vivado threads and the rest 2, so build times are not a speed comparison.
- The XADC samples at about 1 MSPS and cannot see nanosecond supply droop.

## Reproduce

Needs the Nexys A7-100T attached, wall power, no other board job, Vivado 2026.1 and a heavy slot (a debug build takes 7 to 9
minutes). Without a board, the answer can be regenerated from a committed capture:

    python -m debug_core answer results/50a_nl_debug/t1_count_write/capture.json

With the board:

    python -m debug_core build <plan.json>        # one debug build per probe set
    python -m debug_core.demo_t1                  # the model reads each request (paid OpenRouter calls)
    python -m debug_core.demo_t1 --replay         # the recorded replies, no model call

The exact arguments used for the committed runs are not recorded here; `debug_core/demo_t1.py` has the options.
