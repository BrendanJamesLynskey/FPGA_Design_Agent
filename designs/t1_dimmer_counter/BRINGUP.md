# T1 bring-up guide: LED dimmer and push-button counter

For a tester who did not design it. Board: **Digilent Nexys A7-100T**. Bitstreams come from
`flow/run_vivado.sh designs/t1_dimmer_counter both`: `build/base/t1_dimmer_counter_top.bit` (the design) and
`build/ila/t1_dimmer_counter_top.bit` + `.ltx` (the same design with an ILA for debugging). Use the base build
unless you are debugging.

What the design does (full spec: [spec.md](spec.md), [spec.yaml](spec.yaml)): a 16-bit counter driven by the up,
down and centre buttons, shown in binary on the 16 LEDs (with PWM brightness) and in hex on the 7-segment display,
with every register reachable over the USB-UART through the test shell ([shell/PROTOCOL.md](../../shell/PROTOCOL.md)).

## 0. The automated bring-up (one command)

```bash
python3 flow/bringup.py designs/t1_dimmer_counter
```

With the board attached and both builds present, this discovers the board (exactly one JTAG cable, an xc7a100t,
and its UART), checks the USB-power gate, programs the base build into SRAM, runs the UART tests
(`tests/test_t1_hw.py`: identity and build stamp, the PROTOCOL.md byte strings, 1,004 scratch loopback values,
error responses and counters, sync hunting, frame timeout, framing error, the T1 registers against `model.py`),
programs the ILA build, captures four ILA windows and checks them against the model (`hw_checks.py`: a COUNT
write, and the PWM at three dimmer levels), and checks the design is still running. It writes
`results/f0b/t1_dimmer_counter_bringup.json` and exits non-zero on any failure. Sections 1-6 are the same checks
by hand, and what a person checks that the script cannot (buttons, what the display and LEDs look like).

**USB power only.** The board is powered from its PROG/UART USB cable. A bitstream is programmed only if its
`report_power` total on-chip power is at most 0.5 W (`power_ok_usb`, checked by `flow/program.py` before every
programming step; T1 base 0.133 W, T1 ILA 0.149 W, vectorless estimates). Do not leave many LEDs at full brightness
for long: the steps below use at most 0xA0 duty with a few LEDs lit, and 0x40 (25 %) when all 16 are lit. If the
board resets, browns out or drops off USB, stop: fit an external supply before going further.

## 1. Setup

| Item | Setting |
|---|---|
| Power | USB from the PC into the micro-USB port marked PROG/UART (J6); power switch on. JP3 (power select) on USB. Total on-chip power must stay at or below 0.5 W (section 0). |
| Programming mode | JP1 (mode) on JTAG. Nothing is written to the QSPI flash; a power cycle erases the design. (Programming over JTAG works whatever JP1 says; JP1 only chooses what loads at power-up.) |
| PC | Vivado 2025.2 Hardware Manager (`hw_server`), AMD's cable udev rules installed once (root), the user in `plugdev` with a udev rule for the FTDI UART, Python 3 with `pyserial`. |
| Cable | One FTDI FT2232 (`lsusb`: `0403:6010`). Channel A (USB interface 0) is JTAG, channel B (interface 1) is the UART. `hw_server` names the target `Digilent/<USB serial>A`: the USB serial plus the channel letter A. |
| Serial port | interface 1 of that FT2232: `/dev/serial/by-id/usb-Digilent_Digilent_USB_Device_<USB serial>-if01-port0` (on the F0B PC it was `/dev/ttyUSB1`; `ttyUSB0` is interface 0, the JTAG channel). `flow/hw_discover.py` finds it by serial and interface and records it in `~/.config/fpga_design_agent/boards.yaml`. 115200 baud, 8N1, no flow control. |
| Switches | all 16 down (off) to start. |

## 2. Program the board

**Batch (preferred, scripted).**

