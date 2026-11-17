# Request: the Nexys A7's microphone as a 48 kHz audio source

(What the customer writes. This is the only text the FPGA Design Agent is given for the whole project.)

I have a Nexys A7-100T. Its on-board digital microphone gives a one-bit stream, and I want it as ordinary audio that I
can record and look at: 16-bit samples at about 48 kHz, good enough to listen to and to measure. I want to build it
entirely in the FPGA from the 100 MHz clock, with no PLL, and read the samples over the UART link the board already
has.

What I need:

- The microphone's clock from the 100 MHz clock, a little over 3 MHz. Use the microphone's left channel.
- A decimation chain that brings the bit stream down to the audio rate. I expect a CIC filter first, then two
  half-band stages that each halve the rate, then a short FIR that lifts the top of the band, and a DC blocker at the
  end. The overall reduction is 64 (so the output is 48.828 kHz, which is 100 MHz divided by 2048; I do not need
  exactly 48 kHz). Keep the arithmetic exact, keep every number inside 16 bits, and stop at the limit instead of
  wrapping if a value ever reaches it.
- Quality, stated as numbers I can check:
  - flat to within 1 dB from 200 Hz to 15 kHz;
  - tones that would fold into 0 to 15 kHz from above 40 kHz at least 35 dB down;
  - at least 70 dB signal-to-noise ratio for a tone 6 dB below full scale, in 100 Hz to 15 kHz;
  - a latency I can state in samples.
- A memory that records the first 64 output samples after I ask, so that I can read them back at the UART's pace. I
  want to see on the LEDs that the chain is running, that a recording is complete and whether anything hit a limit.
- I want to measure it on the board: the microphone's own noise in a quiet room, and the level of tones played from my
  PC's loudspeaker across the band. I know the loudspeaker and the room limit what that tells me; say so in the
  results.

Please ask me about anything that is not decided here: the exact coefficients, the scaling between stages, the
register layout, and what the checks should be.
