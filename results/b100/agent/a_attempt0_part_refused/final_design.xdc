# chain.xdc: pins of chain_top (brief 100): the GT lane of the KR260 SFP+ cage as in designs/b96_kr260_10g/design.xdc, the GT site, and
# the clock period set by the script (create_clock is added by impl.tcl so that the period can vary per run).
set_property PACKAGE_PIN T2 [get_ports rx_p]
set_property PACKAGE_PIN T1 [get_ports rx_n]
set_property PACKAGE_PIN R4 [get_ports tx_p]
set_property PACKAGE_PIN R3 [get_ports tx_n]
set_property LOC GTHE4_CHANNEL_X0Y6 [get_cells u_gt]
create_clock -name clk -period 3.2 [get_ports clk]
