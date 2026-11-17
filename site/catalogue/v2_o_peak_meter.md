# Peak meter with hold and a clip counter (v2_o_peak_meter)

Domain O (audio), tier T1, Nexys A7-100T. Part of the codec audio path ladder project (brief 78). Draft for the problem catalogue; the task files are in
`benchmark/v2/tasks/v2_o_peak_meter/`.

## The problem, and where it is used

The level meter of a recording desk: a reading that jumps to a loud sample, holds, then falls, and a count of samples that hit the end of the range.

Every mixer, DAW and audio interface has a peak meter and a clip light. Getting the hold, the fall, the magnitude of the most negative sample and the clip rule right is what separates a trustworthy meter from a decorative one.

## Hero diagram

A vertical bar that leaps up on a loud sample, stays for the hold time, then drains; a clip counter ticks beside it each time the waveform touches the top or bottom of a 24-bit range.

## Animation plan (driven by `hidden/model.py`)

Use Model.push(x) to step sample by sample: show the magnitude, the compare with the reading, the hold timer counting down and the fall by a thirty-second. A second panel replays a run of full-scale samples to show the clip count.

## Interface

Shell registers: SAMPLE, PEAK, CLIPS, HOLD, CTRL (clear peak, clear clips), STATUS (holding). LED[15:0] shows the top bits of the reading.

## Acceptance criteria in plain words

The reading rises at once to a louder or equal magnitude and reloads the hold; after the hold it falls by a thirty-second (at least one) per sample to zero; the most negative sample has magnitude 0x800000; every sample at either end of the range counts as a clip; the two clears are independent; hold time and clip count use their full 16 bits.
