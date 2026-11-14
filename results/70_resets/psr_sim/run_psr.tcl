# Brief 70 Part 2b: generate Processor System Reset (default settings) and simulate tb_psr in xsim (behavioural).
# vivado -mode batch -source run_psr.tcl -tclargs <workdir> <testbench file> <C_EXT_RESET_HIGH value, or default>
set_param general.maxThreads 1
set work [lindex $argv 0]
set tb [lindex $argv 1]
set exthigh [lindex $argv 2]
set here [file dirname [file normalize [info script]]]
create_project -force psr $work/proj -part xc7a100tcsg324-1
puts "FDA-IP VIVADO [version -short]"
set def [lindex [lsort [get_ipdefs -all xilinx.com:ip:proc_sys_reset:*]] end]
puts "FDA-IP VLNV $def REQUIRES_LICENSE [get_property REQUIRES_LICENSE $def]"
file mkdir $work/ip
create_ip -name proc_sys_reset -vendor xilinx.com -library ip -module_name psr_dut -dir $work/ip
if {$exthigh ne "default"} { set_property -dict [list CONFIG.C_EXT_RESET_HIGH $exthigh] [get_ips psr_dut] }
puts "FDA-IP C_EXT_RESET_HIGH [get_property CONFIG.C_EXT_RESET_HIGH [get_ips psr_dut]] C_AUX_RESET_HIGH [get_property CONFIG.C_AUX_RESET_HIGH [get_ips psr_dut]] C_EXT_RST_WIDTH [get_property CONFIG.C_EXT_RST_WIDTH [get_ips psr_dut]]"
generate_target all [get_ips psr_dut]
add_files -fileset sim_1 $tb
set_property top tb_psr [get_filesets sim_1]
set_property -name {xsim.simulate.runtime} -value {all} -objects [get_filesets sim_1]
launch_simulation -simset sim_1 -mode behavioral
puts "FDA-IP SIM DONE"
