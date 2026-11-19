# es.xdc (brief 96D): power up the GTHE4 receiver's eye-scan circuit. The Transceiver Wizard sets ES_EYE_SCAN_EN and ES_ERRDET_EN to FALSE and offers no setting for them
# (the generated channel wrapper passes "FALSE"); UG576 v1.7.1 Table 4-20: ES_EYE_SCAN_EN "should always be 1 when using Eye Scan... Re-enabling Eye Scan functionality requires
# reasserting this bit and asserting/deasserting PMA reset", so it is set here, in the bitstream, never through the DRP (a DRP write would need a PMA reset and restart the link).
# ES_ERRDET_EN = 1 selects the statistical-eye view (each Sdata bit is 1 only where the offset sample disagrees with the data sample).
# The attributes are settable on the synthesised primitive (as TXPI_PPM in ppm.xdc). Used only by the eye builds; the other builds keep the Wizard's FALSE.
set_property ES_EYE_SCAN_EN TRUE [get_cells -hierarchical -filter {REF_NAME == GTHE4_CHANNEL}]
set_property ES_ERRDET_EN TRUE [get_cells -hierarchical -filter {REF_NAME == GTHE4_CHANNEL}]
