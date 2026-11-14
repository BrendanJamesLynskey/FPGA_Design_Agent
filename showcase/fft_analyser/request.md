# Request: a streaming spectrum core with windowing and averaging

(What the customer writes. This is the only text the FPGA Design Agent is given for the whole project.)

I am building a spectrum analyser on the Nexys A7-100T and I need its heart first: an FFT core that never stops. In
simulation first, then on the board with a converter later.

What I need:

- An FFT that takes one 16-bit sample on every clock, with no gaps, and gives a spectrum back for every frame. Frame
  sizes 64, 256 and 1024, chosen by a setting.
- A window multiplied in before the transform: none, Hann or Hamming, chosen by a setting.
- Power spectra averaged over 1, 2, 4, 8 or 16 frames, chosen by a setting; the result is the power of each of the
  lower half of the bins, in natural frequency order.
- Fixed-point arithmetic that fits in 16 bits at every stage, scaled so that nothing can overflow. I want the
  numbers to agree with a floating-point FFT to within a couple of least-significant bits, and I want a clean tone to
  show a spurious-free range of at least 70 dB. If any value hits a limit, tell me.
- Throughput: a run of K frames of N samples should take just over N times K clocks, not more. I want to read how
  many clocks it took.
- For now the samples come from a small memory that I fill and the core replays; later they will come from a
  converter. I read the results over the UART link the board already has.

Please ask me about anything that is not decided here: the exact window tables, the scaling, how the frames are formed
from the memory, the rounding, and the register layout.
