# Brief 30: hardware-in-the-loop verification (2026-11-11)

The Vivado builds (`builds.json`) were measured on 2025.2; the base build is superseded by `results/49_vivado_2026_1/b30_hil_audio.json`. The board runs (`hil_runs/`) used the earlier release's bitstreams and stay as recorded.

What was connected to the PC on 2026-11-11 (`lsusb`, `/dev/video*`, ALSA, libm2k/iio, the LAN):

| Item | State |
|---|---|
| Nexys A7-100T (FT2232 JTAG + UART), on wall power | connected, programmed over JTAG (SRAM only) |
| Behringer UMC22 USB audio (input 2 cabled to the Nexys audio jack) | connected; **a tone arrives** (below) |
| Onboard HDA line-in | present, not used |
| UGREEN HDMI capture (`/dev/video*`) | **not connected** |
| ADALM2000 (M2K) | **not connected** (no USB device, libm2k not installed) |
| ADALM-Pluto, RTL-SDR | **not connected** |
| Red Pitaya | **not reachable** (no `rp-*.local`; port 5000 closed on the four LAN neighbours) |

## Measured on the board

All from committed files: [hil_runs/b30_hil_audio.hil.json](hil_runs/b30_hil_audio.hil.json), [hil_runs/b30_hil_audio_pinfault.hil.json](hil_runs/b30_hil_audio_pinfault.hil.json), [builds.json](builds.json), [ila_t1/](ila_t1/).

| Path | Known answer and pass rule | Result | Seeded fault |
|---|---|---|---|
| UART shell | design ID `H30A` | pass | |
| Frame CRC (in FPGA) | CRC-32, pixel count and sum of a 128-pixel LFSR frame equal `models.frame_crc32`, zero new mismatches | pass (`93c30c48`, 128 pixels) | one pixel bit flipped in every frame: mismatches counted, CRC differs from the model: caught |
| Frequency in FPGA | 1000 Hz +-4 Hz | 1000.0 Hz | |
| Logic analyser (library IP) | 256 samples are a contiguous run of the DDS model (start tick unknown) | pass | |
| Pre-trigger | rising sign-bit edge at buffer index 8 | pass | |
| XADC (fabric DRP) against JTAG sysmon | Tj +-2 C, VCCINT/VCCBRAM +-20 mV, VCCAUX +-30 mV, Tj <= 85 C | Tj 25.72 vs 25.60 C, VCCINT 1.0063 vs 1.006 V, VCCAUX 1.7944 vs 1.794 V | |
| Audio at the jack (UMC22 input 2) | frequency +-2 Hz, level >= -75 dBFS rms, THD <= 5 %, SINAD >= 15 dB | 999.99 Hz, -29.27 dBFS rms, THD 1.32 %, SINAD 32.65 dB | pin fault below |
| ILA in batch (T1, `flow/bringup.py`) | T1's own rules on four 1024-sample captures | 4 of 4 pass | the same rules fail on five seeded capture or expectation faults ([hil/tests/test_30_ila_known_answer.py](../../hil/tests/test_30_ila_known_answer.py)) |

**Seeded fault that passes simulation and fails at the pins.** `designs/b30_hil_audio_pinfault` has the same RTL as
`b30_hil_audio`; only the constraint file differs (AUD_PWM on the LED0 pin, H17). Simulation passes (the RTL is the same
source), every in-FPGA check passes (7 of 7), and the audio check at the jack fails: level -90.5 dBFS rms, THD 72 %,
SINAD -2.9 dB. A simulation-only flow, or one that trusts the design's own self-checks, ships this.

**ILA limits (T1, 14 probes, depth 1024).** One trigger stage (the flow uses BASIC_ONLY, no storage qualification); the
tool-inserted core costs +1583 LUT, +2582 FF and +2 block RAM tiles on a 495-LUT design (utilisation `base` against `ila`);
capture of 1024 clocks at 100 MHz is 10.24 us; arm, upload and export through `hw_server` took about 20 s for four captures.
Probes are register output pins found after synthesis (names survive there, net names do not); one probe port can split
over several hardware probes, so the capture reader joins them by their MAP.

**Library instruments in context** (Vivado 2025.2, xc7a100t -1, 100 MHz, WNS +3.19 ns, 1228 LUT, 1158 FF, 0.5 block RAM tile,
0.128 W, predicted Tj 42.3 C): dds_awg 115 LUT, 48 FF, 1 RAMB18; frame_crc 274 LUT, 257 FF; freq_duty_counter 12 LUT, 165 FF;
logic_analyser 132 LUT + 88 LUTRAM, 142 FF; shell 564 LUT, 245 FF. Library simulation: 17 tests, 16 seeded faults all caught
([faults.json](faults.json)).

## Not measured (no hardware connected)

M2K logic analyser and scope, Pluto spectrum analyser and tracking generator, RTL-SDR cross-check, Red Pitaya instrument,
UGREEN video pixel compare, I2S2 audio paths, external analogue input on JXADC. The drivers for these exist
(`hil/instruments/{m2k,pluto_sa,redpitaya,logic_decode}.py`) and are tested on synthetic data or a fake SCPI server only; none
has run against an instrument. The purchase verdict therefore rests on specifications, not on a measured gap: see the report.
