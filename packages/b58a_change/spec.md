# Change request: saturate the `lost` counter in lat_hist (b58a_trigger)

The user's words: the existing b58a trigger design in `existing/` stays as it is, except for one module. In `lat_hist`, the `lost`
counter (samples that arrived too close together to be counted) wraps from 0xFFFFFFFF to 0; it should stop at 0xFFFFFFFF instead, so a
host never reads a small number after a long run. Nothing else changes: the ports of `lat_hist` and of every other module, the XDC and
the timing of the rest of the design stay as they are (frozen).
