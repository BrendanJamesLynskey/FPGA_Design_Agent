# Register map: gth_serdes_core (brief 56A)

Generated from `regmap.py` (`python3 designs/b56a_gth_serdes/regmap.py --write`); `tests/test_b56a_docs.py` fails if this file is stale or if the RTL's address decode differs.

## Bus rules (read first)

1. The bus is 32 bits wide with a 12-bit address field: the addresses below are the values the host puts in the address field of the `jtag_bus` command (one register per listed value, not byte addresses; no byte enables, no partial writes: every write replaces the whole register).
2. **Unmapped addresses:** a read returns 0x00000000, a write is ignored. There is no error response. The same holds for the gaps inside a mapped range.
3. **Reserved bits:** read as 0; writes to them are ignored.
4. **Reads have no side effects.** No register is cleared, popped or acknowledged by being read. Counters are cleared only by `PULSE.clear`; the sticky bits only by writing 1 to them (`STICKY`, W1C).
5. **Write-only registers read as 0.** `PULSE` bits are strobes: writing 1 starts the action once, writing 0 does nothing, and nothing is stored.
6. **Counters are read from a snapshot.** The counters run in the receive clock domain; `PULSE.snap` (write 1) copies the latest crossed copy of all of them at once into the snapshot registers, so a 64-bit counter read as two words, or several counters read one after another, are from the same instant. The crossed copy is at most a few hundred nanoseconds old at the time of the snapshot. `SNAP_COUNT` counts snapshots. Without a snapshot the registers do not change.
7. **Multi-word reads:** the low word and the high word of a 64-bit counter are separate reads of the same snapshot; there is no latching between them.
8. **Same-clock priority:** a write to `PULSE` that sets reset bits and a clear in the same word does both. Writing `CTRL` while a reset pulse runs takes effect immediately (the reset helper sees the new loopback or PRBS selection).
9. **Reset:** the register block is reset with the core clock (held until the 100 MHz clock is stable); values are in the tables. The GT Wizard is held in reset-all while the register block is in reset; its reset sequence starts when that reset is released.
10. **Clock domains:** the registers live on the 100 MHz free-running clock. Controls reach the GT user clocks through XPM synchronisers (two to four clocks of delay), so a changed selection takes effect a few user-clock cycles later. Reset pulses are 8 clocks long (80 ns).
11. **Latency of a read:** the value is registered once after the address is presented; the JTAG front end (`jtag_bus`) allows three clocks, so a read is always current. Registers that follow GT pins (STATUS, I2C inputs) are synchronised and trail the pin by two to four clocks.

## Registers

