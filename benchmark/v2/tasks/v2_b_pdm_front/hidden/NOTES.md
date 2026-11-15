# Notes for v2_b_pdm_front

What spec.md does not say:
- the channel rule (M_LRSEL low: data valid from one clock after a falling edge to one clock after the next rising edge);
- the sampling instant (the clock edge at which M_CLK goes high, or the next one) and that sampling at the falling edge or three
  clocks late reads garbage (the bench model drives random bits there);
- the word size (32), bit order (first bit lowest), queue depth (4) and the full-queue rule (drop the new word);
- the stuck threshold (40 equal samples), that the run counter starts at 1 and is cleared when RUN goes 0, that flags are sticky until CLEAR;
- what RUN=0 does (clock low, partial word and run counter discarded, queue and flags kept);
- the register layout and the LED mapping.

Trap: a textbook reader takes the bit at the falling edge.

The bench cannot know exactly how many samples were taken when RUN is switched off (an edge may be in flight): it feeds the model
every edge it saw except the last and resolves that one from the DUT's WORDS count; patterns are built so that no flag threshold
is crossed on that last sample.
