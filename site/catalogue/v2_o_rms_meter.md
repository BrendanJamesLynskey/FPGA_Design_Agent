# RMS level meter (v2_o_rms_meter)

Domain O (audio), tier T1, Nexys A7-100T. Part of the codec audio path ladder project (brief 78); development task since the family re-draw of brief 83. Draft for the problem catalogue; the task files are in
`benchmark/v2/tasks/v2_o_rms_meter/`.

## The problem, and where it is used

A level meter that reports the effective (root mean square) size of the audio over a block of samples, exactly, for the full 24-bit range.

Loudness meters, compressors and recording levels all work from RMS rather than peak, because RMS follows how loud the signal sounds and a single spike does not move it much.

## Hero diagram

A waveform with a block outlined; the squared samples accumulate, the mean is taken and a square root gives one bar reading per block. A peak marker beside it shows how differently a spike reads.

## Animation plan (driven by `hidden/model.py`)

Use the model in hidden/model.py to push one sample at a time: show the running sum of squares, the block counter and the reading that appears when the block completes and is then held.

## Interface

Shell registers: SAMPLE (write one sample), block position, reading, block count and a control to abandon the block in progress. LED[15:0] shows the upper 16 bits of the reading.

## Acceptance criteria in plain words

One reading per completed block of 2 to the power RMS_LOG2 samples, exact for every input including a block at the most negative value, held until the next block completes; the abandon control restarts the block without touching the last reading; register map and reset values as listed.
