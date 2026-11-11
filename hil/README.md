# hil/: hardware-in-the-loop

Verifying a design by sensing what it does on a board and feeding the result back (brief 30). Two rigs live here.

| Path | What |
|---|---|
| [cdc_soak/](cdc_soak/README.md) | the CDC soak rig (brief 11b/11c) |
| [instruments/](instruments/) | host-side drivers: board lock, UART-shell instrument hosts (XADC, logic analyser, frequency and duty, frame CRC), audio capture and tone measurement, JTAG sysmon, logic-analyser decode (UART, SPI, I2C), M2K (libm2k), Pluto swept analyser and tracking generator, Red Pitaya SCPI, golden models |
| [ip_tb/](ip_tb/) and [tests/](tests/) | cocotb benches and pytest for the five library instruments in [ip_lib](../ip_lib/README.md) (`freq_duty_counter`, `frame_crc`, `dds_awg`, `logic_analyser`, `adc_histogram`), the ILA known-answer checks, the driver tests |
| [ip_faults.py](ip_faults.py) | seeded-fault runner for those five (16 faults, all caught: [results/b30/faults.json](../results/b30/faults.json)) |

The stage that runs a design's `hil.yaml` after the board build is [flow/hil.py](../flow/hil.py); the demonstration designs are
[designs/b30_hil_audio](../designs/b30_hil_audio) and its seeded-fault twin [designs/b30_hil_audio_pinfault](../designs/b30_hil_audio_pinfault).
Measured results and what was and was not connected on 2026-11-11: [results/b30/README.md](../results/b30/README.md).

Rules that bind every run here: SRAM only (never flash, SD or eMMC; never eFUSE or BBRAM); wall power with at most 2.0 W
predicted and Tj at most 85 C; no VGA hot-plug; one board job at a time through `_handoff/board.lock`
(`hil/instruments/board_lock.py` takes it with exclusive create and releases only a lock carrying the same session prefix);
the Pluto transmits only into at least 30 dB of attenuation or a dummy load (`pluto_sa.tracking_sweep` refuses otherwise).
