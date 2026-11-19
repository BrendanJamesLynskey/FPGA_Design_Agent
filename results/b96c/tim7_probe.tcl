open_checkpoint /home/brendan/Claude_sandbox/_worktrees/96c-ppm/designs/b96_kr260_10g/build/base/post_synth.dcp
set ram [get_cells -hierarchical -filter {NAME =~ *u_rm/u_fifo/* && REF_NAME =~ RAM*}]
puts "RAMCELLS [llength $ram] [lindex $ram 0]"
set pins [get_pins -of_objects $ram -filter {REF_PIN_NAME == CLK || REF_PIN_NAME == WCLK}]
puts "RAMPINS [llength $pins]"
set_max_delay -datapath_only -from $pins -to [get_cells -hierarchical -filter {NAME =~ u_core/u_rx/u_rm/* && IS_SEQUENTIAL}] 6.0
report_methodology -checks TIMING-7 -file tim7.rpt
puts DONE
