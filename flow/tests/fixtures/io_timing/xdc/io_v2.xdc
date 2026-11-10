create_clock -period 10.000 -name sys_clk [get_ports CLK100MHZ]
# vclk125: the device's 125 MHz clock, not a design clock: a virtual clock at the period of clk125
create_clock -period 8.000 -name vclk125
# din: an external device clocked at 125 MHz by a clock from the same oscillator (phase-aligned on the board) that the
# FPGA does not receive; din is captured by clk125 (MMCM CLKOUT0, 1000 MHz VCO / 8). Device: tCO 0.5 ns min, 2.5 ns max;
# data trace 0.5 ns: -max = 2.5 + 0.5 = 3.0 ns; -min = 0.5 + 0.5 = 1.0 ns
set_input_delay -clock vclk125 -max 3.000 [get_ports {din[*]}]
set_input_delay -clock vclk125 -min 1.000 [get_ports {din[*]}]
# LED[0]: read by a person, no timing relationship
set_output_delay -clock sys_clk 0.000 [get_ports {LED[0]}]
set_false_path -to [get_ports {LED[0]}]
