create_clock -period 10.000 -name sys_clk [get_ports CLK100MHZ]
# dac_clk: sys_clk forwarded by the ODDR fwd_oddr with D1=0, D2=1, so it is sys_clk inverted
create_generated_clock -name dac_clk -source [get_pins fwd_oddr/C] -divide_by 1 -invert [get_ports dac_clk]
# DAC data sheet: tSU 1.5 ns, tH 0.5 ns; board: dac_clk and dac_d traces matched (skew 0), so
# -max = tSU = 1.5 ns; -min = -tH = -0.5 ns, fault: relative to sys_clk
set_output_delay -clock sys_clk -max 1.500 [get_ports {dac_d[*]}]
set_output_delay -clock sys_clk -min -0.500 [get_ports {dac_d[*]}]
