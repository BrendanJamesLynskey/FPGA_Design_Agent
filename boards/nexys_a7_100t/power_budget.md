# Nexys A7-100T power budget (brief 04c, 2026-10-31)

What the power gate (`flow/hw.py` `power_ok`) checks, and why. Sources are named as in `inventory.yaml`
`documents:` (RM = Digilent reference manual, SCH = schematic Rev D.0, data sheets by part). Numbers marked
*assumed* are not in any document collected; the gate does not depend on them.

**Proposal for the owner (the owner decides):** keep **2.0 W** total on-chip as the **final wall-power limit**,
with **Tj <= 85 C computed for the board's own thermal environment**, and add three per-rail current limits
(below). Keep **0.5 W** on USB power. The binding limit on wall power is **heat, not the regulators**: in still
air with no heat sink the FPGA's junction reaches 85 C at about 2.5 W in a 40 C room.

## 1. Where the power comes from

| Item | Value | Source |
|---|---|---|
| Wall input | 5 V, 3 A supply on J13 (owner's), JP3 = WALL; the board accepts 4.5-5.5 V, centre positive, >= 1 A | RM 1.1, owner |
| USB input | the PC's port on J6, JP3 = USB; 500 mA at 5 V for a USB 2.0 port = 2.5 W for the whole board (*assumed*: a standard port) | RM 1.1 |
| Protection | 3.5 A fuse R287 and a SMBJ5.0A TVS diode (D16), not resettable | RM 1.2, SCH sheet 11 |
| 1.0 V rail (VCCINT, VCCBRAM) | IC22 ADP2118 buck, 3 A max | SCH sheet 11, RM Table 1.1, ADP2118 p.1 |
| 1.8 V rail (VCCAUX, VCCADC, bank 34 VCCO, DDR2) | IC23 **ADP2138** buck, **0.8 A** max (RM Table 1.1 names an ADP2118; the schematic's part and the RM's 0.8 A agree with the ADP2138) | SCH sheet 11, RM Table 1.1, ADP2138 p.1 |
| 3.3 V rail (FPGA 3.3 V banks, PHY, flash, sensors, SD, PIC24, Pmod VCC) | IC17 ADP2118 buck, 3 A max | SCH sheet 11, RM Table 1.1 |
| Audio 3.3 V | IC25 ADP121 LDO, 150 mA | SCH sheet 11, ADP121 p.1 |
| Straight from 5 V | the USB host port J5 (no current limiter), RGB LED anodes | SCH sheets 2, 4 |

## 2. What else draws from the rails (board loads, not in `report_power`)

| Load | Rail | Typical / max | Source |
|---|---|---|---|
| DDR2 MT47H64M16HR-25:H | 1.8 V | 30 mA standby (IDD2N) / **260 mA** bank-interleave read (IDD7, x16, -25E, die H) | MT47H Table 10 |
| Ethernet PHY LAN8720A | 3.3 V | 45 / 49 mA at 100BASE-TX with traffic | LAN8720A Table 5-1 |
| QSPI flash | 3.3 V | up to 61 mA reading (quad, 104 MHz); 100 mA programming (never done here) | S25FL128S DC characteristics |
| PIC24FJ128GB106 | 3.3 V | about 18 mA at 16 MIPS (DC24) | PIC24 Table 29-4 |
| ADT7420, ADXL362, microphone | 3.3 V | 0.27 mA, microamps, 0.7 mA max | data sheets (inventory.yaml) |
| 16 LEDs (330 ohm) | FPGA VCCO 3.3 V | about 4 mA each if lit (*assumed* 2 V LED drop): counted by `report_power` as I/O | RM 9 |
| microSD card | 3.3 V | not in any document collected; **100 mA budgeted** (*assumed*) | - |
| Pmod VCC pins | 3.3 V | up to 1 A per the RM; the owner has no Pmods, so 0 | RM 10 |
| RGB LEDs (6 colours) | 5 V | about 30 mA a colour fully on (*assumed* drops; 75-150 ohm resistors) | SCH sheet 2 |
| USB device on J5 | 5 V | up to 100 mA (low power) or 500 mA | SCH sheet 4 |

Board 3.3 V loads without Pmods: 49 + 61 + 24 + 1 + 100 (SD) = **about 0.24 A**; reserve **0.5 A**.

## 3. The FPGA's own limits

`report_power` reports on-chip power by rail and the junction temperature for the environment it is told.
Vivado's default environment is a **medium heat sink, 250 LFM airflow and a 10 x 10 in, 12-15 layer board**, which
gives an effective thetaJA of **4.6 C/W** (F0B's T1 report). The Nexys A7 has no heat sink and no fan. Since 04c
`flow/build.tcl` applies `boards/nexys_a7_100t/board.yaml` `thermal:` before `report_power`: **still air (0 LFM),
no heat sink, Vivado's "small" board, 4-7 layers** (the stack-up is not published, so the smallest class, which
spreads heat least), and **40 C ambient** (a warm room plus margin). Vivado then reports **thetaJA = 18.2 C/W**
(all three 04c builds, e.g. `designs/b2_tmp_adt7420/build/base/power.rpt`). The gate refuses any report made with
another airflow or a heat sink.

| Limit | Arithmetic | Allows |
|---|---|---|
| Thermal, 40 C room | (85 - 40) / 18.2 | **2.47 W** on-chip |
| Thermal, 25 C room | (85 - 25) / 18.2 | 3.30 W on-chip |
| VCCINT regulator (3 A at 1.0 V) | 3.0 A x 1.0 V | about 3 W on VCCINT alone |
| 1.8 V regulator (0.8 A) less DDR2 at IDD7 (0.26 A) | 0.54 A x 1.8 V | about 1 W for VCCAUX + VCCADC + bank 34 |
| 3.3 V regulator (3 A) less the board reserve (0.5 A) | 2.5 A | FPGA 3.3 V banks: rarely binding |
| Input fuse / wall supply (3.5 A / 3 A at 5 V) | 15 W from the supply | the rails above are reached long before |

So on wall power **heat binds first, at about 2.5 W**. At the interim 2.0 W the junction sits at about
40 + 2.0 x 18.2 = **76 C** in a 40 C room: a 9 C margin, and about 20 % in power for `report_power`'s estimate,
which is vectorless (confidence Low) for these designs.

## 4. Proposed limits

**Wall power (proposal; the owner decides):**

| Check | Limit | Why |
|---|---|---|
| total on-chip power | **<= 2.0 W** (unchanged from the interim) | thermal: 2.47 W reaches 85 C at 40 C ambient; 2.0 W keeps 20 % for estimate error |
| junction temperature | **<= 85 C** in still air, no heat sink, 40 C ambient | commercial grade (house rules) |
| VCCINT current | **<= 2.4 A** (80 % of the 3 A regulator) | IC22 ADP2118 |
| VCCAUX + VCCADC + VCCO18 + VCCAUX_IO | **<= 0.38 A** (80 % of 0.8 A, less 0.26 A for the DDR2 at IDD7) | IC23 ADP2138 shares the rail with the DDR2 |
| VCCO33 | **<= 1.9 A** (80 % of 3 A, less the 0.5 A board reserve) | IC17 ADP2118 shares the rail with the board |

The total and the junction limits are in `flow/hw.py` now (2.0 W is the interim value and also the proposal). The
three rail limits are **in the code too**, for both power sources: they can only make the gate stricter, and no
04c design comes near them (largest: VCCINT 0.031 A). Remove or change them if the owner prefers.

**USB power: 0.5 W confirmed.** The port gives 2.5 W for the whole board. Board loads with nothing plugged in are
about 0.24 A at 3.3 V plus DDR2 standby (0.05 W), so about **1.0 W from 5 V** at an *assumed* 80 % converter
efficiency; 0.5 W on-chip is about **0.6 W more**; that leaves about 0.9 W (180 mA) for LEDs, the display, VGA and
the RGB LEDs. The RM's own data point agrees: the out-of-box demo, which uses most peripherals and the DDR2, draws
about 400 mA (2.0 W) from USB (RM 1.1). Raising the USB limit would eat the margin for exactly the loads a design
is likely to switch on. On USB power: no USB device on J5 other than a low-power keyboard or mouse (J5 has no
current limiter), no DDR2/MIG designs (the DDR2 alone can take 0.47 W), the RGB LEDs at <= 50 % duty (RM 9.2).

## 5. The gate (`flow/hw.py` `power_ok`)

- The power source is read from the local board file: `boards.<name>.power_source: usb | wall` in
  `~/.config/fpga_design_agent/boards.yaml`. Missing file, board or key, or any other value: **usb** (fails safe).
  `flow/hw_discover.py` keeps the key when it rewrites the board's entry.
- It passes only if: total on-chip power <= the source's limit; junction temperature <= 85 C; the report's
  environment is still air and no heat sink; each rail current within section 4's limit.
- `flow/program.py` runs it before every programming step; `flow/bringup.py` and `flow/board_check.py` run it as
  their first step and record the result (source, limit, total, junction temperature, environment, rail currents).
- Tests: `flow/tests/test_hw_flow.py` (both sources, the junction limit, the default-environment refusal, the
  board-file rules, rediscovery keeping the source).

## 6. What 04c's bitstreams used (from their `power.rpt`, still air, 40 C ambient)

| Build | Total on-chip | Dynamic | VCCINT | 1.8 V rail (FPGA) | VCCO33 | Junction |
|---|---|---|---|---|---|---|
| `designs/b2_tmp_adt7420` | 0.116 W | 0.003 W | 0.031 A | 0.039 A | 0.004 A | 42.1 C |
| `designs/b2_acl_adxl362` | 0.116 W | 0.004 W | 0.031 A | 0.039 A | 0.004 A | 42.1 C |
| `designs/b2_qspi_jedec` | 0.117 W | 0.004 W | 0.032 A | 0.039 A | 0.004 A | 42.1 C |
| `designs/b2_mic_pdm` | 0.117 W | 0.004 W | 0.032 A | 0.039 A | 0.004 A | 42.1 C |

All four are almost entirely device static power (0.113 W at this temperature). The gate result of every
programmed bitstream is in `results/board_v2/runs/*.json`, step `power_ok` (source `wall`, from the local board
file).
