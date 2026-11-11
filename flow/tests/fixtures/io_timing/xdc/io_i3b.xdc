create_clock -period 10.000 -name sys_clk [get_ports CLK100MHZ]
# ADC (system-synchronous: the board's oscillator clocks the ADC and CLK100MHZ). Data sheet: tCO 1.0 ns min, 5.0 ns max;
# board: data trace 0.5 ns, clock traces to the ADC and the FPGA matched.
# -max = tCO_max + trace = 5.0 + 0.5 = 5.5 ns; fault: -min written as -(tCO_min + trace)
set_input_delay -clock sys_clk -max 5.500 [get_ports {adc_d[*]}]
set_input_delay -clock sys_clk -min -1.500 [get_ports {adc_d[*]}]
# BTNC: a push button, asynchronous to sys_clk; it enters the two-flop synchroniser btn_sync (ASYNC_REG), so the pin
# has no timing relationship: a 0 ns placeholder delay (check_timing) and a false path
set_input_delay -clock sys_clk 0.000 [get_ports BTNC]
set_false_path -from [get_ports BTNC]
# LED[0] (read by a person) and UART_RXD_OUT (115200 baud): slow outputs, no timing relationship
set_output_delay -clock sys_clk 0.000 [get_ports {LED[0] UART_RXD_OUT}]
set_false_path -to [get_ports {LED[0] UART_RXD_OUT}]
