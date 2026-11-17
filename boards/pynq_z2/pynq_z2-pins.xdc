## TUL PYNQ-Z2 (xc7z020clg400-1): PL pins
## Written by tools/board_pins_import.py from boards/pynq_z2/pins_import.yaml. Pin locations are facts about the board;
## this file is our own listing of them in one format, not a copy of a vendor file. Sources:
##   PYNQZ2_PINS: https://raw.githubusercontent.com/Xilinx/XilinxBoardStore/40fad97cf36f3d856c6759d83c2390de1566ffa7/boards/TUL/pynq-z2/A.0/part0_pins.xml (sha256 bf7618420270...; AMD XilinxBoardStore board file, TUL; no licence text in this file, so only pin facts are listed); supplies every pin, its I/O standard and its function name
## Every port is commented out in the vendor style: the agent's board_constraints tool writes the lines a design uses.


## PL clock
#set_property -dict { PACKAGE_PIN H16   IOSTANDARD LVCMOS33   } [get_ports { clk }]; # PYNQZ2_PINS: sys_clk

## LEDs
#set_property -dict { PACKAGE_PIN R14   IOSTANDARD LVCMOS33   } [get_ports { led[0] }]; # PYNQZ2_PINS: leds_4bits_tri_o_0
#set_property -dict { PACKAGE_PIN P14   IOSTANDARD LVCMOS33   } [get_ports { led[1] }]; # PYNQZ2_PINS: leds_4bits_tri_o_1
#set_property -dict { PACKAGE_PIN N16   IOSTANDARD LVCMOS33   } [get_ports { led[2] }]; # PYNQZ2_PINS: leds_4bits_tri_o_2
#set_property -dict { PACKAGE_PIN M14   IOSTANDARD LVCMOS33   } [get_ports { led[3] }]; # PYNQZ2_PINS: leds_4bits_tri_o_3

## RGB LEDs
#set_property -dict { PACKAGE_PIN L15   IOSTANDARD LVCMOS33   } [get_ports { rgb_led[0] }]; # PYNQZ2_PINS: rgb_led_tri_o_0
#set_property -dict { PACKAGE_PIN G17   IOSTANDARD LVCMOS33   } [get_ports { rgb_led[1] }]; # PYNQZ2_PINS: rgb_led_tri_o_1
#set_property -dict { PACKAGE_PIN N15   IOSTANDARD LVCMOS33   } [get_ports { rgb_led[2] }]; # PYNQZ2_PINS: rgb_led_tri_o_2
#set_property -dict { PACKAGE_PIN G14   IOSTANDARD LVCMOS33   } [get_ports { rgb_led[3] }]; # PYNQZ2_PINS: rgb_led_tri_o_3
#set_property -dict { PACKAGE_PIN L14   IOSTANDARD LVCMOS33   } [get_ports { rgb_led[4] }]; # PYNQZ2_PINS: rgb_led_tri_o_4
#set_property -dict { PACKAGE_PIN M15   IOSTANDARD LVCMOS33   } [get_ports { rgb_led[5] }]; # PYNQZ2_PINS: rgb_led_tri_o_5

## Push buttons
#set_property -dict { PACKAGE_PIN D19   IOSTANDARD LVCMOS33   } [get_ports { btn[0] }]; # PYNQZ2_PINS: btns_4bits_tri_i_0
#set_property -dict { PACKAGE_PIN D20   IOSTANDARD LVCMOS33   } [get_ports { btn[1] }]; # PYNQZ2_PINS: btns_4bits_tri_i_1
#set_property -dict { PACKAGE_PIN L20   IOSTANDARD LVCMOS33   } [get_ports { btn[2] }]; # PYNQZ2_PINS: btns_4bits_tri_i_2
#set_property -dict { PACKAGE_PIN L19   IOSTANDARD LVCMOS33   } [get_ports { btn[3] }]; # PYNQZ2_PINS: btns_4bits_tri_i_3

## Slide switches
#set_property -dict { PACKAGE_PIN M20   IOSTANDARD LVCMOS33   } [get_ports { sw[0] }]; # PYNQZ2_PINS: sws_2bits_tri_i_0
#set_property -dict { PACKAGE_PIN M19   IOSTANDARD LVCMOS33   } [get_ports { sw[1] }]; # PYNQZ2_PINS: sws_2bits_tri_i_1

