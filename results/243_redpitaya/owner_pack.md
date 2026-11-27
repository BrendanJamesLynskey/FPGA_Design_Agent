# Red Pitaya board visit: the owner's one-page pack (brief 243; replaces the brief 235 pack)

**Nothing on this page has been run.** The agent never touched the Red Pitaya, any board or any instrument. Everything below is for the owner's next board visit; until then no command here is to be run.

Board: the owner's STEMlab 125-14 (original generation, v1.1), hostname `rp-f00c16`, on its own 5 V isolated 2 A or 2.1 A supply (micro USB power input, never a PC port). Image to load: build `d2f617ca` (`fpga.bit.bin`, md5 `4b74fa654ad90b26fb81509e9eac786d`, 993,360 bytes). Volatile load only: a power cycle returns the factory image. Writing files to the SD card is allowed by the owner (2026-11-27) but nothing here needs it.

## 1. What went wrong last time, in two sentences

Build `170300fd` loaded fine, but every read of our two blocks returned 0: the vendor's clock-crossing bridge reads a slot's answer two to three clocks after the block raises it, and our blocks (following the documented one-cycle convention) had already dropped it. Build `d2f617ca` puts a small adapter (`rp_bus_adapt`) in front of each block that holds the answer; in simulation, with the vendor's own bridge, both IDs and scratch registers now read back correctly ([README](README.md), section 1 and 2).

## 2. Timing status of the image (be aware before you load)

Build `d2f617ca` (Vivado 2026.1, vendor shell commit 728a4f37e9, our constraints overlay, Explore directives): **setup timing is NOT met: WNS -0.084 ns, 4 failing endpoints, all in `rp_freqcount`'s `span` register; hold met (+0.056 ns).** The image still loads and the bus, ID, scratch and `rp_patgen` paths are not on that path; a frequency reading from `rp_freqcount` is provisional until the path is repaired (a follow-up, not done). The same exclusions as before apply: the vendor's own generator, oscilloscope and the two deep-memory AXI bridges are left out of the timing analysis, are not used by this image and are not claimed to work. Details: [README](README.md), section 3.

## 3. Wiring (board unpowered while you do it)

1. Unplug the 5 V supply. Check the input jumpers with the board off: IN1 = LV (+-1 V full scale, absolute maximum +-6 V), IN2 = HV.
2. One short lead from OUT1 to IN1 (SMA to SMA). Nothing else on IN1. Never anything above +-1 V into IN1. OUT1 is never left connected to anything unprotected.
3. Power the board only after the lead is fitted. Wait for the LEDs to settle and for `ssh` to answer. (Fitting or removing the lead is done with the board off, every time.)

## 4. The scripts (copies ready in `~/Claude_sandbox/_bench/rp_visit_d2f617ca/rp_patgen/` and `.../rp_freqcount/`; sources in [owner_scripts/](owner_scripts/))

Each folder holds `fpga.bit.bin`, the script `load_d2f617ca.sh`, `load_fda.sh` (the volatile loader that the script copies to the board), `redpitaya_checks.py` and `redpitaya_regs.py`. Both blocks are in one image (`rp_patgen` in slot 6 at 0x40600000, `rp_freqcount` in slot 7 at 0x40700000), so either script loads the same file. Each script asks you to type `yes` before it loads, and `rp_patgen` asks a second time before anything moves OUT1.

What each script does, in order (new since 235 in bold):
1. Runs every board command after sourcing the board's `/etc/profile` with `/opt/redpitaya/sbin` and `/opt/redpitaya/bin` on PATH.
2. Copies the files to `/tmp/fda_load/` and **loads with `load_fda.sh`** (the bitstream copied to `fpga.bin`, which the v0.94 device tree asks for; `overlay.sh <name> <path>` on OS 3.00 ignores the path).
3. Checks `fpga_manager` is `operating`, the loader's md5 equals the file's, **and the loader's log has no `fail`**.
4. **Reads the ID register of both blocks (slot 6 and slot 7) once. If either reads 0 it stops and names the slot ("its ID register reads 0, so the block does not answer the system bus"); if it reads another value it stops too. Nothing further runs, nothing is written to the blocks, OUT1 is not touched.**
5. Only then: the block's own checks (reset values, scratch, the clamps and sign handling for `rp_patgen`; three 0.1 s gates for `rp_freqcount`), and, after your second `yes`, four 0.25 V pulses of 100 kHz on OUT1.

| Step | Script | What pass looks like |
|---|---|---|
| 1 | `rp_patgen/load_d2f617ca.sh` | the ID lines for both slots, then every row `pass` and the last line `PASS`; `patgen_output` reads `DONE True, PERIODS_DONE 4 (asked 4), STATUS 0x... (CLAMPED must be 0)` |
| 2 | `rp_freqcount/load_d2f617ca.sh` | rows `id`, `reset_values`, `scratch`, `gate_len_readback`, `gate_0` to `gate_2` all `pass`, last line `PASS` |

If a script stops with `STOP:` it has changed nothing further; to put the factory image back run the same script with `RESTORE=1` (it runs `overlay.sh v0.94`) or power-cycle the board. After the visit, set the lab file's Red Pitaya mode back to `factory_instrument`.

## 5. What to check first at the visit

1. The ID lines, before anything else: slot 6 `0xfda10201`, slot 7 `0xfda10101`. If both read right, the 2026-11-27 fault is fixed on the board; say so with the two lines.
2. If an ID still reads 0, the script has already stopped; bring back the terminal output unedited and do not retry blind. The planner decides the next step; it is not a blind rebuild.
3. If an ID reads right but a register reads back wrong, note which register and the value; that is a different fault from last time.
4. `rp_freqcount` frequency results are provisional (setup timing in its span register missed by 84 ps; section 2).

## 6. What to bring back

The JSON records the scripts write (`rp_check_d2f617ca.json` beside each script, one per run) and the terminal output of both, unedited. The planner turns them into the first hardware results; until then every claim for this image is "built and simulated, not run on the board".
