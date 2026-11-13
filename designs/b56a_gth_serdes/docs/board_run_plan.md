# Board run plan: one GTH lane on the KR260 (brief 56B)

**Purpose:** the first measurements of the transceiver on hardware: bring-up, a PRBS-31 bit-error-rate bound in near-end loopback and through the
optical loop, and the module's own diagnostics. **No step here has been run.** Terms: PMA loopback = the receiver listens to its own transmitter inside the
transceiver (no light, no module); SFF-8472 = the standard memory map of an SFP+ module (identity at I2C address 0x50, diagnostics at 0x51); LOS = loss of
signal; ROC = recommended operating conditions.

## 1. Physical set-up (confirmed once before any step)

| Item | Requirement |
|---|---|
| Power | The kit's own 12 V adapter on J12; fan on J13 turning. KR260 powered only by whoever holds `_handoff/board.lock`. |
| Module | The 10Gtek 10G SFP+ LR (1310 nm) in J24 with the LC OS2 loopback fibre in its two ports (fitted by the owner, 2026-11-13). Dust caps on whenever a fibre end is open. |
| Laser safety | Class 1 module, but **never look into the port or a fibre end while the module is powered.** Keep `CTRL.tx_disable = 1` (laser off) except during a test. Never fit an ER or ZR module without a 15 dB or larger attenuator. |
| JTAG | One USB cable from the PC to J4 (JTAG). The PL is loaded into SRAM only; flash, eMMC and SD are never written. |
| SD card | A new card was due on 2026-11-14 for the PS; this design uses no PS and no SD, so the card state does not matter to it. If the PL cannot be loaded over JTAG with the PS idle, stop and ask: nothing else is to be tried. |
| Limits | Wall power; at most 2.0 W predicted (the build reports 0.77 W on-chip, `results/56a_serdes`); junction at most 85 C with a stop of our own; no VGA or other hot-plug while powered. |

## 2. Bring-up order (each step stops at the first failure)

1. **Laser polarity first.** With the module and fibre loop fitted and `tx_disable = 1`: read `STATUS.mod_abs` (expect 0: module present), `rx_los` (expect 1: no light) and `tx_fault` (expect 0).
   Write `CTRL.tx_disable = 0`: within about 10 ms `rx_los` should fall to 0 (light through the loop). Write 1 again: `rx_los` rises. If it does not fall, the polarity or the pin functions differ from the open-source example: stop and read the schematic.
   This step also checks the I2C-independent pin map. Laser on for seconds only.
2. Program the PL over JTAG (SRAM). Read `ID` (0x56A00001) and `BUILD` against the build's manifest.
3. Operating conditions at the start: SYSMON temperature, VCCINT, VCCAUX, VCCBRAM through `SM_ADDR`/`SM_DATA` (raw codes; the conversion is UG580's and is checked before any number is quoted). Limits from the knowledge bank (device and family ROC), plus 85 C.
4. Link bring-up with the laser off: wait for `STATUS.tx_done` and `rx_done` (loopback = 2 near-end PMA, then pulse `rx_dp`), `gt_powergood`, `cdr_lock`. The reference clock is unconfirmed: if `tx_done` never rises, the reference is the first suspect (check with `STATUS` and the CPLL/QPLL lock through the DRP window).
5. **Near-end PMA loopback, PRBS-31:** fabric checker locked, `PULSE.clear`, then count for a stated time. A BER bound needs the bit count: 3 x 10^12 error-free bits (about 291 s at 10.3125 Gb/s) bound the BER under 1e-12 at 95 % confidence; report the bound and the bits, never "zero errors". Repeat with the hard PRBS checker and say which checker produced each number.
6. **External loop, laser on, PRBS-31,** same bound; operating conditions logged at the start, end and at least once a minute; the module's I2C diagnostics (temperature, Vcc, bias, TX and RX power) read at the start and end. The first board run reads MOD_ABS and the pin levels only: the I2C master for SFF-8472 is built in 56B.
7. Error injection: `PULSE.force_err_fab` and `force_err_hard`, counts match; loopback back to 0 with a reset pulse.

## 3. What to record (every number with its conditions: one module, one loop, the temperature, the number of runs)

Operating conditions at the start and end and at intervals (house rule "operating conditions are evidence"): die temperature, VCCINT, VCCAUX, VCCBRAM, and the module's temperature and Vcc. A failure outside ROC voids the run. Results go to `results/56b_*` in the common capture format.

## 4. Scope limit of this board

One lane: channel bonding, lane deskew, PCIe x4 and 40G over QSFP+ are simulation-only. Multi-lane topics are labelled as such in every report.

## 5. Parts for 56B

Fitted: module and loopback fibre. Nothing to buy for this plan. Optional later, not ordered (owner, 2026-11-13: "not buying yet"): a variable or fixed optical attenuator set for the receiver-sensitivity curve of 56C item 8.
