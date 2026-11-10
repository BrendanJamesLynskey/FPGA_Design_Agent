create_clock -period 10.000 -name sys_clk [get_ports CLK100MHZ]
# ADC (system-synchronous: the board's oscillator clocks the ADC and CLK100MHZ). Data sheet: tCO 1.0 ns min, 5.0 ns max;
# board: data trace 0.5 ns, clock traces to the ADC and the FPGA matched.
# -max = tCO_max + trace = 5.0 + 0.5 = 5.5 ns; -min = tCO_min + trace = 1.0 + 0.5 = 1.5 ns
set_input_delay -clock sys_clk -max 5.500 [get_ports {adc_d[*]}]
set_input_delay -clock sys_clk -min 1.500 [get_ports {adc_d[*]}]
# BTNC (push button, into the two-flop synchroniser btn_sync), LED[0] and UART_RXD_OUT (115200 baud): asynchronous or
# slow, no timing relationship: 0 ns placeholder delays only (check_timing), no false path
set_input_delay -clock sys_clk 0.000 [get_ports BTNC]
set_output_delay -clock sys_clk 0.000 [get_ports {LED[0] UART_RXD_OUT}]
