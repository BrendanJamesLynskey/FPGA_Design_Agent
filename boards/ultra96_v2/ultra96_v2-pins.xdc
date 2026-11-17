## Avnet Ultra96-V2 (xczu3eg-sbva484-1-i): the PL pins in the AMD board file (none is a clock or a user LED)
## Written by tools/board_pins_import.py from boards/ultra96_v2/pins_import.yaml. Pin locations are facts about the board;
## this file is our own listing of them in one format, not a copy of a vendor file. Sources:
##   U96_PINS: https://raw.githubusercontent.com/Xilinx/XilinxBoardStore/40fad97cf36f3d856c6759d83c2390de1566ffa7/boards/Avnet/ultra96v2/1.2/part0_pins.xml (sha256 0bdc3fb606ec...; Avnet, Apache-2.0); supplies the PL-connected UART, I2C and radio-LED pins
## Every port is commented out in the vendor style: the agent's board_constraints tool writes the lines a design uses.

#set_property -dict { PACKAGE_PIN AU15  IOSTANDARD LVCMOS18   } [get_ports { uart_pl_tx }]; # U96_PINS: uart2_PL_TX
#set_property -dict { PACKAGE_PIN AT15  IOSTANDARD LVCMOS18   } [get_ports { uart_pl_rx }]; # U96_PINS: uart2_PL_RX
#set_property -dict { PACKAGE_PIN AT16  IOSTANDARD LVCMOS18   } [get_ports { IIC0_SCL_MAIN }]; # U96_PINS: IIC0_SCL_MAIN
#set_property -dict { PACKAGE_PIN AW16  IOSTANDARD LVCMOS18   } [get_ports { IIC0_SDA_MAIN }]; # U96_PINS: IIC0_SDA_MAIN
#set_property -dict { PACKAGE_PIN AV16  IOSTANDARD LVCMOS12   } [get_ports { IIC1_SCL_MAIN }]; # U96_PINS: IIC1_SCL_MAIN
#set_property -dict { PACKAGE_PIN AV13  IOSTANDARD LVCMOS12   } [get_ports { IIC1_SDA_MAIN }]; # U96_PINS: IIC1_SDA_MAIN
#set_property -dict { PACKAGE_PIN A9    IOSTANDARD LVCMOS18   } [get_ports { RADIO_LED0 }]; # U96_PINS: RADIO_LED0
#set_property -dict { PACKAGE_PIN B9    IOSTANDARD LVCMOS18   } [get_ports { RADIO_LED1 }]; # U96_PINS: RADIO_LED1
#set_property -dict { PACKAGE_PIN A3    IOSTANDARD LVCMOS18   } [get_ports { PL_RADIO_RESET }]; # U96_PINS: PL_RADIO_RESET
#set_property -dict { PACKAGE_PIN A2    IOSTANDARD LVCMOS18   } [get_ports { HSIC_STR }]; # U96_PINS: HSIC_STR
#set_property -dict { PACKAGE_PIN J19   IOSTANDARD DIFF_SSTL12 } [get_ports { GTR_CLK1_DP_27M_P }]; # U96_PINS: GTR_CLK1_DP_27M_P
#set_property -dict { PACKAGE_PIN J18   IOSTANDARD DIFF_SSTL12 } [get_ports { GTR_CLK1_DP_27M_N }]; # U96_PINS: GTR_CLK1_DP_27M_N