```bash
python3 flow/hw_discover.py                                   # once: finds the cable serial and the UART
python3 flow/program.py designs/t1_dimmer_counter base        # or: flow/run_vivado.sh designs/t1_dimmer_counter program
python3 flow/program.py designs/t1_dimmer_counter ila         # the ILA build, with its .ltx
```

`program.py` checks the power gate, that the bitstream was built from the sources in the tree (build stamp), and
then runs `flow/program.tcl` with the memory-safe Vivado settings. `program.tcl` opens the target **by serial**
(exactly one match, never "the first target"), checks the chain holds one xc7a100t, and programs SRAM only: any
flash request (`--flash`, `-cfgmem`, an `.mcs`/`.bin`/`.prm` file) is refused before Vivado touches the board.

**GUI.** Vivado → Open Hardware Manager → Open Target → Auto Connect → right-click `xc7a100t_0` → Program
Device → choose the `.bit` (and the `.ltx` for the ILA build) → Program.

**Done when:** the board's DONE LED (near the PROG button) is lit and the display shows section 3's pattern.
`program.tcl` reads the DONE pin from the configuration status register and prints `done_pin=1`.

## 3. What you should see straight after programming

| Output | Expected |
|---|---|
| LEDs LD0-LD15 | all off (the counter is 0) |
| 7-segment display, left to right | `4 0 _ _ 0 0 0 0`: brightness `40` (hex), two dark digits, counter `0000` |
| Decimal points | all off |
| UART | silent until the PC sends a request |

## 4. Step-by-step test (pass/fail)

Run the shell commands from the repo root; `P=` the UART from section 1 (for example `/dev/ttyUSB1`).
`SH="python -m shell.host.fpga_shell --port $P"`.

| # | Do | Pass if | Fail means |
|---|---|---|---|
| 1 | `$SH id` | `design_id T1DC`, `shell_version 1.0`, `build_stamp` = `build_stamp` in `results/f0a/t1_dimmer_counter_base.json` (`dfd4624e` on the F0B board) | wrong bitstream, or the UART is not working (see section 6) |
| 2 | `$SH scratch` | `scratch PASS` | UART bit errors (cable, baud) |
| 3 | `$SH status` | all four counters 0 | errors on the line: note which counter |
| 4 | Press **BTNU** (up) 3 times, slowly | display right digits `0003`; LD0 and LD1 lit; `$SH read 0x84` = `0x00000003` | 4+ or 1-2 counts: debounce problem; nothing: buttons or reset |
| 5 | Press **BTND** (down) 4 times | display `FFFF`; all 16 LEDs lit (at the 25 % reset brightness; go on to step 6 promptly on USB power); `$SH read 0x80` = `0x0000FFFF` | wrap-around wrong |
| 6 | Press **BTNC** (centre) once | display `0000`; LEDs off; `$SH read 0x84` = `0x00010403` | |
| 7 | `$SH write 0x80 0xA5A5` | display `A5A5`; LEDs 0,2,5,7,8,10,13,15 lit | register write path |
| 8 | `$SH write 0x81 0xA0`, then `0x08`, then `0x00` | LEDs bright, then clearly dim, then off; left digits show `A0`, `08`, `00` (0xA0, not 0xFF: USB power) | PWM |
| 9 | `$SH write 0x81 0x40`; `$SH write 0x82 3`; set SW7..SW0 to `1000 0000` | left digits `80`; LEDs at about half brightness | switch path (DUTY_SRC) |
| 10 | Switches back down; `$SH read 0x83` with SW15 up | `0x00008000` (bit 15 = SW15) | switch sync |
| 11 | `$SH write 0x82 0` | display dark; LEDs lit again at the DUTY register's brightness (`0x40`) | DISPLAY_EN, DUTY_SRC back to the register |
| 12 | Press the red **CPU RESET** button | back to section 3: LEDs off, `4 0 _ _ 0 0 0 0`; `$SH read 0x82` = `0x00000002` | reset |
| 13 | `$SH status` | all counters 0 (steps 1-12 sent only good frames) | |

