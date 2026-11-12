# Brief 58A board run plan (KR260, not yet run)

Status 2026-11-12: everything below is a plan. The KR260 is still in its box; no step here has been run.

## 1. Physical set-up (the owner, before any board step)

| Step | What | Why |
|---|---|---|
| Power | The kit's own 12 V, 3 A adapter into J12 (KB `board/kr260/power-config/kr260-power-boot-and-safety`). No other supply. Fan connected to J13 and turning. | The SOM fansink is the cooling. |
| SD card | The existing Linux image in J11, unchanged. No QSPI, eMMC or SD writes; SW1 never pressed. | The PL is loaded over JTAG into SRAM only. |
| JTAG and UART | One USB cable from the PC to J4 (FTDI USB-UART/JTAG). | `hw_server` programs the PL and carries the register bus (BSCANE2). |
| Ethernet, bench loop (first run) | One short Cat5e/Cat6 patch cable from **J10A** (Ethernet 3, PL, port B) to **J10B** (Ethernet 2, PL, port A). Nothing else in J10A/J10B. | The in-FPGA generator (port B) feeds the trading port (port A); both ends timed by one counter. No PC, no router. |
| Ethernet, PC run (second run) | A separate USB or PCIe Ethernet adapter on the PC, cabled straight to **J10B** only; the PC's normal network stays on its usual port. | The mock venue (`host/mock_venue.py`) talks to the board over UDP. |
| PS Ethernet | **J10C and J10D unplugged** for the whole brief. | The PS ports are the ones Linux would bring up; leaving them unplugged keeps the board off the home network. |
| Isolation | The bench adapter gets a static address on 192.168.58.0/24 (venue 192.168.58.15, board 192.168.58.10), no gateway, no DHCP, not bridged or shared; the PC's Wi-Fi/home link keeps its own subnet. The board's MAC addresses are locally administered examples (02:00:00:00:58:0a/0b). | Nothing the board sends can reach the home router or a work device; nothing from the home network reaches the board. |
| SFP+ | Cage empty (brief 58B uses it, with laser safety). | Not part of 58A. |

The owner confirms each line once (see section 6). The first board run uses only the J10A-J10B patch cable.

## 2. Bring-up order (each step stops on the first failure)

1. Take `_handoff/board.lock`; check the build stamp (`0x001`) against `build/base`'s manifest after programming.
2. Program the PL over JTAG (SRAM). Follow-up first: `flow/program.tcl` accepts only a chain with one xc7a100t; a KR260 path
   (the PL TAP of the xck26 beside the PS's debug port, selected by the cable's serial) is still to write. No flash writes.
3. Read ID (`0x000` = 0x58A00001), TS twice (the counter runs), RX_CLK counters (`0x184/0x185`, against TS: 125 MHz on a 1000 Mb/s link,
   which also confirms the 25 MHz clock assumption on C3: KB says TAXI's figure, unconfirmed).
4. Operating conditions before anything else (section 4).
5. PHYs (MDIO, both ports, PHY addresses to be found by a scan 0..31 reading register 2/3): read the ID registers; set the RX clock
   delay on (register 20 bit 7, then a soft reset through register 0 bit 15) so the RGMII receive data are centre-aligned, as the XDC
   assumes; read link and speed (register 17) until both report 1000 Mb/s full duplex. **Owner question 1** below.
6. Port B generator, 1 packet, then counters on port A: 1 frame, 1 good, 0 FCS errors.
7. Rules (the standard test table from `tests/b58a_cocotb.py`), then the generator at 1 kHz for 10 s: counters against the model's
   expectations for the generated stream; histograms A and B read out.
8. Fault injection from the generator: bad FCS every 7th packet (speculative undo on hardware: poisoned or cancelled), sequence gaps
   with halt-on-gap, then the hostile set (`interlocks_under_attack`) replayed from the PC (second run).
9. The measurement run: 10^6 orders (generator interval chosen so the loop never overlaps; ~1.1 µs loop, so 10 µs is safe), histograms A
   and B, min/max/mean, and the operating conditions every minute (section 4). A determinism claim only if the histogram shows it.
10. Software comparison (second run, after the owner's yes for the PC link): the same rule in Python on the PC
    (`host/mock_venue.py` measures its own round trip) and on the PS (Linux on the KR260, a UDP socket); the PS path needs the PS
    Ethernet or a loop through the PL and is a planning item, not yet designed.

## 3. Tick-to-config on the board

`host/strategy.py` runs on the PC over the JTAG register bus (slow: each register access is several JTAG scans) and later on the PS.
Measure: the time from a book change (a generator packet, its RX timestamp read from the decision log) to the commit (`COMMIT_TS`),
both on the board's counter. The simulation only shows the mechanism and the stale-parameter case; it does not measure software time.

## 4. Operating conditions (house rule, every run)

- SYSMON (PL) over the DRP registers (`0x1A0`): die temperature, VCCINT, VCCAUX, VCCBRAM, and the PS supplies, at the start, every
  minute, and at the end, in the common capture format (brief 52).
- Alarm thresholds written over DRP at the start, at the recommended operating conditions with margin, latched in `0x1A2` between polls.
- **The limits must come from the KB.** The KB has no XCK26 recommended-operating-conditions skill yet (searched 2026-11-12: `device/xck26`
  has io-standards, logic-fabric, primitives only). A KB task (from the K26 data sheet) comes before the first board run.
- Every failure report states the nearest readings and "inside ROC" or "outside ROC".

## 5. Stretch: 58C, a minimal TCP session for order entry

Not started. One TCP connection to the mock venue, the sequence and acknowledgement fields handled in the PL for the fast path,
retransmission left to software. Public text must then say, for every number, whether it used UDP (58A) or TCP (58C).

## 6. What the owner must confirm before the first board step

1. The physical set-up of section 1, line by line (power, J4 cable, the J10A-J10B patch cable, J10C/J10D unplugged, SFP+ cage empty).
2. That the bench is isolated: no cable from J10A/J10B to any switch or router; for the PC run, a dedicated adapter with a static
   192.168.58.x address and no sharing or bridging.
3. That PL programming over JTAG while the KR260's Linux keeps running is acceptable (the PS is not used by this design).
4. That the PHY register writes of step 5 (RX delay on, soft reset) are acceptable (they are volatile: a power cycle restores them).
5. The board-lock window and whether a 10^6-order run may be left unattended after a clean smoke run.
