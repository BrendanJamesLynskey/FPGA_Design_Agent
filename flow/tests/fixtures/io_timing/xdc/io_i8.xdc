create_clock -period 10.000 -name sys_clk [get_ports CLK100MHZ]
# ADC data: placeholder (no data sheet numbers yet)
set_input_delay -clock sys_clk 0.000 [get_ports {adc_d[*]}]
# BTNC: a push button, asynchronous to sys_clk; it enters the two-flop synchroniser btn_sync (ASYNC_REG), so the pin
# has no timing relationship: a 0 ns placeholder delay (check_timing) and a false path
set_input_delay -clock sys_clk 0.000 [get_ports BTNC]
set_false_path -from [get_ports BTNC]
# LED[0] (read by a person) and UART_RXD_OUT (115200 baud): slow outputs, no timing relationship
set_output_delay -clock sys_clk 0.000 [get_ports {LED[0] UART_RXD_OUT}]
set_false_path -to [get_ports {LED[0] UART_RXD_OUT}]
