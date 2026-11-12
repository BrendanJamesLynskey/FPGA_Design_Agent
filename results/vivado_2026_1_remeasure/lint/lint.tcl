# brief 49: what synth_design -lint -file writes on this Vivado (text table or CSV), and the Tcl version
set_param general.maxThreads 1
puts "TCL_PATCHLEVEL [info patchlevel]"
read_verilog -sv [file join [file dirname [info script]] lint_top.sv]
synth_design -top lint_top -part xc7a100tcsg324-1 -lint -file lint_out.txt
puts "LINT_DONE"
