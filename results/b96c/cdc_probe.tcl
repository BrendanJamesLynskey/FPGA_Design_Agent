open_checkpoint /home/brendan/Claude_sandbox/_worktrees/96c-ppm/designs/b96_kr260_10g/build/base/post_synth.dcp
set mp [get_pins -hierarchical -filter {NAME =~ *u_rm/mem_reg*/CLK}]
puts "STARTPINS [llength $mp]"
set_max_delay -datapath_only -from $mp -to [get_cells u_core/u_rx/u_rm/*_reg*] 6.0
report_cdc -details -file /home/brendan/Claude_sandbox/_worktrees/96c-ppm/results/b96c/cdc_probe.rpt
puts DONE
