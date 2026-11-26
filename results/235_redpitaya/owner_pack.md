# Red Pitaya board visit: the owner's one-page pack (brief 235)

**Nothing on this page has been run.** The agent never touched the Red Pitaya, any board or any instrument. Everything below is for the owner's board visit; the visit is when. Until then no command here is to be run.

Board: the owner's STEMlab 125-14 (original generation, v1.1), hostname `rp-f00c16`, on its own 5 V isolated 2 A or 2.1 A supply (micro USB power input, never a PC port). Image to load: build `@BUILD@` (`fpga.bit.bin`, rebuilt by `tools/rp_shell.py`, not committed). Volatile load only: a power cycle returns the factory image.

## 1. Timing status of the image (from the shell timing study)

@TIMING@

## 2. Wiring (board unpowered while you do it)

1. Unplug the 5 V supply. Check the input jumpers with the board off: IN1 = LV (+-1 V full scale, absolute maximum +-6 V), IN2 = HV.
2. One short lead from OUT1 to IN1 (SMA to SMA). Nothing else on IN1. Never anything above +-1 V into IN1. OUT1 is never left connected to anything unprotected.
3. Power the board only after the lead is fitted. Wait for the LEDs to settle and for `ssh` to answer. (Fitting or removing the lead is done with the board off, every time.)

## 3. The scripts, in this order (both are in `results/225_redpitaya/owner_scripts/`, regenerated for this build by `python3 -m hil.redpitaya_load script <package> --block <name> --slot <n>`; each needs the package folder, `fpga.bit.bin`, `redpitaya_checks.py` and `redpitaya_regs.py`, beside it)

Both blocks are in one image (`rp_freqcount` in slot 7 at 0x40700000, `rp_patgen` in slot 6 at 0x40600000), so either script loads the same file (the second script loads it again: the same image, no change). Each script asks you to type `yes` before it loads, and `rp_patgen` asks a second time before anything moves OUT1.

| Step | Script | What it checks | What pass looks like |
|---|---|---|---|
| 1 | `rp_patgen/load_@BUILD@.sh` | the load (fpga_manager state `operating`, the loader's md5 equals the file's), the block's ID (0xFDA10201), reset values, a scratch register, the clamps of every register, the level register's sign handling, status idle; then, only after your second `yes`, four 0.25 V pulses of 100 kHz on OUT1 (the block cuts any level to 0.5 V), after which OUT1 returns to 0 | every row prints `pass`, the last line is `PASS`; `patgen_output` reads `DONE True, PERIODS_DONE 4 (asked 4), STATUS 0x... (CLAMPED must be 0)` |
| 2 | `rp_freqcount/load_@BUILD@.sh` | the block's ID (0xFDA10101), reset values, scratch, three 0.1 s gates, `STATUS.DONE`, `GATE_ACTUAL` equals the gate, `MEAS_DONE` moves by one per gate | rows `id`, `reset_values`, `scratch`, `gate_len_readback`, `gate_0` to `gate_2` all `pass`, last line `PASS` |

What the second script does **not** judge: the frequency. With OUT1 idle (0 V) the meter reads no edges and the script records `freq_recorded` (not judged); `rp_patgen` makes four pulses only, so OUT1 into IN1 is a check that the pulse arrives, not a frequency reference. A frequency claim needs a known signal into IN1 (a signal generator or the M2K at a value you set, within +-1 V) and the script generated with `--expect-hz <that value>`; the board's own 125 MHz oscillator has no stated ppm, so a ppm result needs the independent instrument. That is the follow-up, not part of this visit unless you choose.

If a script stops with `STOP:` it has changed nothing further; to put the factory image back run the same script with `RESTORE=1` (or power-cycle the board). After the visit, set the lab file's Red Pitaya mode back to `factory_instrument`.

## 4. What to bring back

The two JSON records the scripts write (`rp_check_@BUILD@.json` beside each script, one per run) and the terminal output of both, unedited. The planner turns them into the first hardware results; until then every claim for this image is "built, not run on the board".
