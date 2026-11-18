read_verilog -sv rate_match_x.sv
read_verilog -sv top.sv
synth_design -top rm_top -part xck26-sfvc784-2LV-c -mode out_of_context
create_clock -period 6.2 [get_ports wclk]
create_clock -period 6.2 [get_ports rclk]
report_cdc -details -file cdc_x.rpt
puts DONE
