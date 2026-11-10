# CDC soak rig: run plan for the owner

This is the plan for the board runs of the CDC soak rig ([README](README.md)). **Nothing here has been run on the
board yet.** Board runs need the owner's yes, and the owner must be at the board for every first smoke run and for
the first 15 minutes of every soak.

## Before any run

- **Board:** Nexys A7-100T on **wall power** (JP3 = WALL, the board's own 5 V supply, 4.5-5.5 V, centre-positive
  2.1 mm; never a 9 V or 12 V adapter). USB stays connected for JTAG and the UART.
- **Air:** the board flat on the bench in still room air, nothing covering the FPGA. Note the room temperature.
- **Bitstream:** built by `hil/cdc_soak/run_build.sh` (`build/<mode>/rig_<mode>.bit`, not committed). Check its
  `report_power` (`build/<mode>/power.rpt`) first: the total on-chip power must be **at most 2.0 W** (house rule for
  wall power) and the junction temperature it reports at most 85 degC. The committed figures are in
  [results/README.md](results/README.md).
- **Programming is to SRAM only, over JTAG.** The rig never writes the QSPI flash; when the board is power-cycled it
  boots whatever is in its flash, as before.

## Program over JTAG (SRAM only)

The repo's programming script selects the board by its JTAG cable serial, checks the device is an xc7a100t and
refuses any flash request:

```bash
python3 flow/hw_discover.py                              # lists the cable serial and the UART device
vivado -mode batch -nojournal -nolog -source flow/program.tcl \
    -tclargs <cable serial> hil/cdc_soak/build/full/rig_full.bit
```

After programming, LED0 blinks (heartbeat, about 1.5 Hz), LED1 is on during each readout, LED2 is on once the reset
storms are enabled (after 10 minutes), LED3 means the rig stopped itself on temperature.

## Read the counters

```bash
python3 hil/cdc_soak/host/read_counters.py --port /dev/serial/by-id/<the board's UART> --baud 115200 \
    --epoch-s 60 --csv soak_$(date +%Y%m%d_%H%M).csv
```

- The rig sends one `H` line after configuration, then every 60 s of traffic an `E` line (epoch, uptime, Tj and
  VCCINT codes, the measured CFGMCLK frequency, the storm mode) followed by one `C` line per copy (errors, events,
  lock-ups, relocks, saturation). About 22 kB per epoch, 2 s at 115,200 baud; traffic is paused while it is sent.
- The script only reads. It checks every line's CRC-8, appends to the CSV with the host time, and prints one status
  line per epoch. `--file <log> --summary` gives the per-variant totals afterwards.
- Join the CSV with `build/full/delays_copies.csv` (per-copy routed delay and skew) on the copy number.

## Smoke run (1 hour per bitstream, owner present)

1. Program the small build first (`rig_small.bit`, 28 copies), then the full build (`rig_full.bit`, 536 copies).
2. Watch the first `E` line: Tj should read about room temperature plus a few degrees, VCCINT about 1,000 mV, and
   CFGMCLK somewhere in 32,000-98,000 kHz (typically about 65,000).
3. Pass rules for the smoke hour (the rig is broken if any fails):
   - every correct variant (C1-C13): 0 errors and 0 lock-ups (C8-C13 show relocks: one at power-up, and one per
     reset event for the stormed ones; relocks are not errors);
   - the mutants the design predicts to fail in seconds (M2, M3, M5 into a slower clock, M6c, M7, and after the
     10-minute storm delay M8, M9, M10, M11) have non-zero errors or lock-ups;
   - M1, M1b, M4 (near copies), M6a and M6b are recorded as they come: the design predicts 0 or "uncertain" for them.
4. Tj must level off within the hour. Stop the run if it keeps rising past 70 degC.

## Soak (12-24 h)

- Only after a clean smoke run of the same bitstream. Owner present for the first 15 minutes to see Tj level off.
- Run the reader as above with a new CSV; leave it running. Unattended after the first 15 minutes.
- A soak that sees 0 errors on a correct variant supports only a lower bound: MTBF > (copies x hours) / 3 per copy
  at 95 % confidence (design section 0), never a theoretical MTBF.

## Stop rules

Stop the run (close the reader, then power the board off or reprogram it with a blank design) when any of these
happens:

- **Tj reaches 80 degC.** The rig checks this itself: the XADC is read every few milliseconds, and two consecutive
  1-second samples at or above 80 degC stop all traffic, gate off clk_c and send `S,TJ,...` lines (LED3 on). The
  reader exits on an `S` line or on an `E` line at or above 80 degC. The XADC's own over-temperature shutdown
  (125 degC) stays enabled as a last resort.
- **Board power above 2.0 W.** The rig cannot measure the board's power. Before the first run, `report_power` must
  say at most 2.0 W on chip; during the smoke run, if a USB power meter or the bench supply shows the board drawing
  more than its idle draw plus 2.0 W, stop.
- **Two epochs missed** (no `E` line for 2 x 60 s + 30 s): the reader exits; check the board.
- The board resets, browns out or drops off USB: stop and report it.

The reader never reprograms the board, and nothing in this rig writes the flash.
