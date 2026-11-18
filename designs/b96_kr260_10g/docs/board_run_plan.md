# Board run plan: the KR260's 10 Gb/s link (brief 96, stage 3)

**No step here has been run.** The KR260 has not been powered or touched for this brief. The planner arranges the session with the owner; the owner
runs the script (`! bash /home/brendan/Claude_sandbox/_handoff/fpga_agent/run_96_stage3.sh <loop length in metres>`). Terms: PMA loopback = the
receiver listens to its own transmitter inside the transceiver (no light); PCS = physical coding sublayer (64b/66b, scrambler, block lock);
E = the echo time (a probe frame out of the transmitter and back to the receiver); L = the trading loop (feed frame out, order in); D = the
digital decision time from the start of the feed frame's reception to the start of the order's transmission.

## 0. Hardware state and what is not assumed

| Item | State | Source |
|---|---|---|
| KR260, own 12 V adapter, fan | the owner's | board rules (house rules) |
| 10Gtek 10G-LR SFP+ module (1310 nm) and an OS2 LC loopback lead in cage J24 | fitted by the owner, 2026-11-13 | brief 96 hardware paragraph, KB `kr260-sfp-plus` |
| A 10G NIC and cable (ConnectX-4 Lx MCX4121A-ACAT recommended) | **not bought** (owner, 2026-11-16: "I won't purchase these yet. Remind me later") | brief 96 |
| The reference clock's source and frequency, the control pins' polarity | **unconfirmed**; step 1 tests them with the laser off | `boards/kr260/board.yaml`, design.md section 1 |
| KR260 entry in `~/.config/fpga_design_agent/boards.yaml` | **missing**: `flow/hw_discover.py` must be run once with the board connected (a planner-approved board step) | the file has only the Nexys A7 |
| `flow/program.py` support for the K26 (PS idle, JTAG-only PL load) | **unverified**: 56A's plan listed it as a question for the planner; stop and ask if the load fails | `reports/56a_serdes_report.md` |

## 1. Rules for the session

- One board job at a time through `_handoff/board.lock` (the script takes it, and releases only its own `96:` text).
- SRAM only. No flash, eFUSE, BBRAM, SD or eMMC. Wall power; at most 2.0 W predicted (the build reports the figure in `results/b96/build_b`); junction at most 85 C.
- **Laser:** class 1; never look into the port or a fibre end while the module is powered; dust caps on when unplugged. `tx_disable` resets to 1 (laser off);
  the bench turns it on for the polarity check (a fraction of a second) and for the run, and turns it off at the end and on any error.
  LR optics need no attenuator back to back (the receiver's range is stated in the report from the module's datasheet and the measured DDM RX power, not assumed).
- Stop at the first failure and report it; do not try anything the plan does not list.

## 2. Steps (loopback part: the script runs 1 to 4)

1. **Polarity and pins, laser off.** After loading: read `ID` (0x96A00001) and `BUILD` against the build's manifest. Read `GT_STAT`: expect `MOD_ABS` 0 (module present),
   `RX_LOS` 1 (no light), `TX_FAULT` 0. Read the module over I2C (vendor, part number, wavelength; the I2C pins are AMD-board-file confirmed; the module may answer
   with the laser off). Write `GT_CTRL.TX_DISABLE = 0` for 100 ms: `RX_LOS` must fall (light through the loop), then 1 again with the disable back on.
   If it does not, the pin functions or the polarity differ from the open-source example: **stop**, read the carrier schematic.
2. **Reference clock.** With the laser off, `GT_RESET.all`; `TX_DONE` and `RX_DONE` must rise within 5 s. They depend on the QPLL locking to the board's reference at the 156.25 MHz settings;
   if `TX_DONE` never rises, the reference is not 156.25 MHz (design.md section 1: the fractional-N alternative is a new build, not a guess). Stop and report.
3. **Link up in the loop.** Laser on; `RX_DONE`, `CDR lock`, then `PCS BLOCK_LOCK`; record the clocks from RX reset release to lock (`RXV15`). Read the module's diagnostics
   (temperature, Vcc, TX bias, TX power, RX power) at the start and the end, and state whether RX power is inside the module's receiver range (the datasheet's figures, cited).
   Record die temperature and the rails from the SYSMON window at the start, the end and once a minute (operating conditions are evidence, house rule).
