# Priority encoder (v2_a_prio_enc)

Domain A, drill tier, Nexys A7-100T. Survey row: A22 (priority encoder, one-hot, decoder, mux). Draft for the problem catalogue; the task files are in
`benchmark/v2/tasks/v2_a_prio_enc/`.

## The problem, and where it is used

Use the 16 slide switches as requests; the highest-numbered request wins and is shown as one lit LED. A mask register, set over the shell, makes chosen requests invisible. The shell also gives the winner's number and a valid flag. The interview question is what the number is when nothing is requested.

Where it appears: Interrupt controllers, bus and memory arbiters, first-set-bit instructions in processors, and floating-point normalisation. A fixed-priority encoder is the simplest arbiter.

## Hero diagram

Sixteen switch icons in a row feeding a column of gates that cascade from bit 15 down to bit 0; each gate lets its request through only if nothing above it is active and its mask bit is clear. The winning line lights and drives both a one-hot LED row and a four-bit number display with a valid lamp.

## Animation plan (driven by `hidden/model.py`)

Set the switch word and mask in the model (Model.req, Model.mask) and call encode(). Animate the inhibit chain from the top: each gate lights red once something above wins, and the winner's index and grant vector appear. Random switch patterns replay so the viewer can watch the winner change.

## Interface

Inputs SW[15:0]. Output LED[15:0] is the one-hot winner. Shell registers: REQ (read, synchronised switches), MASK (read and write) and WINNER (read: index in bits 3:0, valid in bit 4).

## Acceptance criteria in plain words

The highest-numbered unmasked request wins and its LED alone is lit. A masked request is ignored. With nothing requested the LEDs are off, valid is 0 and the index reads all ones. The LED follows the switches by three clocks. Register map and reset values as listed.
