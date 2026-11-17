## Real Digital AUP-ZU3 (xczu3eg-sfvc784-2-e): PL pins
## Written by tools/board_pins_import.py from boards/aup_zu3/pins_import.yaml. Pin locations are facts about the board;
## this file is our own listing of them in one format, not a copy of a vendor file. Sources:
##   AUP_PINS: https://raw.githubusercontent.com/RealDigitalOrg/aup-zu3-bsp/b595ecdf37c7204129517de1773b0895bcdcc2ed/board-files/aup-zu3-4gb/1.0/part0_pins.xml (sha256 442919f0085c...; Real Digital's aup-zu3-bsp repository, no licence file; only pin facts are listed (the 8 GB board file has the same pins)); supplies every pin, its I/O standard and its function name
## Every port is commented out in the vendor style: the agent's board_constraints tool writes the lines a design uses.


## PL clock (100 MHz, differential)
#set_property -dict { PACKAGE_PIN D7    IOSTANDARD LVDS       } [get_ports { clk_100_p }]; # AUP_PINS: CLK_100_P
#set_property -dict { PACKAGE_PIN D6    IOSTANDARD LVDS       } [get_ports { clk_100_n }]; # AUP_PINS: CLK_100_N

## LEDs
#set_property -dict { PACKAGE_PIN AF5   IOSTANDARD LVCMOS12   } [get_ports { led[0] }]; # AUP_PINS: GPIO_LED_0
#set_property -dict { PACKAGE_PIN AE7   IOSTANDARD LVCMOS12   } [get_ports { led[1] }]; # AUP_PINS: GPIO_LED_1
#set_property -dict { PACKAGE_PIN AH2   IOSTANDARD LVCMOS12   } [get_ports { led[2] }]; # AUP_PINS: GPIO_LED_2
#set_property -dict { PACKAGE_PIN AE5   IOSTANDARD LVCMOS12   } [get_ports { led[3] }]; # AUP_PINS: GPIO_LED_3
#set_property -dict { PACKAGE_PIN AH1   IOSTANDARD LVCMOS12   } [get_ports { led[4] }]; # AUP_PINS: GPIO_LED_4
#set_property -dict { PACKAGE_PIN AE4   IOSTANDARD LVCMOS12   } [get_ports { led[5] }]; # AUP_PINS: GPIO_LED_5
#set_property -dict { PACKAGE_PIN AG1   IOSTANDARD LVCMOS12   } [get_ports { led[6] }]; # AUP_PINS: GPIO_LED_6
#set_property -dict { PACKAGE_PIN AF2   IOSTANDARD LVCMOS12   } [get_ports { led[7] }]; # AUP_PINS: GPIO_LED_7

