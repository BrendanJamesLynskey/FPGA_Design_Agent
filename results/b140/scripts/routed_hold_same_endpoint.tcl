# usage: vivado -mode batch -source routed_hold_same_endpoint.tcl -tclargs <post_route.dcp>
# hold slack after routing: worst path to the hub register of the worst placement-stage path, worst launched by the soft-TAP clock, worst inside the TCK domain
open_checkpoint [lindex $argv 0]
set e [get_pins {dbg_hub/inst/BSCANID.u_xsdbm_id/CORE_XSDB.U_ICON/iDATA_CMD_reg/D}]
set p [get_timing_paths -delay_type min -to $e -max_paths 1]
puts "ROUTED_WORST_TO_HUB_REG slack=[get_property SLACK $p] skew=[get_property SKEW $p] start=[get_property STARTPOINT_PIN $p]"
set tp [get_timing_paths -delay_type min -max_paths 1 -from [get_clocks u_dbg/u_bridge/inst/bsip/inst/USE_SOFTBSCAN.U_BSCAN_TAP/U_BASETAP/U_TAP/UPDATEDR_O_reg/Q]]
puts "ROUTED_WORST_FROM_TAPCLK slack=[get_property SLACK $tp]"
set tp [get_timing_paths -delay_type min -max_paths 1 -from [get_clocks u_dbg/u_bridge/inst/axi_jtag/inst/u_jtag_proc/tck_i_reg/Q] -to [get_clocks u_dbg/u_bridge/inst/axi_jtag/inst/u_jtag_proc/tck_i_reg/Q]]
puts "ROUTED_WORST_TCK_INTRA slack=[get_property SLACK $tp]"
