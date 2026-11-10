For each active output coordinate, calculate the median independently for each
4-bit colour channel over its 3x3 neighbourhood. At picture boundaries, clamp
neighbourhood coordinates to the nearest active-picture coordinate. Preserve the
corresponding coordinate, active-video indication, sync timing, and frame_start.