## RGB LEDs
#set_property -dict { PACKAGE_PIN AE9   IOSTANDARD LVCMOS12   } [get_ports { rgbled0_B }]; # AUP_PINS: GPIO_RGBLED0_B_0
#set_property -dict { PACKAGE_PIN AD9   IOSTANDARD LVCMOS12   } [get_ports { rgbled0_G }]; # AUP_PINS: GPIO_RGBLED0_G_0
#set_property -dict { PACKAGE_PIN AD7   IOSTANDARD LVCMOS12   } [get_ports { rgbled0_R }]; # AUP_PINS: GPIO_RGBLED0_R_0
#set_property -dict { PACKAGE_PIN AF8   IOSTANDARD LVCMOS12   } [get_ports { rgbled1_B }]; # AUP_PINS: GPIO_RGBLED1_B_0
#set_property -dict { PACKAGE_PIN AE8   IOSTANDARD LVCMOS12   } [get_ports { rgbled1_G }]; # AUP_PINS: GPIO_RGBLED1_G_0
#set_property -dict { PACKAGE_PIN AG9   IOSTANDARD LVCMOS12   } [get_ports { rgbled1_R }]; # AUP_PINS: GPIO_RGBLED1_R_0
#set_property -dict { PACKAGE_PIN AG6   IOSTANDARD LVCMOS12   } [get_ports { rgbled2_B }]; # AUP_PINS: GPIO_RGBLED2_B_0
#set_property -dict { PACKAGE_PIN AG8   IOSTANDARD LVCMOS12   } [get_ports { rgbled2_G }]; # AUP_PINS: GPIO_RGBLED2_G_0
#set_property -dict { PACKAGE_PIN AF7   IOSTANDARD LVCMOS12   } [get_ports { rgbled2_R }]; # AUP_PINS: GPIO_RGBLED2_R_0
#set_property -dict { PACKAGE_PIN AG5   IOSTANDARD LVCMOS12   } [get_ports { rgbled3_B }]; # AUP_PINS: GPIO_RGBLED3_B_0
#set_property -dict { PACKAGE_PIN AH6   IOSTANDARD LVCMOS12   } [get_ports { rgbled3_G }]; # AUP_PINS: GPIO_RGBLED3_G_0
#set_property -dict { PACKAGE_PIN AF6   IOSTANDARD LVCMOS12   } [get_ports { rgbled3_R }]; # AUP_PINS: GPIO_RGBLED3_R_0

## Push buttons
#set_property -dict { PACKAGE_PIN AB6   IOSTANDARD LVCMOS12   } [get_ports { btn[0] }]; # AUP_PINS: GPIO_PB_0
#set_property -dict { PACKAGE_PIN AB7   IOSTANDARD LVCMOS12   } [get_ports { btn[1] }]; # AUP_PINS: GPIO_PB_1
#set_property -dict { PACKAGE_PIN AB2   IOSTANDARD LVCMOS12   } [get_ports { btn[2] }]; # AUP_PINS: GPIO_PB_2
#set_property -dict { PACKAGE_PIN AC6   IOSTANDARD LVCMOS12   } [get_ports { btn[3] }]; # AUP_PINS: GPIO_PB_3

## Slide switches
#set_property -dict { PACKAGE_PIN AB1   IOSTANDARD LVCMOS12   } [get_ports { sw[0] }]; # AUP_PINS: GPIO_SW_0
#set_property -dict { PACKAGE_PIN AF1   IOSTANDARD LVCMOS12   } [get_ports { sw[1] }]; # AUP_PINS: GPIO_SW_1
#set_property -dict { PACKAGE_PIN AE3   IOSTANDARD LVCMOS12   } [get_ports { sw[2] }]; # AUP_PINS: GPIO_SW_2
#set_property -dict { PACKAGE_PIN AC2   IOSTANDARD LVCMOS12   } [get_ports { sw[3] }]; # AUP_PINS: GPIO_SW_3
#set_property -dict { PACKAGE_PIN AC1   IOSTANDARD LVCMOS12   } [get_ports { sw[4] }]; # AUP_PINS: GPIO_SW_4
#set_property -dict { PACKAGE_PIN AD6   IOSTANDARD LVCMOS12   } [get_ports { sw[5] }]; # AUP_PINS: GPIO_SW_5
#set_property -dict { PACKAGE_PIN AD1   IOSTANDARD LVCMOS12   } [get_ports { sw[6] }]; # AUP_PINS: GPIO_SW_6
#set_property -dict { PACKAGE_PIN AD2   IOSTANDARD LVCMOS12   } [get_ports { sw[7] }]; # AUP_PINS: GPIO_SW_7