4. **Echo and trading loop** (pre-registered in design.md section 6):
   - E: `GEN_TRADE_CTRL` kind 2 (probe), count 5, interval 3000; E from the snapshot (`TXV16..19`).
   - L: ARM, kind 1 (feed, price 99.50 below the 99.75 threshold), the rule fires, the order loops back; L from `TXV20..23`; D' = `TXV24`.
   - **D = L - 2E** (two passes through the link), reported with the uncertainty below.
   - **At least 100 link restarts** (RX datapath reset, wait for lock, repeat steps E and L): min, max, median and histogram of E, of L, and of the lock clocks per restart.
   - **Safety verdict (brief 97B):** every restart keeps its full TX and RX counter snapshot; `stage3.json` carries `safety` with `ok` true only when `poisoned`, `dropped`, `underrun`, `late`, `stale`, `bad`, `err`, `toolong` and `order_bad` are 0 in every restart and `n_order`, `fired` and `order_ok` all equal the count configured (5 per restart). Since brief 97C CMD bit 0 clears `stale` and `go` too and the order number restarts with every restart of either side, so each restart's snapshot is judged as read (builds before 97C accumulate `stale` and have no `order_ok`/`order_bad` words, and fail this verdict). The counters are cleared after the link locks, so they judge the run traffic, not the relock transient. `order_ok` and `order_bad` (RXV16, RXV17) are the hardware's own content check: each returned order is compared with the decision (side, instrument, price, quantity, number, length, FCS); see register_map.md, "What clears what".
   - Timestamp clock and uncertainty: one TX-domain counter; RX events cross by an `xpm_cdc_pulse`; each RX stamp is late by a fixed latency (measured in simulation, `docs/what_we_found.md`) plus up to **one clock (6.2 ns)**
     of phase. Variation in E and L between restarts therefore has a floor of one clock; larger variation comes from the GT's RX buffer and the gearbox alignment per link-up.
   - Subtract: the fibre (measured length x about 4.9 ns/m, group index 1.468 stated, not measured, one way each pass) and the optics' delay, which is **unknown** unless the module's datasheet gives it (state which).
   - Optional, if the first distribution shows the GT's RX buffer matters: rebuild with the RX buffer bypassed (`RX_BUFFER_MODE 0`, the Wizard's alignment procedure) and measure the second distribution.
   - **What this does not prove:** a PCS talking to itself accepts its own symmetric mistakes (a wrong scrambler seed convention, a mirrored bit order). Interoperability needs the NIC (steps 5 to 8).

## 3. NIC steps (5 to 8; after the owner buys a card and cable; not scripted for the loopback session)

5. Link: card in the PC's CPU-attached x16 slot (the HP Elite 7500 MT is full height: check the bracket), cable between the card and J24 (or a second LR module in the card with the OS2 patch lead; the card must accept third-party optics).
   `ethtool <if>` must show 10000Mb/s and link detected; set the bench addresses (192.168.58.0/24; board 192.168.58.10, PC 192.168.58.15 by default).
   Run traffic for a stated number of bits: the PCS counters (`RXV1..6`, `RXV9`) and the card's `ethtool -S` error counters. **10^12 bits is 100 s at 10 Gb/s**; a bound under 3x10^-12 at 95% needs 10^12 error-free bits (the "3/N rule"), reported as a bound with its bit count, never "zero errors".
6. ARP and ping through the endpoint. The 58A path answers ARP; **this design has no ARP or ICMP responder yet** (design.md section 2.5): add `arp_icmp64` before this step or use a static neighbour entry on the PC (`ip neigh replace 192.168.58.10 lladdr 02:00:00:00:58:0a dev <if>`) and treat ping as not tested.
7. The mock venue over 10 Gb: `host/nic_timestamp.py --iface <if> --board-ip 192.168.58.10 --bind-ip 192.168.58.15 --enable-hw --n 100` (needs root for the hardware-timestamp ioctl; an owner action).
   Wire-to-wire = the card's RX stamp of the order minus its TX stamp of the feed packet. Compare with the loopback figure (L), after subtracting both fibres and the card's own figures with their sources.
8. State which numbers come from the NIC (its timestamp resolution and accuracy, from its documentation) and which from the FPGA (clock cycles of 6.2058 ns, with the uncertainty above).

## 4. Pass criteria written before the run

- Step 1: the polarity check passes, or the run stops (the report says what differs).
- Step 2: `TX_DONE` and `RX_DONE` within 5 s.
- Step 3: block lock within 1 s of the laser coming on; zero `type` errors and zero lock losses over 60 s in the loop; RX optical power inside the module's stated receiver range (otherwise state the errors found, no attenuator was bought).
- Step 4: 100 restarts each lock; E and L recorded for each; D computed from the medians of the per-link minima, with the whole distribution alongside.
- Nothing is called a pass that was not measured; a failed check is reported with its number.

## 5. Files

`_handoff/fpga_agent/run_96_stage3.sh` (the owner's script), `host/b96_bench.py` (sequence, restart distribution, arithmetic; tested against a fake board), `host/b96_regs.tcl` (register
access over JTAG), `host/sfp_i2c.py` (module EEPROM and DDM; tested against a slave model), `host/nic_timestamp.py` (NIC timestamps; plumbing tested on `lo` with software stamps),
`docs/register_map.md`. Results go to `results/b96/hw/<timestamp>/stage3.json`.
