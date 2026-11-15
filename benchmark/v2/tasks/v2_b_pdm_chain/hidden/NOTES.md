# Notes for the sibling probe tasks (level L2)

What spec.md does not say:
- the stages in order and their arithmetic (CIC 3 x 16 with two fill outputs dropped, scale x8, two half-band decimators, the nine-tap FIR, the DC blocker), with the exact coefficients and rounding;
- the sampling rule of the microphone (as in the sibling probe tasks) and M_CLK = 100 MHz / 32 in the product (CLK_HALF is a parameter);
- the output rate 48.828125 kHz (not 48 kHz) and the latency (audio sample j after PDM sample 96 + 64 j);
- the capture rules: ARM only when RUN is 0, DONE and CAP persist after RUN goes 0, CAP reads 0 until DONE, a partial capture restarts at the next RUN start;
- SAT (sticky, cleared at RUN start) and COUNT;
- the register layout and the LEDs;
- the product numbers: passband, alias attenuation, SNR (all measured on the model, with margin).

Trap: a chain that keeps the two fill outputs of the CIC.

The product numbers are checked on the model, which the bit-exact capture ties the design to; the design itself is not asked to reproduce them
from 64 samples (a 64-sample record cannot resolve 70 dB). ELAPSED-style timing is not specified for this task.
Reads of SAT after the run include samples after the capture completed (the stream continues until the bench stops RUN); the stimuli
used where SAT is asserted are stationary so the answer is the same.

Also not reachable by the bench: saturation inside the DC blocker alone and SAT raised by one later stage only (every stream a PDM bit
source can make that limits the half-band or FIR stages also limits the scale stage first; a model run over all-ones, all-zeros, tones and
random bits never limits the DC blocker). A DC blocker that wraps or feeds back an unlimited value is therefore not detectable here.
