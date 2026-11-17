## AMD ZCU104 (xczu7ev-ffvc1156-2-e): PL pins from the AMD board file (no DDR4, no FMC)
## Written by tools/board_pins_import.py from boards/zcu104/pins_import.yaml. Pin locations are facts about the board;
## this file is our own listing of them in one format, not a copy of a vendor file. Sources:
##   ZCU104_PINS: https://raw.githubusercontent.com/Xilinx/XilinxBoardStore/40fad97cf36f3d856c6759d83c2390de1566ffa7/boards/Xilinx/zcu104/1.1/part0_pins.xml (sha256 7f94d3b6c0cc...; AMD XilinxBoardStore board file, Apache-2.0); supplies clock, UART, switch, button and LED pins and their standards
## Every port is commented out in the vendor style: the agent's board_constraints tool writes the lines a design uses.
## Left out because no source gives its I/O standard (a standard is never invented): uart_pl_tx on C19 (ZCU104_PINS); uart_pl_rx on A20 (ZCU104_PINS)

#set_property -dict { PACKAGE_PIN AH18  IOSTANDARD DIFF_SSTL12 } [get_ports { clk_300_p }]; # ZCU104_PINS: CLK_300_P
#set_property -dict { PACKAGE_PIN AH17  IOSTANDARD DIFF_SSTL12 } [get_ports { clk_300_n }]; # ZCU104_PINS: CLK_300_N
#set_property -dict { PACKAGE_PIN M11   IOSTANDARD LVCMOS33   } [get_ports { cpu_reset }]; # ZCU104_PINS: CPU_RESET
#set_property -dict { PACKAGE_PIN E4    IOSTANDARD LVCMOS33   } [get_ports { sw[0] }]; # ZCU104_PINS: GPIO_DIP_SW0
#set_property -dict { PACKAGE_PIN D4    IOSTANDARD LVCMOS33   } [get_ports { sw[1] }]; # ZCU104_PINS: GPIO_DIP_SW1
#set_property -dict { PACKAGE_PIN F5    IOSTANDARD LVCMOS33   } [get_ports { sw[2] }]; # ZCU104_PINS: GPIO_DIP_SW2
#set_property -dict { PACKAGE_PIN F4    IOSTANDARD LVCMOS33   } [get_ports { sw[3] }]; # ZCU104_PINS: GPIO_DIP_SW3
#set_property -dict { PACKAGE_PIN D5    IOSTANDARD LVCMOS33   } [get_ports { led[0] }]; # ZCU104_PINS: GPIO_LED_0_LS
#set_property -dict { PACKAGE_PIN D6    IOSTANDARD LVCMOS33   } [get_ports { led[1] }]; # ZCU104_PINS: GPIO_LED_1_LS
#set_property -dict { PACKAGE_PIN A5    IOSTANDARD LVCMOS33   } [get_ports { led[2] }]; # ZCU104_PINS: GPIO_LED_2_LS
#set_property -dict { PACKAGE_PIN B5    IOSTANDARD LVCMOS33   } [get_ports { led[3] }]; # ZCU104_PINS: GPIO_LED_3_LS
#set_property -dict { PACKAGE_PIN B4    IOSTANDARD LVCMOS33   } [get_ports { btn[0] }]; # ZCU104_PINS: GPIO_PB_SW0
#set_property -dict { PACKAGE_PIN C4    IOSTANDARD LVCMOS33   } [get_ports { btn[1] }]; # ZCU104_PINS: GPIO_PB_SW1
#set_property -dict { PACKAGE_PIN B3    IOSTANDARD LVCMOS33   } [get_ports { btn[2] }]; # ZCU104_PINS: GPIO_PB_SW2
#set_property -dict { PACKAGE_PIN C3    IOSTANDARD LVCMOS33   } [get_ports { btn[3] }]; # ZCU104_PINS: GPIO_PB_SW3