## Pmod
#set_property -dict { PACKAGE_PIN Y18   IOSTANDARD LVCMOS33   } [get_ports { pmoda[1] }]; # PYNQZ2_PINS: JA1
#set_property -dict { PACKAGE_PIN Y19   IOSTANDARD LVCMOS33   } [get_ports { pmoda[2] }]; # PYNQZ2_PINS: JA2
#set_property -dict { PACKAGE_PIN Y16   IOSTANDARD LVCMOS33   } [get_ports { pmoda[3] }]; # PYNQZ2_PINS: JA3
#set_property -dict { PACKAGE_PIN Y17   IOSTANDARD LVCMOS33   } [get_ports { pmoda[4] }]; # PYNQZ2_PINS: JA4
#set_property -dict { PACKAGE_PIN U18   IOSTANDARD LVCMOS33   } [get_ports { pmoda[7] }]; # PYNQZ2_PINS: JA7
#set_property -dict { PACKAGE_PIN U19   IOSTANDARD LVCMOS33   } [get_ports { pmoda[8] }]; # PYNQZ2_PINS: JA8
#set_property -dict { PACKAGE_PIN W18   IOSTANDARD LVCMOS33   } [get_ports { pmoda[9] }]; # PYNQZ2_PINS: JA9
#set_property -dict { PACKAGE_PIN W19   IOSTANDARD LVCMOS33   } [get_ports { pmoda[10] }]; # PYNQZ2_PINS: JA10
#set_property -dict { PACKAGE_PIN W14   IOSTANDARD LVCMOS33   } [get_ports { pmodb[1] }]; # PYNQZ2_PINS: JB1
#set_property -dict { PACKAGE_PIN Y14   IOSTANDARD LVCMOS33   } [get_ports { pmodb[2] }]; # PYNQZ2_PINS: JB2
#set_property -dict { PACKAGE_PIN T11   IOSTANDARD LVCMOS33   } [get_ports { pmodb[3] }]; # PYNQZ2_PINS: JB3
#set_property -dict { PACKAGE_PIN T10   IOSTANDARD LVCMOS33   } [get_ports { pmodb[4] }]; # PYNQZ2_PINS: JB4
#set_property -dict { PACKAGE_PIN V16   IOSTANDARD LVCMOS33   } [get_ports { pmodb[7] }]; # PYNQZ2_PINS: JB7
#set_property -dict { PACKAGE_PIN W16   IOSTANDARD LVCMOS33   } [get_ports { pmodb[8] }]; # PYNQZ2_PINS: JB8
#set_property -dict { PACKAGE_PIN V12   IOSTANDARD LVCMOS33   } [get_ports { pmodb[9] }]; # PYNQZ2_PINS: JB9
#set_property -dict { PACKAGE_PIN W13   IOSTANDARD LVCMOS33   } [get_ports { pmodb[10] }]; # PYNQZ2_PINS: JB10

