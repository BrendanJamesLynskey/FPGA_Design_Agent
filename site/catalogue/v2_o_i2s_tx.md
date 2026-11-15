# I2S audio transmitter (v2_o_i2s_tx)

Domain O (audio), tier T2, Nexys A7-100T. Part of the codec audio path ladder project (brief 78). Draft for the problem catalogue; the task files are in
`benchmark/v2/tasks/v2_o_i2s_tx/`.

## The problem, and where it is used

The output side of a digital audio link: a committed stereo sample pair sent in standard I2S, with an atomic commit.

Every codec and DAC is fed by an I2S transmitter. The one-bit-clock delay after the word-select edge, the zero padding and changing the data only after a falling edge are what interoperability depends on; an atomic pair update keeps left and right together.

## Hero diagram

Two clock traces and a data trace. Bits of a 24-bit sample march out one bit clock after the word-select edge; a commit button swaps the pair at the next frame start, and a half-written pair is shown not being sent.

## Animation plan (driven by `hidden/model.py`)

Use Model.slot(channel) to step slot by slot: show the staged registers, the pending snapshot, the pair in use and the bits that leave on the data line.

## Interface

Pmod JA pins 1 and 2 are inputs (word select, bit clock), pin 4 the data output. Shell registers: LEFT, RIGHT (staged), CTRL (commit, clear count), FRAMES. LED[15:0] shows the top bits of the sample being sent.

## Acceptance criteria in plain words

Philips I2S timing with zero padding, data changing only after a falling edge, at bit clocks from 8 to 100 board clocks long; a committed pair goes out whole from the next frame start and repeats; staged or half-written pairs are never sent; silence until the first commit and after reset; the LEDs follow the pair being sent.
