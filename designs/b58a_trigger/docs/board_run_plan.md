# Board run plan: mock trading path on the KR260

**Purpose:** the first measurements of the trading path on real hardware: the latency from a packet's start
arriving to the response's first byte leaving, per order and with its full distribution, the speculative path against
the safe one, and the interlocks under hostile traffic. **No step here has been run.**

Terms: SYSMON is the FPGA's on-chip system monitor (die temperature and supply voltages), read through its DRP
(dynamic reconfiguration port) registers; ROC means the device's recommended operating conditions; BSCANE2 is the FPGA
primitive that lets a design use the JTAG cable as a data port.

## 1. Physical set-up (before any board step)

| Step | What | Why |
|---|---|---|
| Power | The kit's own 12 V, 3 A adapter into J12. No other supply. Fan connected to J13 and turning. | The SOM fansink is the cooling. |
| SD card | The existing Linux image in J11, unchanged. No QSPI, eMMC or SD writes; SW1 never pressed. | The PL is loaded over JTAG into SRAM only. |
| JTAG and UART | One USB cable from the PC to J4 (USB-UART/JTAG). | Programs the PL and carries the register bus. |
| Ethernet, bench loop (first run) | One short Cat5e/Cat6 patch cable from **J10A** (Ethernet 3, PL, port B) to **J10B** (Ethernet 2, PL, port A). Nothing else in J10A/J10B. | The in-FPGA generator (port B) feeds the trading port (port A); both ends timed by one counter. No PC, no router. |
| Ethernet, PC run (second run) | A separate USB or PCIe Ethernet adapter on the PC, cabled straight to **J10B** only; the PC's normal network stays on its usual port. | The mock venue (`host/mock_venue.py`, our own program) talks to the board over UDP. |
| PS Ethernet | **J10C and J10D unplugged** throughout. | The PS ports are the ones Linux would bring up; unplugged, the board stays off any other network. |
| Isolation | The bench adapter gets a static address on 192.168.58.0/24 (venue 192.168.58.15, board 192.168.58.10), no gateway, no DHCP, not bridged or shared. The board's MAC addresses are locally administered examples (02:00:00:00:58:0a/0b). | Nothing the board sends can reach another network; nothing from another network reaches the board. |
| SFP+ | Cage empty (the 10 Gb/s follow-up uses it, with laser safety). | Not part of this run. |

Each line is confirmed once before the first board step (section 6). The first run uses only the J10A-J10B cable.

## 2. Bring-up order (each step stops at the first failure)

