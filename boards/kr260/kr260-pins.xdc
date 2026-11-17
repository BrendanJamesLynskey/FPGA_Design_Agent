## Kria KR260 Robotics Starter Kit (xck26-sfvc784-2LV-c): PL pins with an I/O standard, as this repository's own designs use them
## Written by tools/board_pins_import.py from boards/kr260/pins_import.yaml. Pin locations are facts about the board;
## this file is our own listing of them in one format, not a copy of a vendor file. Sources:
##   B58A_XDC: https://raw.githubusercontent.com/BrendanJamesLynskey/FPGA_Design_Agent/78314d91955d9c573fc4f361749c08df3ed6017f/designs/b58a_trigger/design.xdc (sha256 62c1e380c097...; this repository (MIT); its header says the pins come from the AMD kr260_carrier 1.1 and kr260_som 1.1 board files (Apache-2.0, shipped with Vivado), mapped from SOM pins to package pins); supplies the 25 MHz clock input, the two PL Ethernet ports (RGMII) and the two user LEDs; built (results/b58a), not run on the board
##   B96_XDC: https://raw.githubusercontent.com/BrendanJamesLynskey/FPGA_Design_Agent/78314d91955d9c573fc4f361749c08df3ed6017f/designs/b96_kr260_10g/design.xdc (sha256 4dec8c5ba8f6...; this repository (MIT); the SFP+ control and I2C pins; the board run of 2026-11-17 (results/b96/hw/stage3.json) used them and the module's EEPROM and DDM were read); supplies the SFP+ cage J24 control and I2C pins (LVCMOS33)
## Every port is commented out in the vendor style: the agent's board_constraints tool writes the lines a design uses.
## Left out because no source gives its I/O standard (a standard is never invented): sfp_mgt_refclk_p on Y6 (B96_XDC); sfp_mgt_refclk_n on Y5 (B96_XDC); sfp_rx_p on T2 (B96_XDC); sfp_rx_n on T1 (B96_XDC); sfp_tx_p on R4 (B96_XDC); sfp_tx_n on R3 (B96_XDC)


## PL clock (25 MHz; the frequency is unconfirmed)
#set_property -dict { PACKAGE_PIN C3    IOSTANDARD LVCMOS18   } [get_ports { clk_25 }]; # B58A_XDC: clk_25

## User LEDs
#set_property -dict { PACKAGE_PIN F8    IOSTANDARD LVCMOS18   } [get_ports { led[0] }]; # B58A_XDC: led[0]
#set_property -dict { PACKAGE_PIN E8    IOSTANDARD LVCMOS18   } [get_ports { led[1] }]; # B58A_XDC: led[1]

## SFP+ cage J24 control and I2C (3.3 V; measured on the board 2026-11-17)
#set_property -dict { PACKAGE_PIN Y10   IOSTANDARD LVCMOS33   } [get_ports { sfp_tx_disable }]; # B96_XDC: sfp_tx_disable
#set_property -dict { PACKAGE_PIN W10   IOSTANDARD LVCMOS33   } [get_ports { sfp_mod_abs }]; # B96_XDC: sfp_mod_abs
#set_property -dict { PACKAGE_PIN J12   IOSTANDARD LVCMOS33   } [get_ports { sfp_rx_los }]; # B96_XDC: sfp_rx_los
#set_property -dict { PACKAGE_PIN A10   IOSTANDARD LVCMOS33   } [get_ports { sfp_tx_fault }]; # B96_XDC: sfp_tx_fault
#set_property -dict { PACKAGE_PIN AB11  IOSTANDARD LVCMOS33   } [get_ports { sfp_i2c_scl }]; # B96_XDC: sfp_i2c_scl
#set_property -dict { PACKAGE_PIN AC11  IOSTANDARD LVCMOS33   } [get_ports { sfp_i2c_sda }]; # B96_XDC: sfp_i2c_sda

