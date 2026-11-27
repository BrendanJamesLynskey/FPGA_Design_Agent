# Red Pitaya STEMlab 125-14 (original generation, v1.1): a target board and a lab instrument (brief 225)

The owner's board: hostname `rp-f00c16`, Red Pitaya OS 3.00-57 (U-Boot `redpitaya-v2026.1`, kernel `Release_2026.1`, Ubuntu 24.04.4) on an 8 GB card, input jumpers IN1 = LV
(+-1 V) and IN2 = HV (+-20 V) (owner, 2026-11-25). Zynq-7010 (`xc7z010clg400-1`), two 14-bit 125 MS/s ADC channels, two 14-bit 125 MS/s DAC channels, 512 MB DDR3, two 2 x 13
extension connectors (E1: 16 LVCMOS33 lines; E2: PS buses and four slow analogue inputs and outputs), eight PL LEDs.

**Nothing in this folder has been run on the board.** The agent touched no board or instrument while writing it. Every board step is a script the owner runs at a visit.

Files: [board.yaml](board.yaml) (every fact with its source, or unconfirmed and why), [pins_import.yaml](pins_import.yaml) and the generated
[redpitaya_stemlab_125_14-pins.xdc](redpitaya_stemlab_125_14-pins.xdc) (our own listing of pin facts from the vendor's BSD-licensed constraints and board file at a pinned commit),
[smoke/](smoke) (the generated smoke design, built on Vivado 2026.1: [results/95_boards/redpitaya_stemlab_125_14](../../results/95_boards/redpitaya_stemlab_125_14/smoke.json)),
[shell/](shell) (the block that goes into the vendor's shell, and its test bench).

## Two ways to build for it

| | **Shell** (default for instruments) | **Bare** (default for everything else) |
|---|---|---|
| What the agent writes | one block with a fixed port list (`rp_user_block`'s ports) | the whole PL design, as for the KR260 or the ZedBoard |
| What is kept | the vendor's register map, ADC and DAC front end, calibration registers, oscilloscope and generator; the PS reaches the block through the documented AXI window at `0x40700000` | nothing of the vendor's; the design owns the ADC and DAC pins and the PS-less PL |
| Build | `python3 tools/rp_shell.py prepare/build/package` (the vendor's Vivado script on the pinned shell with the block patched in) | the existing flow: `build.yaml` with `board: redpitaya_stemlab_125_14`, `flow/run_vivado.sh` |
| Host link | the shell's system bus through `/dev/mem` or Red Pitaya's `monitor` | none by default: the board has no PL UART and no JTAG cable here; use LEDs, the E1 lines or the PS |
| Load | `overlay.sh v0.94 <fpga.bit.bin>` (keeps the shell's device tree) | `fpgautil -b <fpga.bit.bin> -f Full` |

Why: an instrument is useful because the PS can reach it and because the front end is already right (the vendor's shell inverts the ADC slope, runs the DAC through ODDR primitives
and holds the calibration registers); redoing that per design would put the same risk in every design. A design that is not an instrument has no use for the window and gains
nothing from the shell. **Any design the agent can build can be aimed at this board** with `--board redpitaya_stemlab_125_14`; the interview checks it against the 7010 (17,600 LUTs,
35,200 flip-flops, 60 block RAM tiles, 80 DSP slices) and against the I/O in `board.yaml`.

## The shell, in numbers from the vendor's source (RedPitaya-FPGA at commit `728a4f37e9`)

The shell's PS AXI GP0 master reaches a system bus that is split into eight 1 MiB slots from `0x40000000` (slot n at `0x40n00000`; 20-bit slave addresses; bus clock the 125 MHz ADC clock).
Slots 0 to 5 are the shell's (housekeeping, scope, ASG, PID, analogue mixed signals, daisy); slots 6 and 7 are stubs in the Z10 build that answer every access with an error
(`ack` and `err` high, `rdata` undefined). `tools/rp_shell.py` replaces the slot-7 stub with the block (and, if asked, the slot-6 stub with a second one) and adds the block's
`dac_a`, `dac_b` to the sum the shell sends to the DAC. Nothing of the vendor's is committed: the tool fetches the pinned commit, checks the top file's SHA-256, requires every patch
marker to match exactly once, and records the result in `build.json`. The vendor's block-design scripts refuse any Vivado but 2025.1 with their own version check; the tool changes that
one line to accept the running version, so the result is a 2026.1 build of the vendor's design (stated in `build.json`; nothing else of the vendor's text is changed).
Licence: BSD 3-clause, Red Pitaya d.o.o.; see [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md).

**Bus adapter (brief 243).** The shell's slots do not see a one-cycle request with a one-cycle answer: the vendor's clock-crossing bridge in front of every slot holds `wen` or `ren` until the ack has been carried back
(a block with a one-cycle ack sees the request twice) and reads `rdata` two to three clocks after the ack was raised. A block that raises `rdata` for the ack cycle only, as `rp_user_block` and every block written to
`shell.yaml` does, therefore read 0 on every access: build `170300fd` answered no read in slots 6 and 7 at the board visit of 2026-11-27 (the vendor's own slots hold `rdata`, so they were unaffected). `tools/rp_shell.py`
now puts [shell/rp_bus_adapt.sv](shell/rp_bus_adapt.sv) between each slot and its block: one access to the block per request, the answer held for the bridge, a silent block answered with an error after 16 clocks.
Blocks keep the one-cycle convention unchanged. The adapter is tested by [shell/tb_rp_bus_adapt.sv](shell/tb_rp_bus_adapt.sv) (a model of the bridge, in CI) and, against the pinned vendor files, by
[hil/rp_bus_sim/](../../hil/rp_bus_sim/) in xsim; the evidence is in [results/243_redpitaya](../../results/243_redpitaya/README.md).

[shell/rp_user_block.sv](shell/rp_user_block.sv) is the template and the trivial test block (ID, scratch, a free-running counter, the two ADC samples, two DAC terms); its behaviour in the cases a
user could guess wrong is written at the top of the file and checked by [shell/tb_rp_user_block.sv](shell/tb_rp_user_block.sv).

## Shell files added by brief 235

- [shell/shell.yaml](shell/shell.yaml): the interface the shell gives a block (the ports of `rp_user_block`); the goal kind "block for a shell" (`--block-for-shell`) checks a block's ports against it instead of checking pins.
- [shell/fda_overlay.xdc](shell/fda_overlay.xdc): our constraints, read after the vendor's (`tools/rp_shell.py prepare --overlay`). It waives the timing of the vendor's own generator and oscilloscope logic, which this image does not use, and says so in its comments;
  the measured result and what it does not claim are in [results/235_redpitaya](../../results/235_redpitaya/README.md).

## Loading is volatile and the owner's

A custom bitstream is loaded at run time by the OS (`overlay.sh` or `fpgautil`, through the Linux FPGA manager); the PL configuration is volatile, so a power cycle returns the factory image.
The agent never writes the SD card, its boot partition or `boot.bin`, never changes the OS image or runs its updater, and never turns the factory SCPI server on (the `redpitaya_os` never-rule,
in every permission mode). `python3 -m hil.redpitaya_load script <package> --block <name>` writes the load-and-check script for the owner: it asks before it loads, verifies the load from the
loader's own files (`/sys/class/fpga_manager/fpga0/state`, `/tmp/update_fpga.txt`, `/tmp/loaded_fpga.inf`), runs the checks on the board and brings the JSON back, and restores the factory shell
with `RESTORE=1`. Its `DRY_RUN=1` path prints every board command and calls none.

## The box is the instrument or the target, never both

The lab file ([docs/agent.md](../../docs/agent.md#the-red-pitaya-as-a-target-and-an-instrument-brief-225)) gives the Red Pitaya `is_board: redpitaya_stemlab_125_14` and a `mode`:
`factory_instrument` (SCPI available, once the owner has turned the server on at onboarding) or `target_loaded` with the `build_id` of the design in it. The interview and stage 9 do not plan a Red Pitaya
measurement of a design that runs on the same Red Pitaya, and a hand-edited step that tries is refused; every run row records the mode it used.

## What a user could get wrong

- **Loading a design and then expecting the factory oscilloscope.** The factory image is gone until a power cycle or `RESTORE=1`; the web oscilloscope and SCPI server do not run.
- **A signal above +-1 V into IN1.** IN1 is on LV: full scale +-1 V, absolute maximum +-6 V. IN2 is on HV (+-20 V, maximum +-30 V). Check both jumpers with the board unpowered. A 3.3 V logic signal needs HV or a divider.
- **Driving OUT1 into something unprotected.** OUT1 is +-1 V into 50 ohm; the original-generation page does not state the swing into a high-impedance input, so a loopback OUT1 to IN1 starts small (the self-test uses 0.25 V) and a reading at full scale means clipped.
  No lead is fitted by the agent: the owner fits it with the board unpowered.
- **Reading an unmapped slot from Linux.** The stub answers with a bus error and what the PS does with it is not documented; the checks stay inside the block's register map.
- **Treating the 125 MHz clock as exact.** The vendor states no oscillator accuracy; a frequency counter on this board is as accurate as that oscillator, which is why the plan prefers an independent instrument for a ppm claim.
- **A power supply.** 5 V DC, isolated, 2 A or 2.1 A, micro USB; never a PC port.
- **Bitstream names.** `overlay.sh` and `fpgautil` expect `fpga.bit.bin` (the package step names it so); a plain `.bit` is not loaded.

## Known gaps

- The smoke design's 125 MHz clock, LEDs and pins are from the vendor's files; none was observed on the board. LED polarity is unconfirmed.
- The DAC's open-circuit swing and the oscillator accuracy are not stated by the vendor for this generation.
- The vendor's schematics are not open (a development schematic exists); the pin list is the vendor's constraints, not a schematic check.
- Bare-mode builds have no host link by default; a bare design that needs one must say how (E1 lines, or the PS through a shell-less block design, which the agent does not generate yet).
