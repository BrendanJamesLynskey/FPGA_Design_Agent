# I2S audio receiver (v2_o_i2s_rx)

Domain O (audio), tier T2, Nexys A7-100T. Part of the codec audio path ladder project (brief 78); development task since the family re-draw of brief 83. Draft for the problem catalogue; the task files are in
`benchmark/v2/tasks/v2_o_i2s_rx/`.

## The problem, and where it is used

The input side of a digital audio link: a codec sends stereo audio over word select, bit clock and serial data in standard I2S, and the receiver recovers the 24-bit signed samples.

Every codec, microphone and DAC board uses this format; the one-bit delay after the word-select edge and the stopped-clock gaps are what make it easy to get wrong.

## Hero diagram

Three traces (word select, bit clock, data) with the sample bits lighting up as they are captured into the left and right registers, and the frame counter ticking.

## Animation plan (driven by `hidden/model.py`)

Use Model.slot(ch, sample) from hidden/model.py to feed one channel slot at a time and show the bits captured, the latest left and right sample and the frame count.

## Interface

Pmod JA inputs: word select, bit clock, serial data. Shell registers: latest left and right sample, frame count, a control to clear the count. LED[15:0] shows the top 16 bits of the left sample.

## Acceptance criteria in plain words

Each channel's 24-bit signed sample is captured after its last bit, left and right kept apart, the frame count advances per stereo frame and clears on request, with the bit clock stopped between bursts; register map and reset values as listed.
