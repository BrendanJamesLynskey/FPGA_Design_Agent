# P4 hidden full spec (oracle only): answers the user would give about the 32-tap FIR
Written for brief 227 as the user's answers; it adds facts the request leaves open and carries no test values.
- Reset: both FIFOs empty, the filter history zero, SAT_COUNT 0, SAMPLES_DONE 0, STATUS 0, CTRL 0.
- RUN while BUSY is ignored. RUN with an empty input FIFO does nothing and BUSY stays 0. CLEAR while BUSY stops the run at once and clears everything; CLEAR wins over RUN written in the same clock.
- The output FIFO has 1,024 words. If a run would produce more outputs than there is room in the output FIFO, the run processes only as many samples as there is room for and leaves the rest in the input FIFO; SAMPLES_DONE counts what was processed. Nothing is dropped or overwritten.
- IN_PUSH with a full input FIFO is ignored; the sample is lost and not counted. IN_PUSH while BUSY is accepted if there is room and is processed in the same run if it arrives before the FIFO has been drained, else in the next run.
- OUT_POP of an empty FIFO returns 0 (bit 31 clear) and removes nothing.
- The 16-bit input is two's-complement. The sum is exact in a 40-bit accumulator; rounding adds 0x4000 before the shift. Saturation clips to -32768 and +32767 and increments SAT_COUNT once per saturated output; SAT_COUNT is 32 bits and wraps.
- The first output of a run corresponds to the first input of that run (no latency visible to the host: outputs appear in the output FIFO in input order, one per input). The history carries over between runs until CLEAR.
- STATUS counts are the number of samples now in each FIFO. SAMPLES_DONE is 32 bits and wraps.
- The datapath clock is 250 MHz derived from the 25 MHz board clock; the FIFOs cross between the bus clock and the datapath clock with asynchronous FIFOs; STATUS and counters are read in the bus clock domain through a documented crossing.
