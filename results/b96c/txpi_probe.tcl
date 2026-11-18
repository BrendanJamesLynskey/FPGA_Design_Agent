# brief 96C probe: can GTHE4_CHANNEL attributes be read and changed on a synthesised netlist? (TXPI_PPM is fixed to 0 in the Wizard's wrapper)
open_checkpoint /home/brendan/Claude_sandbox/_worktrees/97c-seq/designs/b96_kr260_10g/build/base/post_synth.dcp
set c [get_cells -hierarchical -filter {REF_NAME == GTHE4_CHANNEL}]
puts "CELL: $c"
foreach p {TXPI_PPM TXPI_PPMCLK_SEL TXPI_PPM_CFG TXPI_SYNFREQ_PPM TXPI_CFG TXPI_CFG0 TXPI_CFG1 TXPI_CFG2 TXPI_CFG3 TXPI_CFG4 TXPI_CFG5 TXPI_LPM TXPI_GRAY_SEL TXPI_INVSTROBE_SEL TXPI_VREFSEL TXBUF_EN RXBUF_EN TX_XCLK_SEL RX_XCLK_SEL TX_PROGDIV_CFG TXOUTCLKSEL_VAL} {
    if {[catch {puts "PROP $p = [get_property $p $c]"} e]} {puts "PROP $p ERR $e"}
}
foreach {name val} {TXPI_PPM 1'b1} {
    if {[catch {set_property $name $val $c} e]} {puts "SET $name ERR: $e"} else {puts "SET $name OK -> [get_property $name $c]"}
}
catch {report_drc -checks {} -name d1 -quiet}
puts "DONE"
