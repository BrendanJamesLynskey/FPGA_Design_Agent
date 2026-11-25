# quartus_sta -t sta.tcl <project> <out dir>
lassign $quartus(args) proj out
project_open $proj
create_timing_netlist
read_sdc
update_timing_netlist
report_clocks -file $out/sta_clocks.rpt
report_clock_transfers -setup -file $out/sta_clock_transfers.rpt
check_timing -file $out/sta_check_timing.rpt
report_timing -setup -npaths 10 -detail summary -file $out/sta_setup.rpt
create_timing_summary -setup -file $out/sta_summary_setup.rpt
delete_timing_netlist
project_close