## Arduino header
#set_property -dict { PACKAGE_PIN T14   IOSTANDARD LVCMOS33   } [get_ports { arduino_io[0] }]; # PYNQZ2_PINS: arduino_a0_a13_tri_i_0
#set_property -dict { PACKAGE_PIN U12   IOSTANDARD LVCMOS33   } [get_ports { arduino_io[1] }]; # PYNQZ2_PINS: arduino_a0_a13_tri_i_1
#set_property -dict { PACKAGE_PIN U13   IOSTANDARD LVCMOS33   } [get_ports { arduino_io[2] }]; # PYNQZ2_PINS: arduino_a0_a13_tri_i_2
#set_property -dict { PACKAGE_PIN V13   IOSTANDARD LVCMOS33   } [get_ports { arduino_io[3] }]; # PYNQZ2_PINS: arduino_a0_a13_tri_i_3
#set_property -dict { PACKAGE_PIN V15   IOSTANDARD LVCMOS33   } [get_ports { arduino_io[4] }]; # PYNQZ2_PINS: arduino_a0_a13_tri_i_4
#set_property -dict { PACKAGE_PIN T15   IOSTANDARD LVCMOS33   } [get_ports { arduino_io[5] }]; # PYNQZ2_PINS: arduino_a0_a13_tri_i_5
#set_property -dict { PACKAGE_PIN R16   IOSTANDARD LVCMOS33   } [get_ports { arduino_io[6] }]; # PYNQZ2_PINS: arduino_a0_a13_tri_i_6
#set_property -dict { PACKAGE_PIN U17   IOSTANDARD LVCMOS33   } [get_ports { arduino_io[7] }]; # PYNQZ2_PINS: arduino_a0_a13_tri_i_7
#set_property -dict { PACKAGE_PIN V17   IOSTANDARD LVCMOS33   } [get_ports { arduino_io[8] }]; # PYNQZ2_PINS: arduino_a0_a13_tri_i_8
#set_property -dict { PACKAGE_PIN V18   IOSTANDARD LVCMOS33   } [get_ports { arduino_io[9] }]; # PYNQZ2_PINS: arduino_a0_a13_tri_i_9
#set_property -dict { PACKAGE_PIN T16   IOSTANDARD LVCMOS33   } [get_ports { arduino_io[10] }]; # PYNQZ2_PINS: arduino_a0_a13_tri_i_10
#set_property -dict { PACKAGE_PIN R17   IOSTANDARD LVCMOS33   } [get_ports { arduino_io[11] }]; # PYNQZ2_PINS: arduino_a0_a13_tri_i_11
#set_property -dict { PACKAGE_PIN P18   IOSTANDARD LVCMOS33   } [get_ports { arduino_io[12] }]; # PYNQZ2_PINS: arduino_a0_a13_tri_i_12
#set_property -dict { PACKAGE_PIN N17   IOSTANDARD LVCMOS33   } [get_ports { arduino_io[13] }]; # PYNQZ2_PINS: arduino_a0_a13_tri_i_13
#set_property -dict { PACKAGE_PIN Y11   IOSTANDARD LVCMOS33   } [get_ports { arduino_a0 }]; # PYNQZ2_PINS: arduino_a0
#set_property -dict { PACKAGE_PIN Y12   IOSTANDARD LVCMOS33   } [get_ports { arduino_a1 }]; # PYNQZ2_PINS: arduino_a1
#set_property -dict { PACKAGE_PIN W11   IOSTANDARD LVCMOS33   } [get_ports { arduino_a2 }]; # PYNQZ2_PINS: arduino_a2
#set_property -dict { PACKAGE_PIN V11   IOSTANDARD LVCMOS33   } [get_ports { arduino_a3 }]; # PYNQZ2_PINS: arduino_a3
#set_property -dict { PACKAGE_PIN T5    IOSTANDARD LVCMOS33   } [get_ports { arduino_a4 }]; # PYNQZ2_PINS: arduino_a4
#set_property -dict { PACKAGE_PIN U10   IOSTANDARD LVCMOS33   } [get_ports { arduino_a5 }]; # PYNQZ2_PINS: arduino_a5

## Raspberry Pi header
#set_property -dict { PACKAGE_PIN W18   IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[0] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_0
#set_property -dict { PACKAGE_PIN W19   IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[1] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_1
#set_property -dict { PACKAGE_PIN Y18   IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[2] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_2
#set_property -dict { PACKAGE_PIN Y19   IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[3] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_3
#set_property -dict { PACKAGE_PIN U18   IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[4] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_4
#set_property -dict { PACKAGE_PIN U19   IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[5] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_5
#set_property -dict { PACKAGE_PIN F19   IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[6] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_6
#set_property -dict { PACKAGE_PIN V10   IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[7] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_7
#set_property -dict { PACKAGE_PIN V8    IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[8] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_8
#set_property -dict { PACKAGE_PIN W10   IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[9] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_9
#set_property -dict { PACKAGE_PIN B20   IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[10] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_10
#set_property -dict { PACKAGE_PIN W8    IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[11] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_11
#set_property -dict { PACKAGE_PIN V6    IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[12] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_12
#set_property -dict { PACKAGE_PIN Y6    IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[13] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_13
#set_property -dict { PACKAGE_PIN B19   IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[14] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_14
#set_property -dict { PACKAGE_PIN U7    IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[15] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_15
#set_property -dict { PACKAGE_PIN C20   IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[16] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_16
#set_property -dict { PACKAGE_PIN Y8    IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[17] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_17
#set_property -dict { PACKAGE_PIN A20   IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[18] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_18
#set_property -dict { PACKAGE_PIN Y9    IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[19] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_19
#set_property -dict { PACKAGE_PIN U8    IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[20] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_20
#set_property -dict { PACKAGE_PIN W6    IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[21] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_21
#set_property -dict { PACKAGE_PIN Y7    IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[22] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_22
#set_property -dict { PACKAGE_PIN F20   IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[23] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_23
#set_property -dict { PACKAGE_PIN W9    IOSTANDARD LVCMOS33   } [get_ports { rpi_gpio[24] }]; # PYNQZ2_PINS: raspberry_pi_tri_i_24