| Address | Name | Access | Reset | Summary |
|---|---|---|---|---|
| 0x000 | `ID` | RO | 0x56A00001 | Design identifier (56A, version 1). |
| 0x004 | `BUILD` | RO | BUILD_STAMP | The flow's build stamp (first 8 hex digits of the sources' SHA-256). |
| 0x00C | `CTRL` | RW | 0x00053008 | Link control. Reset: laser disabled, LPM equaliser, fabric PRBS-31 sending. |
| 0x010 | `PULSE` | WO (W1P) | 0 | Strobes. Writing a 1 starts the action once; reads return 0. |
| 0x014 | `STATUS` | RO | - | Link status (levels, synchronised to the 100 MHz clock). |
| 0x018 | `STICKY` | RW1C | 0 | Sticky events. Reading does not clear; write 1 to a bit to clear it. |
| 0x01C | `TXCFG` | RW | 0x00000018 | Transmitter shaping and the phase-interpolator ppm controller (all through GT ports; see UG576). |
| 0x020 | `FAB_WORDS_LO` | RO | 0 | Snapshot: 64-bit words compared by the fabric checker while locked (low half; bits = 64 x words). |
| 0x024 | `FAB_WORDS_HI` | RO | 0 | Snapshot: high half of the above. |
| 0x028 | `FAB_ERRBITS_LO` | RO | 0 | Snapshot: bits that differed while locked (exact: one line error is one bit; low half). |
| 0x02C | `FAB_ERRBITS_HI` | RO | 0 | Snapshot: high half of the above. |
| 0x030 | `FAB_ERRWORDS` | RO | 0 | Snapshot: words with at least one differing bit while locked. |
| 0x034 | `FAB_LOSSES` | RO | 0 | Snapshot [15:0]: times the fabric checker dropped its lock (4 words of 16 or more bad bits). |
| 0x038 | `HARD_CYCLES_LO` | RO | 0 | Snapshot: user-clock cycles with the GT checker locked (low half). |
| 0x03C | `HARD_CYCLES_HI` | RO | 0 | Snapshot: high half of the above. |
| 0x040 | `HARD_ERR_LO` | RO | 0 | Snapshot: user-clock cycles in which `RXPRBSERR` was high while locked (**cycles with an error, not a bit count**; low half). |
| 0x044 | `HARD_ERR_HI` | RO | 0 | Snapshot: high half of the above. |
| 0x048 | `SNAP_COUNT` | RO | 0 | Number of snapshots taken since reset ([15:0], wraps). |
| 0x050 | `I2C` | RW / RO | 0 | SFP+ I2C bit-bang, open drain (a 1 pulls the line low; 0 releases it to the carrier's pull-up). |
| 0x060 | `SM_ADDR` | RW | 0 | Write: start a SYSMON DRP read of this address [7:0] (the channel addresses are in AMD UG580's register map; not reproduced or checked here). Read: the last address. |
| 0x064 | `SM_DATA` | RO | 0 | [15:0] the last SYSMON read's data (the raw 16-bit register; the conversion to physical units is UG580's and is not applied here); [16] valid (0 from the write to SM_ADDR until the read completes). |
| 0x070 | `DRP_ADDR` | RW | 0 | GT channel DRP address [9:0]. |
| 0x074 | `DRP_DATA` | RW | 0 | Write: the data for the next DRP write [15:0]. **Read: the data of the last DRP read** (a write does not change it, so it is not the value written). |
| 0x078 | `DRP_CTRL` | W / RO | 0 | Write bit 0 = go (ignored while busy), bit 1 = write (1) or read (0). Read: [0] busy, [1] done (cleared by go). The Wizard arbitrates this access against its own calibration; DRP is ignored while the GT is held in reset, and **a go in that state never completes: busy stays 1 and later DRP commands are ignored until the register block is reset (no timeout)**. |
| 0x080 | `EYE` | RW / RO | 0 | Eye-scan ports (`EYESCANRESET`, `EYESCANTRIGGER`); the scan itself is run through the DRP window. |

## Fields

### 0x00C `CTRL`

| Bits | Field | Meaning |
|---|---|---|
| 2:0 | `loopback` | GT `LOOPBACK`: 0 normal, 1 near-end PCS, 2 near-end PMA, 4 far-end PMA, 6 far-end PCS. Changing it needs a reset pulse (`rx_dp` after near-end PMA). |
| 3 | `tx_disable` | Drives `sfp_tx_disable`. **Reset 1 = laser off (high-active convention; polarity on this carrier is unconfirmed until the first board run).** Write 0 to enable the laser. |
| 7:4 | `txprbssel` | GT transmitter PRBS: 0 off (the fabric sends), 1 PRBS-7, 2 PRBS-9, 3 PRBS-15, 4 PRBS-23, 5 PRBS-31, 8-10 compliance/square patterns. While non-zero the GT, not the fabric, drives the line. |
| 11:8 | `rxprbssel` | GT receiver PRBS checker select (0 off, same codes). A change pulses the checker's counter reset (UG576). |
| 13:12 | `fab_poly` | Fabric PRBS polynomial for generator and checker: 0 PRBS-7, 1 PRBS-15, 2 PRBS-23, 3 PRBS-31. A change restarts both. |
| 14 | `tx_pol` | Transmit polarity invert. |
| 15 | `rx_pol` | Receive polarity invert. |
| 16 | `rx_lpm` | 1 = low-power-mode equaliser, 0 = DFE (`RXLPMEN`). |
| 17 | `tx_idle` | `TXELECIDLE`: 1 = transmitter electrically idle. |
| 18 | `fab_tx_en` | 1 = the fabric PRBS generator runs; 0 holds it. |
| 19 | `cdr_hold` | `RXCDRHOLD`: freeze the CDR. |

### 0x010 `PULSE`

| Bits | Field | Meaning |
|---|---|---|
| 0 | `reset_all` | Wizard reset-all (PLLs and both datapaths), 8 clocks. |
| 1 | `tx_pll_dp` | TX PLL and datapath reset. |
| 2 | `rx_pll_dp` | RX PLL and datapath reset. |
| 3 | `tx_dp` | TX datapath reset. |
| 4 | `rx_dp` | RX datapath reset (needed after entering or leaving near-end PMA loopback). |
| 5 | `clear` | Zero the fabric and hard PRBS counters and the lock-loss count (the lock state is kept). |
| 6 | `force_err_fab` | Flip bit 0 of the next fabric word (one bit error on the line). |
| 7 | `force_err_hard` | One `TXPRBSFORCEERR` pulse (hard generator; needs txprbssel non-zero). |
| 8 | `snap` | Take a counter snapshot. |

### 0x014 `STATUS`

| Bits | Field | Meaning |
|---|---|---|
| 0 | `tx_done` | Wizard TX reset done. |
| 1 | `rx_done` | Wizard RX reset done. |
| 2 | `gt_powergood` | `GTPOWERGOOD`. |
| 3 | `cdr_lock` | `RXCDRLOCK`. |
| 4 | `txpma_done` | `TXPMARESETDONE`. |
| 5 | `rxpma_done` | `RXPMARESETDONE`. |
| 7:6 | `-` | Reserved, 0. |
| 8 | `cdr_stable` | The reset helper's CDR-stable delay has elapsed. |
| 9 | `fab_locked` | The fabric PRBS checker is locked. |
| 10 | `hard_locked` | The GT's PRBS checker is locked. |
| 11 | `mod_abs` | SFP+ MOD_ABS pin (1 = no module, by the SFF convention; unconfirmed on this carrier). |
| 12 | `rx_los` | SFP+ RX_LOS pin (1 = no light). |
| 13 | `tx_fault` | SFP+ TX_FAULT pin (1 = fault). |

### 0x018 `STICKY`

| Bits | Field | Meaning |
|---|---|---|
| 0 | `tx_done_fell` | TX reset done went 1 to 0. |
| 1 | `rx_done_fell` | RX reset done went 1 to 0. |
| 2 | `fab_lock_lost` | The fabric checker's lock went 1 to 0. |
| 3 | `hard_lock_lost` | The GT checker's lock went 1 to 0. |

### 0x01C `TXCFG`

| Bits | Field | Meaning |
|---|---|---|
| 4:0 | `txdiffctrl` | `TXDIFFCTRL` (reset 0b11000). |
| 9:5 | `txpostcursor` | `TXPOSTCURSOR`. |
| 14:10 | `txprecursor` | `TXPRECURSOR`. |
| 19:15 | `ppm_step` | `TXPIPPMSTEPSIZE`. |
| 20 | `ppm_en` | `TXPIPPMEN`. |
| 21 | `ppm_sel` | `TXPIPPMSEL`. |

### 0x050 `I2C`

| Bits | Field | Meaning |
|---|---|---|
| 0 | `scl_low` | RW: pull SCL low. |
| 1 | `sda_low` | RW: pull SDA low. |
| 8 | `scl_in` | RO: SCL pin level. |
| 9 | `sda_in` | RO: SDA pin level. |

### 0x080 `EYE`

| Bits | Field | Meaning |
|---|---|---|
| 0 | `eyescanreset` | RW. |
| 1 | `eyescantrigger` | RW (level). |
| 8 | `eyescandataerror` | RO: synchronised `EYESCANDATAERROR`. |
