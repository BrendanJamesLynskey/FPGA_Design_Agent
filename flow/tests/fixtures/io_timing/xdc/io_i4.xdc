create_clock -period 10.000 -name sys_clk [get_ports CLK100MHZ]
# DAC (system-synchronous: clocked by the board's oscillator, fanned out on the board). Data sheet: tSU 1.5 ns,
# tH 0.5 ns; board: data trace 0.4 ns, clock traces matched.
# -max = tSU + trace = 1.5 + 0.4 = 1.9 ns; -min = -tH + trace = -0.5 + 0.4 = -0.1 ns
set_output_delay -clock sys_clk -max 1.900 [get_ports {dac_d[*]}]
set_output_delay -clock sys_clk -min -0.100 [get_ports {dac_d[*]}]
