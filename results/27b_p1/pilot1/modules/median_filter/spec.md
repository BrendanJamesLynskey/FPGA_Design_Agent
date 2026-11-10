For each active output pixel, computes the median of the nine samples in
the corresponding 3 x 3 neighbourhood independently for red, green, and
blue. Replicates the nearest active-picture pixel at boundaries. Delays
raster metadata so filtered pixels, active timing, and sync remain aligned.
Sustains one raster beat per pixel clock without inserting gaps.
