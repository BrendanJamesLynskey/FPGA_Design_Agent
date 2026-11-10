# Serial pattern spotter (v2_a_seq_detect)

Domain A, drill tier, Nexys A7-100T. Survey row: A08 (sequence detector). Draft for the problem catalogue; the task files are in
`benchmark/v2/tasks/v2_a_seq_detect/`.

## The problem, and where it is used

Watch one serial bit stream, one bit per clock, and flag every time the last four bits are 1, 0, 1, 1 (oldest first). Count the hits, and let the user clear the count. The catch is overlap: the stream 1,0,1,1,0,1,1 holds two hits, because the second shares its first bits with the end of the first.

Where it appears: Frame and preamble detection in serial links, start-of-packet markers, bit-pattern triggers in logic analysers and protocol decoders. It is the standard first exercise for finite-state machines and shift-register detectors.

## Hero diagram

A row of four boxes (the history) sliding along a strip of bits, with the pattern 1,0,1,1 drawn under them. When the boxes line up with the pattern the strip flashes a hit lamp and a counter above ticks. A second, ghosted copy of the strip shows the same stream through a non-overlapping detector that drops the second hit, so the difference is visible.

## Animation plan (driven by `hidden/model.py`)

Step the golden model one bit per animation tick with Model.push(bit). The viewer sees: the incoming bit enter the two-flop synchroniser, the four-bit history shift, the compare against the pattern, and the registered hit lamp lighting two ticks after the last bit (the model's LATENCY). COUNT is the model's count. A preset stream (1,0,1,1,0,1,1,0,1,1) plays by default and the viewer can toggle bits to try their own.

## Interface

Input JA1 (one bit per clock). Output LED[0] is a one-clock hit pulse. Shell registers: COUNT (read, any write clears) and LEVEL (read, the synchronised input level). Reset clears the count.

## Acceptance criteria in plain words

LED[0] is high for exactly one clock per match and at no other time, two clocks after the last bit. Matches may overlap. The count is 16 bits wide and a write to it clears it. The register map and reset values are as listed. Checked cycle by cycle against the model on directed, near-miss and random streams.
