# design.xdc: kr260_top on the Kria KR260 (xck26-sfvc784-2LV-c), brief 58A.
# Pins: AMD board files kr260_carrier 1.1 (pl_gem2, pl_gem3, User_led, hpa_clk0p_clk) mapped to package pins through
# kr260_som 1.1 part0_pins.xml (Apache-2.0, shipped with Vivado); PHY2 agrees with KB board/kr260/ethernet/kr260-four-gbe
# (TAXI). All PL Ethernet pins are in the 1.8 V HP banks (LVCMOS18).

# ---- clock in: 25 MHz on HPA_CLK0P (KB board/kr260/clocking; the frequency is TAXI's, unconfirmed) ----
set_property -dict {PACKAGE_PIN C3 IOSTANDARD LVCMOS18} [get_ports clk_25]
create_clock -name clk_25 -period 40.000 [get_ports clk_25]

# ---- port A: PHY2, J10B (Ethernet 2) ----
set_property -dict {PACKAGE_PIN D4 IOSTANDARD LVCMOS18} [get_ports a_rxc]
set_property -dict {PACKAGE_PIN A1 IOSTANDARD LVCMOS18} [get_ports {a_rxd[0]}]
set_property -dict {PACKAGE_PIN B3 IOSTANDARD LVCMOS18} [get_ports {a_rxd[1]}]
set_property -dict {PACKAGE_PIN A3 IOSTANDARD LVCMOS18} [get_ports {a_rxd[2]}]
set_property -dict {PACKAGE_PIN B4 IOSTANDARD LVCMOS18} [get_ports {a_rxd[3]}]
set_property -dict {PACKAGE_PIN A4 IOSTANDARD LVCMOS18} [get_ports a_rx_ctl]
set_property -dict {PACKAGE_PIN A2 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports a_txc]
set_property -dict {PACKAGE_PIN E1 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports {a_txd[0]}]
set_property -dict {PACKAGE_PIN D1 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports {a_txd[1]}]
set_property -dict {PACKAGE_PIN F2 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports {a_txd[2]}]
set_property -dict {PACKAGE_PIN E2 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports {a_txd[3]}]
set_property -dict {PACKAGE_PIN F1 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports a_tx_ctl]
set_property -dict {PACKAGE_PIN B1 IOSTANDARD LVCMOS18} [get_ports a_rst_n]
set_property -dict {PACKAGE_PIN F3 IOSTANDARD LVCMOS18 PULLUP TRUE} [get_ports a_mdio]
set_property -dict {PACKAGE_PIN G3 IOSTANDARD LVCMOS18} [get_ports a_mdc]

# ---- port B: PHY3, J10A (Ethernet 3) ----
set_property -dict {PACKAGE_PIN K4 IOSTANDARD LVCMOS18} [get_ports b_rxc]
set_property -dict {PACKAGE_PIN H1 IOSTANDARD LVCMOS18} [get_ports {b_rxd[0]}]
set_property -dict {PACKAGE_PIN K2 IOSTANDARD LVCMOS18} [get_ports {b_rxd[1]}]
set_property -dict {PACKAGE_PIN J2 IOSTANDARD LVCMOS18} [get_ports {b_rxd[2]}]
set_property -dict {PACKAGE_PIN H4 IOSTANDARD LVCMOS18} [get_ports {b_rxd[3]}]
set_property -dict {PACKAGE_PIN H3 IOSTANDARD LVCMOS18} [get_ports b_rx_ctl]
set_property -dict {PACKAGE_PIN J1 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports b_txc]
set_property -dict {PACKAGE_PIN U9 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports {b_txd[0]}]
set_property -dict {PACKAGE_PIN V9 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports {b_txd[1]}]
set_property -dict {PACKAGE_PIN U8 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports {b_txd[2]}]
set_property -dict {PACKAGE_PIN V8 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports {b_txd[3]}]
set_property -dict {PACKAGE_PIN Y8 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports b_tx_ctl]
set_property -dict {PACKAGE_PIN K1 IOSTANDARD LVCMOS18} [get_ports b_rst_n]
set_property -dict {PACKAGE_PIN T8 IOSTANDARD LVCMOS18 PULLUP TRUE} [get_ports b_mdio]
set_property -dict {PACKAGE_PIN R8 IOSTANDARD LVCMOS18} [get_ports b_mdc]

