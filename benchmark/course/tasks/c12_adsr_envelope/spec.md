# Envelope generator for a synthesiser voice, behind the test shell

I am building a hardware synthesiser voice on the Nexys A7-100T and need an ADSR (attack, decay, sustain, release) envelope that steps once per sample tick, with linear segments. I want to exercise it entirely from the test shell.

- Inputs: a tick (the sample tick: everything below happens only on a clock where the tick is present; on all other clocks the outputs hold), `gate` (the key is down), and four 16-bit values that are read on every tick: `atk_inc` (the level added per tick during the attack), `dec_dec` (subtracted per tick during the decay), `sus_lvl` (the sustain level) and `rel_dec` (subtracted per tick during the release). Outputs: `level` (unsigned 16 bits) and `state` (3 bits: 0 idle, 1 attack, 2 decay, 3 sustain, 4 release), both showing the result of the latest tick from the clock after it.
- After reset: `level` = 0, `state` = idle, and the gate is considered to have been low. CPU_RESETN does this and clears the loaded values.
- On each tick, in this order of priority:
  1. If `gate` is high and it was low at the previous tick: state becomes attack (the level is not changed on this tick, so a re-trigger starts from the present level).
  2. Otherwise, if `gate` is low, it was high at the previous tick, and the state is not idle: state becomes release (level unchanged on this tick).
  3. Otherwise by state: **attack**: if level + `atk_inc` reaches 65535 or more, the level is 65535 and the state becomes decay; else the level grows by `atk_inc`. **Decay**: if the level is at or below `sus_lvl`, the state becomes sustain (level unchanged); else if level - `sus_lvl` is at most `dec_dec`, the level becomes `sus_lvl` and the state becomes sustain; else the level falls by `dec_dec`. **Sustain** and **idle**: hold. **Release**: if the level is at most `rel_dec`, the level becomes 0 and the state idle; else the level falls by `rel_dec`.
- The block must close timing at 100 MHz.
- Over the shell I set the gate and the four values, give a "tick" command that presents the tick for 1 to 16 consecutive clocks, and read the level and the state back. I will run a script of about 900 ticks (full notes, early releases, re-triggers during decay and release, extreme step sizes and sustain levels, with gaps between the ticks) and compare `level` and `state` after every tick, and some boundary cases (a level that lands exactly on a limit).
- The shell runs at 115200 baud on the USB-UART. The design ID is "ADSR".

Test hooks: top module `c12_adsr_envelope_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters as top-level parameters. There are no other time
constants.
