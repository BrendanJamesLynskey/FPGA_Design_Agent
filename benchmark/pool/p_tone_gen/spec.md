# Tone generator

I want to play a scale on the board's audio output with the switches.

- SW[2:0] pick one of eight notes, a rising scale from note 0 (lowest) to note 7. SW[3] raises the note by one
  octave. The output is a plain square wave on AUD_PWM.
- SW[15] up turns the sound on: it switches the audio amplifier on with AUD_SD and starts the tone. With SW[15]
  down the amplifier is off and AUD_PWM is held low.
- Changing the note while it plays should not cut a half-wave short: the half-wave in progress finishes first.
- LED[2:0] show the note in use, LED[3] the octave, LED[15] whether the sound is on.
- Over the test shell (USB-UART, 115200 baud) I can read the note in use, the half-period in clocks, and a count of
  how many times the output has flipped. The design ID is "TONE".

Test hooks: top module `p_tone_gen_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `NOTE_BASE` (the half-period of the lowest note in
clocks) as a top-level parameter.