# ---- user LEDs (KB board/kr260/user-io) ----
set_property -dict {PACKAGE_PIN F8 IOSTANDARD LVCMOS18 SLEW SLOW DRIVE 8} [get_ports {led[0]}]
set_property -dict {PACKAGE_PIN E8 IOSTANDARD LVCMOS18 SLEW SLOW DRIVE 8} [get_ports {led[1]}]

# ---- RGMII receive: each port's RX_CLK, 125 MHz at 1000 Mb/s ----
# The PHY's internal RX clock delay is to be enabled over MDIO (M88E1111 register 20 bit 7; docs/board_run_plan.md), which
# makes the data centre-aligned at the FPGA pins. RGMII v2.0 with the delay gives data valid at least tSU = 1.2 ns
# before and tH = 1.2 ns after each RX_CLK edge (to be confirmed for this PHY: owner question). A virtual clock models
# the PHY's launch; data launched on one edge are captured on the next opposite edge by IDDRE1 (SAME_EDGE_PIPELINED).
create_clock -name a_rxc -period 8.000 [get_ports a_rxc]
create_clock -name b_rxc -period 8.000 [get_ports b_rxc]
create_clock -name a_rxc_v -period 8.000
create_clock -name b_rxc_v -period 8.000
# port A, rising-edge data: max = T/2 - tSU = 4.0 - 1.2 = 2.8 ns, min = tH = 1.2 ns
set_input_delay -clock a_rxc_v -max 2.800 [get_ports {a_rxd[*] a_rx_ctl}]
set_input_delay -clock a_rxc_v -min 1.200 [get_ports {a_rxd[*] a_rx_ctl}]
# port A, falling-edge data: max = T/2 - tSU = 2.8 ns, min = tH = 1.2 ns (-add_delay keeps the rising-edge lines)
set_input_delay -clock a_rxc_v -clock_fall -max 2.800 -add_delay [get_ports {a_rxd[*] a_rx_ctl}]
set_input_delay -clock a_rxc_v -clock_fall -min 1.200 -add_delay [get_ports {a_rxd[*] a_rx_ctl}]
# port B, rising-edge data: max = T/2 - tSU = 4.0 - 1.2 = 2.8 ns, min = tH = 1.2 ns
set_input_delay -clock b_rxc_v -max 2.800 [get_ports {b_rxd[*] b_rx_ctl}]
set_input_delay -clock b_rxc_v -min 1.200 [get_ports {b_rxd[*] b_rx_ctl}]
# port B, falling-edge data: max = T/2 - tSU = 2.8 ns, min = tH = 1.2 ns (-add_delay keeps the rising-edge lines)
set_input_delay -clock b_rxc_v -clock_fall -max 2.800 -add_delay [get_ports {b_rxd[*] b_rx_ctl}]
set_input_delay -clock b_rxc_v -clock_fall -min 1.200 -add_delay [get_ports {b_rxd[*] b_rx_ctl}]
# each edge's data are captured by the next opposite edge only
set_false_path -setup -rise_from [get_clocks a_rxc_v] -fall_to [get_clocks a_rxc]
set_false_path -setup -fall_from [get_clocks a_rxc_v] -rise_to [get_clocks a_rxc]
set_false_path -hold  -rise_from [get_clocks a_rxc_v] -rise_to [get_clocks a_rxc]
set_false_path -hold  -fall_from [get_clocks a_rxc_v] -fall_to [get_clocks a_rxc]
set_false_path -setup -rise_from [get_clocks b_rxc_v] -fall_to [get_clocks b_rxc]
set_false_path -setup -fall_from [get_clocks b_rxc_v] -rise_to [get_clocks b_rxc]
set_false_path -hold  -rise_from [get_clocks b_rxc_v] -rise_to [get_clocks b_rxc]
set_false_path -hold  -fall_from [get_clocks b_rxc_v] -fall_to [get_clocks b_rxc]

