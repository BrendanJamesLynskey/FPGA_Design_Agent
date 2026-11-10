# video_src: 720p timing and test pattern

Generates the CEA-861 1280 x 720 at 60 Hz raster (1650 x 750 clocks of 74.25 MHz) as an AXI4-Stream with one beat on
every clock, blanking included: `tuser` carries `hs`, `vs` and `de`, `tlast` marks the last beat of each line, and
`tdata` is 8:8:8 RGB, 0 outside the active picture. With `pattern_sel` = 0 the picture is eight vertical colour bars
of 160 pixels, left to right white, yellow, cyan, green, magenta, red, blue, black, at full intensity. `frame_count`
counts frames started since reset. The contract is `contract.yaml`.
