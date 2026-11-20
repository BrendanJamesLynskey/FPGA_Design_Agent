# netlist_attrs.tcl (brief 96F1 stage 0, third question): the GTHE4_CHANNEL attributes of an IMPLEMENTED build, read from its post_route checkpoint with report_property.
# Run: vivado -mode batch -source netlist_attrs.tcl -tclargs <post_route.dcp> <out.txt>
lassign $argv dcp out
set fo [open $out w]
proc say {msg} { global fo; puts $fo $msg; flush $fo }
say "checkpoint: [file tail [file dirname [file dirname $dcp]]]/[file tail $dcp]"
if {[catch {open_checkpoint $dcp} m]} { say "open_checkpoint failed: $m"; close $fo; exit 1 }
set c [get_cells -hierarchical -filter {REF_NAME == GTHE4_CHANNEL}]
say "GTHE4_CHANNEL cells: $c  (LOC [get_property LOC $c])"
say "=== the attributes the bypass changes or depends on (name = value) ==="
foreach p [lsort [list_property $c -regexp {^(TXBUF_EN|RXBUF_EN|TX_XCLK_SEL|RX_XCLK_SEL|TX_FIFO_BYP_EN|TXOUTCLKSEL_VAL|TX_PROGDIV_CFG|RX_PROGDIV_CFG|TXPIPPMPD_VAL|TXPI_.*|TX_PHICAL_CFG.*|TXSYNC.*|RXSYNC.*|TXPHDLY.*|RXPHDLY.*|TXDLY.*|RXDLY.*|TXPH.*|RXPH.*|TXPHALIGN.*|RXPHALIGN.*|PCIERSTTXSYNCSTART.*|RXBUF_.*|TXBUF_.*|CLK_COR_M.*_LAT|RX_CLK25_DIV|TX_SAMPLE_PERIOD|TXOUT_DIV|RXOUT_DIV|TXPROGDIV.*|RXOUTCLKSEL.*|TX_DATA_WIDTH|RX_DATA_WIDTH|TX_INT_DATAWIDTH|RX_INT_DATAWIDTH|TXOUTCLK_.*|RXOUTCLK_.*)$}]] {
    say "$p = [get_property $p $c]"
}
say "=== full report_property of the cell ==="
set tmp [file rootname $out].full.txt
report_property -file $tmp $c
say "(full report in [file tail $tmp])"
set cm [get_cells -hierarchical -filter {REF_NAME == GTHE4_COMMON}]
say "GTHE4_COMMON cells: $cm"
foreach p {QPLL0_FBDIV QPLL0_CFG0 QPLL0_SDM_CFG0 QPLL0_SDM_CFG1 QPLL0_SDM_CFG2 SDM0DATA1_0 SDM0DATA1_1 SDM0_DATA_PIN_SEL SDM0_WIDTH_PIN_SEL QPLL0_INIT_CFG0 QPLL0_INIT_CFG1} {
    if {[catch {say "$p = [get_property $p $cm]"} e]} { say "$p : not a property ($e)" }
}
foreach pin {SDM0DATA0 SDM0TOGGLE SDM0RESET SDM0WIDTH0} {
    catch {say "pin $pin of GTHE4_COMMON: [get_nets -quiet -of_objects [get_pins -quiet -of_objects $cm -filter "REF_PIN_NAME =~ ${pin}*"]]"}
}
close $fo