## Pmod
#set_property -dict { PACKAGE_PIN J12   IOSTANDARD LVCMOS33   } [get_ports { pmod_a[0] }]; # AUP_PINS: pmod0_0
#set_property -dict { PACKAGE_PIN H12   IOSTANDARD LVCMOS33   } [get_ports { pmod_a[1] }]; # AUP_PINS: pmod0_1
#set_property -dict { PACKAGE_PIN H11   IOSTANDARD LVCMOS33   } [get_ports { pmod_a[2] }]; # AUP_PINS: pmod0_2
#set_property -dict { PACKAGE_PIN G10   IOSTANDARD LVCMOS33   } [get_ports { pmod_a[3] }]; # AUP_PINS: pmod0_3
#set_property -dict { PACKAGE_PIN K13   IOSTANDARD LVCMOS33   } [get_ports { pmod_a[4] }]; # AUP_PINS: pmod0_4
#set_property -dict { PACKAGE_PIN K12   IOSTANDARD LVCMOS33   } [get_ports { pmod_a[5] }]; # AUP_PINS: pmod0_5
#set_property -dict { PACKAGE_PIN J11   IOSTANDARD LVCMOS33   } [get_ports { pmod_a[6] }]; # AUP_PINS: pmod0_6
#set_property -dict { PACKAGE_PIN J10   IOSTANDARD LVCMOS33   } [get_ports { pmod_a[7] }]; # AUP_PINS: pmod0_7
#set_property -dict { PACKAGE_PIN E12   IOSTANDARD LVCMOS33   } [get_ports { pmod_b[0] }]; # AUP_PINS: pmod1_0
#set_property -dict { PACKAGE_PIN D11   IOSTANDARD LVCMOS33   } [get_ports { pmod_b[1] }]; # AUP_PINS: pmod1_1
#set_property -dict { PACKAGE_PIN B11   IOSTANDARD LVCMOS33   } [get_ports { pmod_b[2] }]; # AUP_PINS: pmod1_2
#set_property -dict { PACKAGE_PIN A10   IOSTANDARD LVCMOS33   } [get_ports { pmod_b[3] }]; # AUP_PINS: pmod1_3
#set_property -dict { PACKAGE_PIN C11   IOSTANDARD LVCMOS33   } [get_ports { pmod_b[4] }]; # AUP_PINS: pmod1_4
#set_property -dict { PACKAGE_PIN B10   IOSTANDARD LVCMOS33   } [get_ports { pmod_b[5] }]; # AUP_PINS: pmod1_5
#set_property -dict { PACKAGE_PIN A12   IOSTANDARD LVCMOS33   } [get_ports { pmod_b[6] }]; # AUP_PINS: pmod1_6
#set_property -dict { PACKAGE_PIN A11   IOSTANDARD LVCMOS33   } [get_ports { pmod_b[7] }]; # AUP_PINS: pmod1_7
#set_property -dict { PACKAGE_PIN F12   IOSTANDARD LVCMOS33   } [get_ports { pmod_ab[0] }]; # AUP_PINS: pmod01_0
#set_property -dict { PACKAGE_PIN G11   IOSTANDARD LVCMOS33   } [get_ports { pmod_ab[1] }]; # AUP_PINS: pmod01_1
#set_property -dict { PACKAGE_PIN E10   IOSTANDARD LVCMOS33   } [get_ports { pmod_ab[2] }]; # AUP_PINS: pmod01_2
#set_property -dict { PACKAGE_PIN D10   IOSTANDARD LVCMOS33   } [get_ports { pmod_ab[3] }]; # AUP_PINS: pmod01_3
#set_property -dict { PACKAGE_PIN F10   IOSTANDARD LVCMOS33   } [get_ports { pmod_ab[4] }]; # AUP_PINS: pmod01_4
#set_property -dict { PACKAGE_PIN F11   IOSTANDARD LVCMOS33   } [get_ports { pmod_ab[5] }]; # AUP_PINS: pmod01_5

