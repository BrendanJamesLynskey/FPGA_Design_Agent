# median3x3: 3 x 3 median filter on a raster stream

Takes a full-raster AXI4-Stream video (one beat on every clock, `H_TOTAL` beats a line) and outputs, for each pixel,
the median of each colour channel over its 3 x 3 neighbourhood (the fifth smallest of nine). The `tuser` sideband
(`hs`, `vs`, `de`) and `tlast` are delayed by the same fixed latency as the pixels, so the output raster has the
input's timing. Outside the active picture (`de` = 0) the output pixel is 0. At the picture's edges the window
includes blanking pixels, which are 0 (assumption A-1 in design.yaml). The contract is `contract.yaml`.
