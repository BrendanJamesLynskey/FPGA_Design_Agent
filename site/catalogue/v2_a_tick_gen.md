# Programmable tick generator (v2_a_tick_gen)

Domain A, drill tier, Nexys A7-100T. Survey row: A12 (clock divider, tick and enable generator). Draft for the problem catalogue; the task files are in
`benchmark/v2/tasks/v2_a_tick_gen/`.

## The problem, and where it is used

Produce a one-clock enable pulse every N clocks, with N written over the shell: exactly N apart, not roughly, N = 1 meaning every clock, and N = 0 meaning no ticks. Count the ticks (32 bits) and let the user clear the count. A second LED flips on every tick so the ticks can be seen at half rate.

Where it appears: Every FPGA design that needs a slow event (a millisecond tick, a sample-rate enable, a UART baud tick, a display refresh) from the fast board clock without making a second clock. Using an enable rather than a divided clock keeps the whole design in one clock domain.

## Hero diagram

A fast clock drawn as a dense comb of edges; under it a counter bar filling from 0 to N-1 and wrapping; at each wrap a single narrow tick pulse is drawn, and a toggle flip-flop beneath it makes a square wave at half the tick rate. A side-by-side faded panel shows the textbook divided clock with 50 per cent duty, to show why it is a different thing.

## Animation plan (driven by `hidden/model.py`)

Drive Model.clock() once per animation step. The counter bar is the model's cnt, the tick lamp is the returned tick, the toggle lamp is led1. A slider sets DIV (write_div), including 0 and 1. A tick counter shows the TICKS register as the model adds ticks.

## Interface

Output LED[0] is the tick, LED[1] flips on each tick. Shell registers: DIV (read and write, 16 bits, 0 = stopped, 8 at reset) and TICKS (32-bit count, any write clears it).

## Acceptance criteria in plain words

Ticks are exactly DIV clocks apart and one clock wide. DIV = 1 ticks every clock and DIV = 0 stops them. LED[1] changes exactly where a tick starts. TICKS counts every tick in 32 bits and any write clears it. DIV keeps 16 bits. Compared clock by clock with the model after each DIV write.
