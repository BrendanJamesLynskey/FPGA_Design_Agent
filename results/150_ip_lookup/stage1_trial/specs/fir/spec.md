# Low-pass filter

I want a 32-tap low-pass FIR filter on the Nexys A7-100T for 16-bit signed samples sent over the UART test shell.
The coefficients are loaded at run time over the same link, and I can read the filtered sample back. Use as few
DSP slices as practical because the rest of my design needs them. Reset with the CPU reset button. The design ID
reads "FILT".