1. Take the shared board lock. After programming, check the build stamp (`0x001`) against the build's manifest.
2. Program the PL over JTAG (SRAM). No flash writes.
3. Read ID (`0x000` = 0x58A00001), the time counter (`0x005`) twice, and the RX_CLK counters (`0x184/0x185`) against it:
   125 MHz on a 1000 Mb/s link. This also checks the input clock assumption (25 MHz on C3; AMD's schematic: SiT1602 U92 through buffer U91).
4. Operating conditions before anything else (section 4).
5. PHYs over MDIO (both ports; the PHYs are TI DP83867, port A = U79 at MDIO address 2, port B = U80 at address 3, separate
   MDIO buses; `docs/phy_dp83867.md`). Every register below is read first and written only if it differs. Extended registers
   (0x0032, 0x006F, 0x0086) go through REGCR (0x0D) and ADDAR (0x0E): REGCR = 0x001F, ADDAR = address, REGCR = 0x401F, then the
   data through ADDAR. Pre-registered, not run:
   - 5a. Read PHYIDR1/PHYIDR2 (registers 2 and 3) at addresses 2 and 3: expect 0x2000 and 0xA231 (the datasheet's OUI and model;
     the low four bits of register 3 are the silicon revision and may differ). A different value, or no answer at 2/3, stops the run.
     Read RGMIICTL (0x0032): expect bit 7 (RGMII enable) = 1 and bits 1:0 = 11 (TX and RX clock delay on). Read STRAP_STS2 (0x006F) and
     RGMIIDCTL (0x0086): record both (the strap defaults on this carrier give 2.0 ns on each side; the datasheet's strap and register
     tables disagree on the encoding, so this read is how the reset value is known). Do **not** use the global software reset (CTRL 0x001F
     bit 15): it returns every register to its default.
   - 5b. Delay sweep, in the bench loop (step 6's generator running, one frame per millisecond): write RGMIIDCTL TX field 0x0 to 0xF
     (0.25 to 4.0 ns), keep the RX field, and at each value send 1000 frames from port B and read port A's good and FCS-error counters
     and the receive counters; then repeat on the opposite direction (port A to port B) by reading port B's counters. Record the range of
     TX delay with no FCS errors in both ports and choose the centre. The same for the RX field at the default TX (the FPGA's RX IDELAY
     is 1000 ps). The build's timing (docs/phy_dp83867.md) assumes TX = 1.75 ns (`RGMIIDCTL[7:4]` = 0110) and RX = 2.0 ns (`[3:0]` =
     0111), so the first working write is RGMIIDCTL = 0x0067.
   - 5c. Leave the PHYs at the chosen values, read RGMIIDCTL back, then read link and speed (register 0x11, PHYSTS: bits 15:14 speed
     = 10 for 1000 Mb/s, bit 13 duplex, bit 10 link) until both ports report 1000 Mb/s full duplex with link up.
   - All writes are volatile: a PHY hardware reset or a power cycle restores the strap defaults.
6. Port B generator, one packet, then the port A counters: one frame, one good, no FCS errors.
7. The standard rule table from `tests/b58a_cocotb.py`, then the generator at 1 kHz for 10 s: the counters against the
   model's expectation for the generated stream; histograms A and B read out.
8. Fault injection from the generator: a bad FCS on every 7th packet (the speculative undo on hardware: dropped,
   poisoned or cancelled), sequence gaps with halt-on-gap, then the hostile set (`interlocks_under_attack`) from the PC
   (second run). The order-slot status (`0x009`) must return to idle after each; if not, PULSE bit 7 drops an order that has not started (it never removes an undo: a started order from a bad frame is still poisoned or cancelled).
9. The measurement run: 10^6 orders (generator interval long enough that loops never overlap: about 1.1 us per loop,
   so 10 us is safe), histograms A and B, minimum, maximum and mean, and the operating conditions every minute. A
   claim of determinism only if the histogram shows it.
10. Software comparison (second run, after the PC link is confirmed): the same rule in Python on the PC
    (`host/mock_venue.py` measures its own round trip) and on the KR260's processor; the processor path needs its
    Ethernet or a loop through the PL and is not yet designed.

## 3. Tick-to-config on the board

`host/strategy.py` runs on the PC over the JTAG register bus (slow: each register access is several JTAG scans) and
later on the KR260's processor. Measured on the board's counter: from a book change (a generator packet; its time from
the decision log) to the commit (`COMMIT_TS`, `0x007`).

## 4. Operating conditions (recorded on every run)

- SYSMON over the DRP registers (`0x1A0`): die temperature, VCCINT, VCCAUX, VCCBRAM and the processor supplies, at the
  start, every minute and at the end.
- Alarm thresholds written over DRP at the start, at the ROC with margin, latched in `0x1A2` between polls.
- The XCK26 ROC limits must be taken from its data sheet before the first run; they are not yet in our notes.
- Every failure report states the nearest readings and whether they were inside or outside the ROC.

## 5. Later: a minimal TCP session for order entry

Not started. One TCP connection to the mock venue, sequence and acknowledgement fields handled in the PL for the fast
path, retransmission left to software. Any latency quoted will say whether it used UDP or TCP.

## 6. Confirmations before the first board step

1. The physical set-up of section 1, line by line (power, J4 cable, the J10A-J10B patch cable, J10C/J10D unplugged,
   SFP+ cage empty).
2. Isolation: nothing from J10A/J10B goes to a switch or router; for the PC run, a dedicated adapter with a static
   192.168.58.x address and no sharing or bridging.
3. Programming the PL over JTAG while the KR260's Linux keeps running is acceptable (the processor is not used).
4. The PHY register writes of step 5 (RGMIIDCTL TX and RX delay fields, swept in step 5b; no soft or global reset) are acceptable (they are volatile: a PHY
   reset or a power cycle restores them).
5. When the board may be used, and whether a 10^6-order run may run unattended after a clean first run.

## Known gaps

- The transmit constraints take at most 0.05 ns (port A) and 0.09 ns (port B) of TXC-to-TXD skew from the carrier copper (AMD board file, via brief 162); the SOM's routing is not in the files.
- The DP83867 datasheet gives the transmit window only as a clock-after-data range at the PHY (1.0 to 2.6 ns); how the PHY's own delay setting adds to it is our reading (`docs/phy_dp83867.md`), which step 5b tests.
- The PHY's 88 / 288 ns latency figures (RGMII to MDI, MDI to RGMII) are the datasheet's, unmeasured, and are outside every FPGA latency figure here.
- The flow's programming script supports only a single-device JTAG chain; a KR260 path still has to be written.
- `host/jtag_regs.tcl` has not run on a board; step 3 is its first test.
- There is no PL push button for the kill switch on the KR260; the kill is a register.