The board passes if steps 1-13 all pass. Record the result (pass, or the first failing step) in the bring-up log.

## 5. Debug aids: the ILA build

Program the `ila` bitstream with its `.ltx` (section 2). In Hardware Manager the ILA `u_ila_0` appears with these
probes (1024 samples at 100 MHz = 10.24 µs a capture; [probes.yaml](probes.yaml)):

| Probe | Width | Signal |
|---|---|---|
| `count` | 16 | the counter |
| `led`, `phase` | 16, 8 | the LED outputs and the PWM phase counter (added in F0B so the ILA can check PWM duty against the level) |
| `press_up`, `press_down`, `press_clear` | 1 each | one-clock debounced press pulses |
| `rx_valid`, `rx_data` | 1, 8 | a byte received from the host, and its value |
| `win_wr`, `win_rd`, `addr` | 1, 1, 8 | the shell accessing a design register; `addr` is the request's ADDR byte (0x80 + register offset) |
| `uart_rx_pin`, `uart_tx_pin` | 1, 1 | the raw serial lines |

Trigger set-ups:

| Name | Trigger condition | Trigger position | Then do | Expect |
|---|---|---|---|---|
| count_write | `win_wr == 1` AND `addr == 0x80` | 64 | `$SH write 0x80 0x1234` | `count` becomes `0x1234` on the clock after `win_wr` |
| button_press | `press_up == 1` OR `press_down == 1` OR `press_clear == 1` (set the ILA to OR) | 512 | press any button | exactly one pulse; `count` changes by one (or to 0) on the next clock |
| host_byte | `rx_valid == 1` AND `rx_data == 0xA5` | 16 | `$SH id` | the trigger fires; `uart_rx_pin` shows the next byte's start bit |
| pwm_period | `phase == 0x00` | 0 | set COUNT and DUTY first | the 1024 samples are exactly one PWM period; each lit LED is on for DUTY x 4 of them |

`flow/bringup.py` runs `count_write` and `pwm_period` (at DUTY 0x08, 0x40 and 0xA0) by Tcl
(`flow/ila_capture.tcl`), exports each capture to CSV and VCD, and checks them with `hw_checks.py` (its docstring
states the comparison rules). One thing that surprised us: the `.ltx` names probes after nets, so one probe port
can appear as several hardware probes (`count` shows up as six, `addr` as three); `ila_capture.tcl` cuts each
trigger value across them using their `MAP` property, and `flow/ila.py` puts the CSV columns back together.

## 6. If it fails, check in this order

1. **Power and programming.** Is the red power LED on? Did programming finish with DONE lit? If not: the cable
   drivers (`hw_server` must list a Digilent target), the USB cable (some are charge-only), JP1 on JTAG.
2. **Right bitstream.** Step 1's `build_stamp` must match the results file. If it differs, you programmed another
   build.
3. **Reset.** If nothing responds (display stuck, UART silent), the design may be held in reset: CPU RESET is active
   low and must not be pressed or stuck.
4. **Serial port.** Wrong port (`ttyUSB0` is the JTAG channel), wrong baud, or another program holding the port.
   `$SH status` working but showing framing errors means a baud mismatch.
5. **Display or LEDs dark but UART fine.** Read CTRL (`$SH read 0x82`): bit 1 = 0 turns the display off. Read DUTY
   (`0x81`) and COUNT (`0x80`): LEDs are dark when either is 0, or when CTRL bit 0 = 1 and SW7-SW0 are down.
6. **Counts wrong by more than one per press.** Read PRESSES (`0x84`) after a single press; then use the ILA
   `button_press` trigger to see the pulses.
7. **Still stuck.** Capture with the ILA (`host_byte`, then `count_write`) and keep the waveform (`.wdb`/`.csv`) for
   the designer, with the build stamp and the step that failed.
