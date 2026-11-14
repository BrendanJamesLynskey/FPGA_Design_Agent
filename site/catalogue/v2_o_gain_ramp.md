# Click-free gain control (v2_o_gain_ramp)

Domain O (audio), tier T1, Nexys A7-100T. Part of the codec audio path ladder project (brief 78). Draft for the problem catalogue; the task files are in
`benchmark/v2/tasks/v2_o_gain_ramp/`.

## The problem, and where it is used

A gain stage that slides to a new gain (or to silence on mute) by a fixed step per sample instead of jumping.

A volume knob or mute that must not click: every digital audio path, DAW and hearing-aid has one. A sudden step in gain is heard as a click; a constant per-sample slide that stops exactly on the target is the standard fix.

## Hero diagram

A sine wave on a scope; a gain slider. Dragging the slider moves the target marker at once, and the applied-gain marker follows it by equal steps. Below, the output waveform shows a smooth fade for the slide and a visible step for an unsmoothed control.

## Animation plan (driven by `hidden/model.py`)

Use Model.push(x) from hidden/model.py to step one sample at a time: show cur moving toward the target by the step, the product, the floor and the clamp. Run the same samples through a no-ramp variant beside it.

## Interface

Shell registers: GAIN (target, Q4.12), CTRL (mute), SAMPLE (write one sample), OUT, CUR (applied gain), STATUS (still moving, limited). LED[15:0] shows the top bits of the output.

## Acceptance criteria in plain words

The applied gain moves toward the target by RAMP_STEP each sample and stops exactly on it, for gain changes and for mute and unmute; the output is the floored product limited to 24 bits; the status bits report the slide and a limited sample; register map and reset values as listed. Checked with three different RAMP_STEP values, including the default.
