# ppm.xdc (brief 96C): enable the GTHE4 transmitter's phase-interpolator ppm controller. The Transceiver Wizard fixes TXPI_PPM to 0 and offers no setting for it, so the
# attribute is set on the primitive here (confirmed settable on a synthesised netlist: results/b96c/txpi_probe.log). With TXPI_PPM = 0 the TXPIPPMEN,
# TXPIPPMSEL and TXPIPPMSTEPSIZE ports have no documented effect that we could confirm; whether this attribute alone is enough is the board run's question
# (docs/board_run_plan.md, 96C). Used only by the ppm_* builds; the control builds leave the Wizard's value.
set_property TXPI_PPM 1'b1 [get_cells -hierarchical -filter {REF_NAME == GTHE4_CHANNEL}]
