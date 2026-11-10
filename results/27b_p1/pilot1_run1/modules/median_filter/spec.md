For active pixels, compute each RGB channel's median over its corresponding 3-by-3
neighbourhood. Replicate the nearest active-picture pixel beyond each active-picture
edge, including corners. Preserve the pixel's active, sync, and line-end association
through the filter pipeline.
