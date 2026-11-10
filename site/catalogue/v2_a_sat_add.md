# Saturating adder (v2_a_sat_add)

Domain A, drill tier, Nexys A7-100T. Survey row: A16 (adders: wrapping, saturating, overflow flag). Draft for the problem catalogue; the task files are in
`benchmark/v2/tasks/v2_a_sat_add/`.

## The problem, and where it is used

A 16-bit adder that can be signed or unsigned and can wrap or saturate, with overflow, zero and negative flags. The points to get right are that overflow means carry out when unsigned but a sign error when signed, that the flag reports the overflow even when saturation hid it from the sum, and which end a signed sum saturates to.

Where it appears: Digital signal processing (audio and image pixels clip rather than wrap), control loops and accumulators that must not roll over, and every processor status register. The signed and unsigned overflow rules are a classic source of bugs.

## Hero diagram

A number line on a circle for the wrapping case and a number line with end stops for the saturating case. Two operands are dots; their sum walks round the circle or stops at the end. Three flag lamps (OVF, ZERO, NEG) sit beside it. Switches select signed or unsigned, which relabels the same 16-bit circle.

## Animation plan (driven by `hidden/model.py`)

Use add(a, b, signed, sat) from the model to give (sum, flags). Animate A's dot moving by B round the circle and show where the wrapped result and the saturated result land. The same operands are replayed in the four mode combinations, with the flag lamps following the model's flags.

## Interface

Shell registers: A and B (16 bits), CTRL (bit 0 signed, bit 1 saturate), SUM and FLAGS (read-only). LED[15:0] shows SUM.

## Acceptance criteria in plain words

The sum is the wrapped sum when saturation is off and the clamped value when it is on and the add overflowed, in both signed and unsigned mode. OVF is the carry out unsigned and the signed overflow signed, with or without saturation. ZERO and NEG come from the final sum. Register map and reset values as listed.
