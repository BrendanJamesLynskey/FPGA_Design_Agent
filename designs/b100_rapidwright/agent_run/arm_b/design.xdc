set_property PACKAGE_PIN T2 [get_ports rx_p]
set_property PACKAGE_PIN T1 [get_ports rx_n]
set_property PACKAGE_PIN R4 [get_ports tx_p]
set_property PACKAGE_PIN R3 [get_ports tx_n]
set_property LOC GTHE4_CHANNEL_X0Y6 [get_cells u_gt]
create_clock -name clk -period 3.2 [get_ports clk]
create_pblock pb_chain
add_cells_to_pblock pb_chain [get_cells {u_mac u_pcs}]
resize_pblock pb_chain -add {CLOCKREGION_X0Y1:CLOCKREGION_X0Y1}