## HDMI
#set_property -dict { PACKAGE_PIN T19   IOSTANDARD LVCMOS33   } [get_ports { hdmi_rx_hpd }]; # PYNQZ2_PINS: hdmi_rx_hpd
#set_property -dict { PACKAGE_PIN N18   IOSTANDARD TMDS_33    } [get_ports { TMDS_IN_clk_p }]; # PYNQZ2_PINS: TMDS_IN_clk_p
#set_property -dict { PACKAGE_PIN P19   IOSTANDARD TMDS_33    } [get_ports { TMDS_IN_clk_n }]; # PYNQZ2_PINS: TMDS_IN_clk_n
#set_property -dict { PACKAGE_PIN V20   IOSTANDARD TMDS_33    } [get_ports { TMDS_IN_data_p_0 }]; # PYNQZ2_PINS: TMDS_IN_data_p_0
#set_property -dict { PACKAGE_PIN T20   IOSTANDARD TMDS_33    } [get_ports { TMDS_IN_data_p_1 }]; # PYNQZ2_PINS: TMDS_IN_data_p_1
#set_property -dict { PACKAGE_PIN N20   IOSTANDARD TMDS_33    } [get_ports { TMDS_IN_data_p_2 }]; # PYNQZ2_PINS: TMDS_IN_data_p_2
#set_property -dict { PACKAGE_PIN W20   IOSTANDARD TMDS_33    } [get_ports { TMDS_IN_data_n_0 }]; # PYNQZ2_PINS: TMDS_IN_data_n_0
#set_property -dict { PACKAGE_PIN U20   IOSTANDARD TMDS_33    } [get_ports { TMDS_IN_data_n_1 }]; # PYNQZ2_PINS: TMDS_IN_data_n_1
#set_property -dict { PACKAGE_PIN P20   IOSTANDARD TMDS_33    } [get_ports { TMDS_IN_data_n_2 }]; # PYNQZ2_PINS: TMDS_IN_data_n_2
#set_property -dict { PACKAGE_PIN R19   IOSTANDARD LVCMOS33   } [get_ports { hdmi_tx_hpd }]; # PYNQZ2_PINS: hdmi_tx_hpd
#set_property -dict { PACKAGE_PIN L16   IOSTANDARD LVCMOS33   } [get_ports { TMDS_OUT_clk_p }]; # PYNQZ2_PINS: TMDS_OUT_clk_p
#set_property -dict { PACKAGE_PIN L17   IOSTANDARD LVCMOS33   } [get_ports { TMDS_OUT_clk_n }]; # PYNQZ2_PINS: TMDS_OUT_clk_n
#set_property -dict { PACKAGE_PIN K17   IOSTANDARD LVCMOS33   } [get_ports { TMDS_OUT_data_p_0 }]; # PYNQZ2_PINS: TMDS_OUT_data_p_0
#set_property -dict { PACKAGE_PIN K19   IOSTANDARD LVCMOS33   } [get_ports { TMDS_OUT_data_p_1 }]; # PYNQZ2_PINS: TMDS_OUT_data_p_1
#set_property -dict { PACKAGE_PIN J18   IOSTANDARD LVCMOS33   } [get_ports { TMDS_OUT_data_p_2 }]; # PYNQZ2_PINS: TMDS_OUT_data_p_2
#set_property -dict { PACKAGE_PIN K18   IOSTANDARD LVCMOS33   } [get_ports { TMDS_OUT_data_n_0 }]; # PYNQZ2_PINS: TMDS_OUT_data_n_0
#set_property -dict { PACKAGE_PIN J19   IOSTANDARD LVCMOS33   } [get_ports { TMDS_OUT_data_n_1 }]; # PYNQZ2_PINS: TMDS_OUT_data_n_1
#set_property -dict { PACKAGE_PIN H18   IOSTANDARD LVCMOS33   } [get_ports { TMDS_OUT_data_n_2 }]; # PYNQZ2_PINS: TMDS_OUT_data_n_2
#set_property -dict { PACKAGE_PIN U14   IOSTANDARD LVCMOS33   } [get_ports { hdmi_in_ddc_scl }]; # PYNQZ2_PINS: hdmi_in_ddc_scl
#set_property -dict { PACKAGE_PIN U15   IOSTANDARD LVCMOS33   } [get_ports { hdmi_in_ddc_sda }]; # PYNQZ2_PINS: hdmi_in_ddc_sda
#set_property -dict { PACKAGE_PIN G15   IOSTANDARD LVCMOS33   } [get_ports { hdmi_tx_cec }]; # PYNQZ2_PINS: hdmi_tx_cec