## Grove
#set_property -dict { PACKAGE_PIN AE14  IOSTANDARD LVCMOS33   } [get_ports { grove0[0] }]; # AUP_PINS: GPIO_GROVE0_0
#set_property -dict { PACKAGE_PIN AE13  IOSTANDARD LVCMOS33   } [get_ports { grove0[1] }]; # AUP_PINS: GPIO_GROVE0_1
#set_property -dict { PACKAGE_PIN AD15  IOSTANDARD LVCMOS33   } [get_ports { grove1[0] }]; # AUP_PINS: GPIO_GROVE1_0
#set_property -dict { PACKAGE_PIN AD14  IOSTANDARD LVCMOS33   } [get_ports { grove1[1] }]; # AUP_PINS: GPIO_GROVE1_1

## Raspberry Pi header
#set_property -dict { PACKAGE_PIN AF10  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[0] }]; # AUP_PINS: raspberry_pi_0
#set_property -dict { PACKAGE_PIN AG10  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[1] }]; # AUP_PINS: raspberry_pi_1
#set_property -dict { PACKAGE_PIN AC12  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[2] }]; # AUP_PINS: raspberry_pi_2
#set_property -dict { PACKAGE_PIN AD12  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[3] }]; # AUP_PINS: raspberry_pi_3
#set_property -dict { PACKAGE_PIN AE12  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[4] }]; # AUP_PINS: raspberry_pi_4
#set_property -dict { PACKAGE_PIN AE10  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[5] }]; # AUP_PINS: raspberry_pi_5
#set_property -dict { PACKAGE_PIN AB11  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[6] }]; # AUP_PINS: raspberry_pi_6
#set_property -dict { PACKAGE_PIN AD11  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[7] }]; # AUP_PINS: raspberry_pi_7
#set_property -dict { PACKAGE_PIN AG11  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[8] }]; # AUP_PINS: raspberry_pi_8
#set_property -dict { PACKAGE_PIN AH11  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[9] }]; # AUP_PINS: raspberry_pi_9
#set_property -dict { PACKAGE_PIN AH12  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[10] }]; # AUP_PINS: raspberry_pi_10
#set_property -dict { PACKAGE_PIN AH10  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[11] }]; # AUP_PINS: raspberry_pi_11
#set_property -dict { PACKAGE_PIN AD10  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[12] }]; # AUP_PINS: raspberry_pi_12
#set_property -dict { PACKAGE_PIN AA11  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[13] }]; # AUP_PINS: raspberry_pi_13
#set_property -dict { PACKAGE_PIN AE15  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[14] }]; # AUP_PINS: raspberry_pi_14
#set_property -dict { PACKAGE_PIN AF13  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[15] }]; # AUP_PINS: raspberry_pi_15
#set_property -dict { PACKAGE_PIN AB10  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[16] }]; # AUP_PINS: raspberry_pi_16
#set_property -dict { PACKAGE_PIN AG14  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[17] }]; # AUP_PINS: raspberry_pi_17
#set_property -dict { PACKAGE_PIN AC11  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[18] }]; # AUP_PINS: raspberry_pi_18
#set_property -dict { PACKAGE_PIN AB9   IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[19] }]; # AUP_PINS: raspberry_pi_19
#set_property -dict { PACKAGE_PIN AA10  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[20] }]; # AUP_PINS: raspberry_pi_20
#set_property -dict { PACKAGE_PIN Y9    IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[21] }]; # AUP_PINS: raspberry_pi_21
#set_property -dict { PACKAGE_PIN AH13  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[22] }]; # AUP_PINS: raspberry_pi_22
#set_property -dict { PACKAGE_PIN AG13  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[23] }]; # AUP_PINS: raspberry_pi_23
#set_property -dict { PACKAGE_PIN AF12  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[24] }]; # AUP_PINS: raspberry_pi_24
#set_property -dict { PACKAGE_PIN AF11  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[25] }]; # AUP_PINS: raspberry_pi_25
#set_property -dict { PACKAGE_PIN AA8   IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[26] }]; # AUP_PINS: raspberry_pi_26
#set_property -dict { PACKAGE_PIN AH14  IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[27] }]; # AUP_PINS: raspberry_pi_27
