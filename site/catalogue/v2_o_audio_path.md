# Stereo audio path with metering (v2_o_audio_path)

Domain O (audio), tier T2, Nexys A7-100T. Part of the codec audio path ladder project (brief 78). Draft for the problem catalogue; the task files are in
`benchmark/v2/tasks/v2_o_audio_path/`.

## The problem, and where it is used

The digital heart of an audio path: I2S in, gain and mute with click-free smoothing, peak, RMS and clip meters, I2S out.

The processing core of an audio interface, mixer channel or hearing aid, and the L2 stage of the codec audio path project: everything between the codec chip pins except the codec set-up.

## Hero diagram

A signal flowing left to right through a gain fader, a mute switch and a pair of meters; moving the fader slides the applied gain, the meters move with the processed signal, and a one-frame delay marker sits between input and output.

## Animation plan (driven by `hidden/model.py`)

Use Model.frame(left, right) to step a stereo frame: show the received sample, the smoothed gain, the product and limit, the three meters and the sample sent in the next frame.

## Interface

Pmod JA: word select, bit clock, data in, data out, and a master clock output. Shell registers: GAIN_L/R, CTRL (mutes), HOLD, PEAK_L/R, RMS_L/R, CLIPS_L/R, CLR, FRAMES, WINDOWS, CUR_L/R. LED shows both peaks.

## Acceptance criteria in plain words

I2S in and out at bit clocks from 8 to 100 board clocks long, with a one-frame delay and silence first; gain and mute slide by RAMP_STEP per sample; the product is floored and limited; meters read the processed signal and agree with the model per channel; the clears are per channel; the master clock is the board clock divided by 8. Checked with two parameter sets, including the defaults.
