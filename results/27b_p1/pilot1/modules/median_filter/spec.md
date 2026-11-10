For each active output pixel, compute the median independently for each RGB channel over the 3 x 3 active-picture
neighbourhood. At active-picture edges, extend the nearest active pixel to fill missing neighbourhood positions.
Carry the timing and stable indications through the filter so they stay aligned with the corresponding filtered
pixel. Sustain one beat per clock and one output beat per input beat; latency is H_TOTAL + 2 clock cycles.
