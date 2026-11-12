# Shell protocol 1.1 on the board: BUILD_ID over the UART (2026-11-12)

T1 built fresh with the 1.1 shell on Vivado 2026.1 (4 threads; gates pass, WNS 4.307 ns, 526 LUT), build ID `fd6f6bfb`
(`manifest.json`), then programmed into SRAM on a Nexys A7-100T:

| Where | Read | Manifest | Match |
|---|---|---|---|
| UART, shell register 0x05 BUILD_ID (`uart.json`) | `fd6f6bfb` | `build_id` `fd6f6bfb` | yes |
| UART, shell register 0x02 build stamp | `5ba59eb7` | `settings.build_stamp` `5ba59eb7` | yes |
| UART, SHELL_VERSION | `0x00010001` (1.1) | | |
| JTAG, `REGISTER.USR_ACCESS` (`program.json`, `build_id_jtag`) | `fd6f6bfb` | `build_id` `fd6f6bfb` | yes |

The T1 hardware tests then passed 8 of 8 (`hw_tests.txt`), including the protocol 1.1 checks (0x05 read-only, 0x06 reserved).

Operating conditions from the on-chip sensor at programming time (`program.json`, `conditions`): 26.7 C, VCCINT 1.006 V,
VCCAUX 1.794 V, VCCBRAM 1.006 V, alarm flags 0000; inside the Artix-7 -1 recommended operating conditions (DS181 table 2)
and the board's 85 C limit. The latched minimum and maximum in `program.json` were read at programming time, so they
cover the configuration up to then, not the test window that followed (the tests took 38 s). The end-of-run sensor read
was refused while a Vivado build ran; by the time it ran, another session had reprogrammed the board, so it is not
recorded.
