# ppm.xdc (brief 96C): enable the GTHE4 transmitter's phase-interpolator ppm controller. The Transceiver Wizard fixes TXPI_PPM to 0 and offers no setting for it, so the
# attribute is set on the primitive here (confirmed settable on a synthesised netlist: results/b96c/txpi_probe.log). UG576 Table 3-34: TXPI_PPM "enables gating reset to the TXPIPPM controller in the PCS" (UltraScale+ only), so with 0 the controller is held in reset; it also
# needs TXPIPPMSEL = 1 and TXPIPPMEN = 1 (Table 3-33). Used only by the ppm_* builds; the control builds leave the Wizard's value.
set_property TXPI_PPM 1'b1 [get_cells -hierarchical -filter {REF_NAME == GTHE4_CHANNEL}]
# UG576 v1.7.1 Table 3-34 / Equation 3-3: the PI code is updated every TXPI_SYNFREQ_PPM + 1 TXUSRCLK cycles; the Wizard's value (3'b001) gives 244 ppm a step at this line rate
# and width, too coarse for +-100 ppm. 3'b111 gives 61.04 ppm a step (TXOUT_DIV 1, internal width 32, 8 cycles).
set_property TXPI_SYNFREQ_PPM 3'b111 [get_cells -hierarchical -filter {REF_NAME == GTHE4_CHANNEL}]
