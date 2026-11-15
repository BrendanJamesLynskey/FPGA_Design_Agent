# A stereo audio path on the ZedBoard, with gain, mute and metering

*This is the plain-English request the FPGA Design Agent receives for the project (brief 78). It is written as a customer
would write it. The formal specification the planner holds is [spec.yaml](spec.yaml); the agent is given only this text and
answers its own clarifying questions through the usual interview.*

I want a stereo audio path on the ZedBoard (the board I call "bump", Zynq-7020), from the line input to the line output and
the headphones, at 48 kHz and 24 bits. The board's audio codec, the ADAU1761, does the conversion; the programmable logic does
everything in between.

**The path.** Line in goes into the codec. The codec sends the samples to the logic as I2S, the logic processes them and sends
them back as I2S, and the codec turns them into the line output and the headphone output. The codec generates the bit clock and
the left/right clock; the logic generates the codec's master clock.

**What the logic does to the sound, per channel.**
- A gain and a mute, set from the processor.
- Gain changes and the mute must never click. When I change the gain or press mute, the gain slides to its new value, by
  the same small step every sample, and lands exactly on it. The step size is part of your specification; I want a full
  swing from silence to unity to take a few milliseconds.
- If the result is too big for 24 bits it is limited, not wrapped round.

**What the logic measures, per channel, on the signal after the gain and mute.**
- A peak meter that jumps up to a loud sample at once, holds for a time I can set, then falls away.
- An RMS meter over a block of samples, so I can see how loud it sounds.
- A clip counter, so I know if the signal ran out of range and how many times.

**How I use it.**
- The processor (bare-metal, no operating system) reads and writes all of this over AXI4-Lite: gains, mutes, the hold time,
  clearing the meters, and reading the peaks, RMS values and clip counts. Use the house register conventions, generate the
  register block with the project's register generator, and give me a datasheet for it that says what every read, write and
  unmapped address does.
- The processor sets up the codec over I2C at start-up (or you may use a small I2C master in the logic: choose one and tell me
  why). Line-out starts at a low level; nothing loud comes out of the headphones by surprise.
- The audio clock domain and the processor's bus clock domain are different. The crossings must be through documented
  synchronisers, and the clock-domain-crossing check must pass.

**What I will check on the board**, with my PC's line output and line input cabled to the board:
- the frequency response;
- the distortion plus noise (THD+N) of a 1 kHz tone;
- the noise floor;
- the crosstalk between the channels;
- the delay from the analogue input to the analogue output, in samples;
- how much click a gain step makes, compared with a build that has no smoothing.

I know that the codec and my PC's interface have limits of their own. If a measurement is at one of those limits, say so and
name the limit, rather than reporting it as the design's.

Please write what you built so that another engineer can take it over: what it does, its parameters, how to build and run it,
what you verified and measured, what is not done, and what to do next.