## PL Ethernet port A (PHY2, J10B, RGMII, 1.8 V; built, not run)
#set_property -dict { PACKAGE_PIN D4    IOSTANDARD LVCMOS18   } [get_ports { a_rxc }]; # B58A_XDC: a_rxc
#set_property -dict { PACKAGE_PIN A1    IOSTANDARD LVCMOS18   } [get_ports { a_rxd[0] }]; # B58A_XDC: a_rxd[0]
#set_property -dict { PACKAGE_PIN B3    IOSTANDARD LVCMOS18   } [get_ports { a_rxd[1] }]; # B58A_XDC: a_rxd[1]
#set_property -dict { PACKAGE_PIN A3    IOSTANDARD LVCMOS18   } [get_ports { a_rxd[2] }]; # B58A_XDC: a_rxd[2]
#set_property -dict { PACKAGE_PIN B4    IOSTANDARD LVCMOS18   } [get_ports { a_rxd[3] }]; # B58A_XDC: a_rxd[3]
#set_property -dict { PACKAGE_PIN A4    IOSTANDARD LVCMOS18   } [get_ports { a_rx_ctl }]; # B58A_XDC: a_rx_ctl
#set_property -dict { PACKAGE_PIN A2    IOSTANDARD LVCMOS18   } [get_ports { a_txc }]; # B58A_XDC: a_txc
#set_property -dict { PACKAGE_PIN E1    IOSTANDARD LVCMOS18   } [get_ports { a_txd[0] }]; # B58A_XDC: a_txd[0]
#set_property -dict { PACKAGE_PIN D1    IOSTANDARD LVCMOS18   } [get_ports { a_txd[1] }]; # B58A_XDC: a_txd[1]
#set_property -dict { PACKAGE_PIN F2    IOSTANDARD LVCMOS18   } [get_ports { a_txd[2] }]; # B58A_XDC: a_txd[2]
#set_property -dict { PACKAGE_PIN E2    IOSTANDARD LVCMOS18   } [get_ports { a_txd[3] }]; # B58A_XDC: a_txd[3]
#set_property -dict { PACKAGE_PIN F1    IOSTANDARD LVCMOS18   } [get_ports { a_tx_ctl }]; # B58A_XDC: a_tx_ctl
#set_property -dict { PACKAGE_PIN B1    IOSTANDARD LVCMOS18   } [get_ports { a_rst_n }]; # B58A_XDC: a_rst_n
#set_property -dict { PACKAGE_PIN F3    IOSTANDARD LVCMOS18   } [get_ports { a_mdio }]; # B58A_XDC: a_mdio
#set_property -dict { PACKAGE_PIN G3    IOSTANDARD LVCMOS18   } [get_ports { a_mdc }]; # B58A_XDC: a_mdc

## PL Ethernet port B (PHY3, J10A, RGMII, 1.8 V; built, not run)
#set_property -dict { PACKAGE_PIN K4    IOSTANDARD LVCMOS18   } [get_ports { b_rxc }]; # B58A_XDC: b_rxc
#set_property -dict { PACKAGE_PIN H1    IOSTANDARD LVCMOS18   } [get_ports { b_rxd[0] }]; # B58A_XDC: b_rxd[0]
#set_property -dict { PACKAGE_PIN K2    IOSTANDARD LVCMOS18   } [get_ports { b_rxd[1] }]; # B58A_XDC: b_rxd[1]
#set_property -dict { PACKAGE_PIN J2    IOSTANDARD LVCMOS18   } [get_ports { b_rxd[2] }]; # B58A_XDC: b_rxd[2]
#set_property -dict { PACKAGE_PIN H4    IOSTANDARD LVCMOS18   } [get_ports { b_rxd[3] }]; # B58A_XDC: b_rxd[3]
#set_property -dict { PACKAGE_PIN H3    IOSTANDARD LVCMOS18   } [get_ports { b_rx_ctl }]; # B58A_XDC: b_rx_ctl
#set_property -dict { PACKAGE_PIN J1    IOSTANDARD LVCMOS18   } [get_ports { b_txc }]; # B58A_XDC: b_txc
#set_property -dict { PACKAGE_PIN U9    IOSTANDARD LVCMOS18   } [get_ports { b_txd[0] }]; # B58A_XDC: b_txd[0]
#set_property -dict { PACKAGE_PIN V9    IOSTANDARD LVCMOS18   } [get_ports { b_txd[1] }]; # B58A_XDC: b_txd[1]
#set_property -dict { PACKAGE_PIN U8    IOSTANDARD LVCMOS18   } [get_ports { b_txd[2] }]; # B58A_XDC: b_txd[2]
#set_property -dict { PACKAGE_PIN V8    IOSTANDARD LVCMOS18   } [get_ports { b_txd[3] }]; # B58A_XDC: b_txd[3]
#set_property -dict { PACKAGE_PIN Y8    IOSTANDARD LVCMOS18   } [get_ports { b_tx_ctl }]; # B58A_XDC: b_tx_ctl
#set_property -dict { PACKAGE_PIN K1    IOSTANDARD LVCMOS18   } [get_ports { b_rst_n }]; # B58A_XDC: b_rst_n
#set_property -dict { PACKAGE_PIN T8    IOSTANDARD LVCMOS18   } [get_ports { b_mdio }]; # B58A_XDC: b_mdio
#set_property -dict { PACKAGE_PIN R8    IOSTANDARD LVCMOS18   } [get_ports { b_mdc }]; # B58A_XDC: b_mdc
