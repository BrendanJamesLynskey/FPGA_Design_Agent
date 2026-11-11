create_clock -period 10.000 -name sys_clk [get_ports CLK100MHZ]
# ADC (system-synchronous: the board's oscillator clocks the ADC and CLK100MHZ). Data sheet: tCO 1.0 ns min, 5.0 ns max;
# board: data trace 0.5 ns, clock traces to the ADC and the FPGA matched.
# -max = tCO_max + trace = 5.0 + 0.5 = 5.5 ns; -min = tCO_min + trace = 1.0 + 0.5 = 1.5 ns
set_input_delay -clock sys_clk -max 5.500 [get_ports {adc_d[*]}]
set_input_delay -clock sys_clk -min 1.500 [get_ports {adc_d[*]}]
# button and UART inputs
set_input_delay -clock sys_clk -max 2.000 [get_ports BTNC]
set_input_delay -clock sys_clk -min 0.000 [get_ports BTNC]
# LED and UART outputs
set_output_delay -clock sys_clk -max -1.500 [get_ports {LED[0] UART_RXD_OUT}]
set_output_delay -clock sys_clk -min -2.000 [get_ports {LED[0] UART_RXD_OUT}]