# ---- RGMII transmit: TXC forwarded from the 90-degree MMCM output through ODDRE1 ----
# The PHY's TX delay stays off; the 90-degree TXC centres the clock in each data half. Receiver requirement at the PHY
# assumed from RGMII v2.0 without delay: tSU = 1.0 ns, tH = 0.8 ns (0.8 is our choice, under the 1.0 ns the v2.0
# table gives; owner question). output delay max = tSU, min = -tH.
create_generated_clock -name a_txc -source [get_pins u_atx/u_txc/C] -multiply_by 1 [get_ports a_txc]
create_generated_clock -name b_txc -source [get_pins u_btx/u_txc/C] -multiply_by 1 [get_ports b_txc]
# port A, both edges: max = tSU = 1.0 ns, min = -tH = -0.8 ns
set_output_delay -clock a_txc -max 1.000 [get_ports {a_txd[*] a_tx_ctl}]
set_output_delay -clock a_txc -min -0.800 [get_ports {a_txd[*] a_tx_ctl}]
set_output_delay -clock a_txc -clock_fall -max 1.000 -add_delay [get_ports {a_txd[*] a_tx_ctl}]
set_output_delay -clock a_txc -clock_fall -min -0.800 -add_delay [get_ports {a_txd[*] a_tx_ctl}]
# port B, both edges: max = tSU = 1.0 ns, min = -tH = -0.8 ns
set_output_delay -clock b_txc -max 1.000 [get_ports {b_txd[*] b_tx_ctl}]
set_output_delay -clock b_txc -min -0.800 [get_ports {b_txd[*] b_tx_ctl}]
set_output_delay -clock b_txc -clock_fall -max 1.000 -add_delay [get_ports {b_txd[*] b_tx_ctl}]
set_output_delay -clock b_txc -clock_fall -min -0.800 -add_delay [get_ports {b_txd[*] b_tx_ctl}]
# same-edge transfers only (each ODDRE1 half is launched on its own edge of clk)
set_false_path -setup -rise_from [get_clocks -of_objects [get_pins u_mmcm/CLKOUT0]] -fall_to [get_clocks {a_txc b_txc}]
set_false_path -setup -fall_from [get_clocks -of_objects [get_pins u_mmcm/CLKOUT0]] -rise_to [get_clocks {a_txc b_txc}]
set_false_path -hold  -rise_from [get_clocks -of_objects [get_pins u_mmcm/CLKOUT0]] -rise_to [get_clocks {a_txc b_txc}]
set_false_path -hold  -fall_from [get_clocks -of_objects [get_pins u_mmcm/CLKOUT0]] -fall_to [get_clocks {a_txc b_txc}]

# ---- JTAG register front end: BSCANE2 (the clock is defined on INTERNAL_TCK, as AMD's own debug IP does) ----
create_clock -name tck -period 33.333 [get_pins u_jtag/u_bscan/INTERNAL_TCK]
create_generated_clock -name tck_out -source [get_pins u_jtag/u_bscan/INTERNAL_TCK] -divide_by 1 [get_pins u_jtag/u_bscan/TCK]
# TDO: the shift register (TCK) to the primitive's TDO, timed within the TCK clocks (no exception: a false path here
# makes report_cdc call it a crossing into a non-FD primitive, CDC-13)

# Clock-domain crossings (each RX_CLK, TCK and the core clock) are all inside XPM macros, which carry their own
# constraints; there is no set_clock_groups, so any other crossing would show as a timing failure.
# The one path XPM leaves timed as synchronous: each xpm_fifo_async (distributed RAM) is written on RX_CLK and read
# into its output register on the core clock. The read address only reaches an entry after the write pointer has
# crossed (two synchroniser stages), so the data path needs only to settle within one core clock period: 8 ns.
set_max_delay -datapath_only 8.000 -from [get_clocks a_rxc] -to [get_cells -hierarchical -filter {NAME =~ u_acdc/u_fifo/*doutb_reg_reg*}]
set_max_delay -datapath_only 8.000 -from [get_clocks b_rxc] -to [get_cells -hierarchical -filter {NAME =~ u_bcdc/u_fifo/*doutb_reg_reg*}]

# ---- slow pins: PHY resets (held 16.8 ms), MDIO (1.95 MHz, the input synchronised by xpm_cdc_single), LEDs ----
# No timing relationship to any clock: 0 ns placeholder delays and false paths (flow/io_check.py rules).
set_output_delay -clock [get_clocks -of_objects [get_pins u_mmcm/CLKOUT0]] 0.000 [get_ports {a_rst_n b_rst_n a_mdc b_mdc a_mdio b_mdio led[*]}]
set_input_delay -clock [get_clocks -of_objects [get_pins u_mmcm/CLKOUT0]] 0.000 [get_ports {a_mdio b_mdio}]
set_false_path -to [get_ports {a_rst_n b_rst_n a_mdc b_mdc a_mdio b_mdio led[*]}]
set_false_path -from [get_ports {a_mdio b_mdio}]