## Audio codec
#set_property -dict { PACKAGE_PIN T9    IOSTANDARD LVCMOS33   } [get_ports { audio_sd_i }]; # PYNQZ2_PINS: audio_sd_i
#set_property -dict { PACKAGE_PIN U9    IOSTANDARD LVCMOS33   } [get_ports { audio_sc_i }]; # PYNQZ2_PINS: audio_sc_i
#set_property -dict { PACKAGE_PIN M17   IOSTANDARD LVCMOS33   } [get_ports { audio_adr_0 }]; # PYNQZ2_PINS: audio_adr_0
#set_property -dict { PACKAGE_PIN M18   IOSTANDARD LVCMOS33   } [get_ports { audio_adr_1 }]; # PYNQZ2_PINS: audio_adr_1
#set_property -dict { PACKAGE_PIN U5    IOSTANDARD LVCMOS33   } [get_ports { audio_clk }]; # PYNQZ2_PINS: audio_clk
#set_property -dict { PACKAGE_PIN R18   IOSTANDARD LVCMOS33   } [get_ports { bclk_i }]; # PYNQZ2_PINS: bclk_i
#set_property -dict { PACKAGE_PIN T17   IOSTANDARD LVCMOS33   } [get_ports { wclk_i }]; # PYNQZ2_PINS: wclk_i
#set_property -dict { PACKAGE_PIN F17   IOSTANDARD LVCMOS33   } [get_ports { sdata_in_i }]; # PYNQZ2_PINS: sdata_in_i

## Other
#set_property -dict { PACKAGE_PIN P15   IOSTANDARD LVCMOS33   } [get_ports { i2c_scl_i }]; # PYNQZ2_PINS: i2c_scl_i
#set_property -dict { PACKAGE_PIN P16   IOSTANDARD LVCMOS33   } [get_ports { i2c_sda_i }]; # PYNQZ2_PINS: i2c_sda_i
#set_property -dict { PACKAGE_PIN W15   IOSTANDARD LVCMOS33   } [get_ports { spi_miso_i }]; # PYNQZ2_PINS: spi_miso_i
#set_property -dict { PACKAGE_PIN T12   IOSTANDARD LVCMOS33   } [get_ports { spi_mosi_i }]; # PYNQZ2_PINS: spi_mosi_i
#set_property -dict { PACKAGE_PIN H15   IOSTANDARD LVCMOS33   } [get_ports { spi_sclk_i }]; # PYNQZ2_PINS: spi_sclk_i
#set_property -dict { PACKAGE_PIN F16   IOSTANDARD LVCMOS33   } [get_ports { spi_ss_i }]; # PYNQZ2_PINS: spi_ss_i
#set_property -dict { PACKAGE_PIN Y16   IOSTANDARD LVCMOS33   } [get_ports { respberry_sd_i }]; # PYNQZ2_PINS: respberry_sd_i
#set_property -dict { PACKAGE_PIN Y17   IOSTANDARD LVCMOS33   } [get_ports { respberry_sc_i }]; # PYNQZ2_PINS: respberry_sc_i
#set_property -dict { PACKAGE_PIN G18   IOSTANDARD LVCMOS33   } [get_ports { sdada_out_i }]; # PYNQZ2_PINS: sdada_out_i
