## Red Pitaya STEMlab 125-14, original generation (xc7z010clg400-1): PL pins
## Written by tools/board_pins_import.py from boards/redpitaya_stemlab_125_14/pins_import.yaml. Pin locations are facts about the board;
## this file is our own listing of them in one format, not a copy of a vendor file. Sources:
##   RPFPGA_XDC: https://raw.githubusercontent.com/RedPitaya/RedPitaya-FPGA/728a4f37e9c0a9b5ba1d9b7a0d44c38bbd2dc674/sdc/red_pitaya.xdc (sha256 ec5aa406fefd...; Red Pitaya d.o.o., BSD 3-clause (LICENSE of the RedPitaya-FPGA repository, covering the fpga directory); only pin facts are listed, nothing is copied); supplies pin locations and port names of the shell
##   RPFPGA_BRD: https://raw.githubusercontent.com/RedPitaya/RedPitaya-FPGA/728a4f37e9c0a9b5ba1d9b7a0d44c38bbd2dc674/brd/redpitaya/1.1/part0_pins.xml (sha256 46369ef3fad3...; Red Pitaya d.o.o., BSD 3-clause (same repository); only pin facts are listed); supplies the I/O standard of each pin it lists (board file version 1.1, xc7z010clg400-1)
## Every port is commented out in the vendor style: the agent's board_constraints tool writes the lines a design uses.


## PL clock (125 MHz, differential, from the ADC clock tree)
#set_property -dict { PACKAGE_PIN U18   IOSTANDARD DIFF_HSTL_I_18 } [get_ports { adc_clk_p }]; # RPFPGA_XDC: adc_clk_i[1]
#set_property -dict { PACKAGE_PIN U19   IOSTANDARD DIFF_HSTL_I_18 } [get_ports { adc_clk_n }]; # RPFPGA_XDC: adc_clk_i[0]

## LEDs
#set_property -dict { PACKAGE_PIN F16   IOSTANDARD LVCMOS33   } [get_ports { led[0] }]; # RPFPGA_XDC: led_o[0]
#set_property -dict { PACKAGE_PIN F17   IOSTANDARD LVCMOS33   } [get_ports { led[1] }]; # RPFPGA_XDC: led_o[1]
#set_property -dict { PACKAGE_PIN G15   IOSTANDARD LVCMOS33   } [get_ports { led[2] }]; # RPFPGA_XDC: led_o[2]
#set_property -dict { PACKAGE_PIN H15   IOSTANDARD LVCMOS33   } [get_ports { led[3] }]; # RPFPGA_XDC: led_o[3]
#set_property -dict { PACKAGE_PIN K14   IOSTANDARD LVCMOS33   } [get_ports { led[4] }]; # RPFPGA_XDC: led_o[4]
#set_property -dict { PACKAGE_PIN G14   IOSTANDARD LVCMOS33   } [get_ports { led[5] }]; # RPFPGA_XDC: led_o[5]
#set_property -dict { PACKAGE_PIN J15   IOSTANDARD LVCMOS33   } [get_ports { led[6] }]; # RPFPGA_XDC: led_o[6]
#set_property -dict { PACKAGE_PIN J14   IOSTANDARD LVCMOS33   } [get_ports { led[7] }]; # RPFPGA_XDC: led_o[7]

## Extension connector E1, positive lines (DIOn_P)
#set_property -dict { PACKAGE_PIN G17   IOSTANDARD LVCMOS33   } [get_ports { exp_p_io[0] }]; # RPFPGA_XDC: exp_p_io[0]
#set_property -dict { PACKAGE_PIN H16   IOSTANDARD LVCMOS33   } [get_ports { exp_p_io[1] }]; # RPFPGA_XDC: exp_p_io[1]
#set_property -dict { PACKAGE_PIN J18   IOSTANDARD LVCMOS33   } [get_ports { exp_p_io[2] }]; # RPFPGA_XDC: exp_p_io[2]
#set_property -dict { PACKAGE_PIN K17   IOSTANDARD LVCMOS33   } [get_ports { exp_p_io[3] }]; # RPFPGA_XDC: exp_p_io[3]
#set_property -dict { PACKAGE_PIN L14   IOSTANDARD LVCMOS33   } [get_ports { exp_p_io[4] }]; # RPFPGA_XDC: exp_p_io[4]
#set_property -dict { PACKAGE_PIN L16   IOSTANDARD LVCMOS33   } [get_ports { exp_p_io[5] }]; # RPFPGA_XDC: exp_p_io[5]
#set_property -dict { PACKAGE_PIN K16   IOSTANDARD LVCMOS33   } [get_ports { exp_p_io[6] }]; # RPFPGA_XDC: exp_p_io[6]
#set_property -dict { PACKAGE_PIN M14   IOSTANDARD LVCMOS33   } [get_ports { exp_p_io[7] }]; # RPFPGA_XDC: exp_p_io[7]

## Extension connector E1, negative lines (DIOn_N)
#set_property -dict { PACKAGE_PIN G18   IOSTANDARD LVCMOS33   } [get_ports { exp_n_io[0] }]; # RPFPGA_XDC: exp_n_io[0]
#set_property -dict { PACKAGE_PIN H17   IOSTANDARD LVCMOS33   } [get_ports { exp_n_io[1] }]; # RPFPGA_XDC: exp_n_io[1]
#set_property -dict { PACKAGE_PIN H18   IOSTANDARD LVCMOS33   } [get_ports { exp_n_io[2] }]; # RPFPGA_XDC: exp_n_io[2]
#set_property -dict { PACKAGE_PIN K18   IOSTANDARD LVCMOS33   } [get_ports { exp_n_io[3] }]; # RPFPGA_XDC: exp_n_io[3]
#set_property -dict { PACKAGE_PIN L15   IOSTANDARD LVCMOS33   } [get_ports { exp_n_io[4] }]; # RPFPGA_XDC: exp_n_io[4]
#set_property -dict { PACKAGE_PIN L17   IOSTANDARD LVCMOS33   } [get_ports { exp_n_io[5] }]; # RPFPGA_XDC: exp_n_io[5]
#set_property -dict { PACKAGE_PIN J16   IOSTANDARD LVCMOS33   } [get_ports { exp_n_io[6] }]; # RPFPGA_XDC: exp_n_io[6]
#set_property -dict { PACKAGE_PIN M15   IOSTANDARD LVCMOS33   } [get_ports { exp_n_io[7] }]; # RPFPGA_XDC: exp_n_io[7]

## Fast ADC data (LTC2145-14), LVCMOS18; adc1_dat is the vendor shell's adc_dat_i[0] (IN1), adc2_dat its adc_dat_i[1] (IN2)
#set_property -dict { PACKAGE_PIN V17   IOSTANDARD LVCMOS18   } [get_ports { adc1_dat[0] }]; # RPFPGA_XDC: adc_dat_i[0][0]
#set_property -dict { PACKAGE_PIN U17   IOSTANDARD LVCMOS18   } [get_ports { adc1_dat[1] }]; # RPFPGA_XDC: adc_dat_i[0][1]
#set_property -dict { PACKAGE_PIN Y17   IOSTANDARD LVCMOS18   } [get_ports { adc1_dat[2] }]; # RPFPGA_XDC: adc_dat_i[0][2]
#set_property -dict { PACKAGE_PIN W16   IOSTANDARD LVCMOS18   } [get_ports { adc1_dat[3] }]; # RPFPGA_XDC: adc_dat_i[0][3]
#set_property -dict { PACKAGE_PIN Y16   IOSTANDARD LVCMOS18   } [get_ports { adc1_dat[4] }]; # RPFPGA_XDC: adc_dat_i[0][4]
#set_property -dict { PACKAGE_PIN W15   IOSTANDARD LVCMOS18   } [get_ports { adc1_dat[5] }]; # RPFPGA_XDC: adc_dat_i[0][5]
#set_property -dict { PACKAGE_PIN W14   IOSTANDARD LVCMOS18   } [get_ports { adc1_dat[6] }]; # RPFPGA_XDC: adc_dat_i[0][6]
#set_property -dict { PACKAGE_PIN Y14   IOSTANDARD LVCMOS18   } [get_ports { adc1_dat[7] }]; # RPFPGA_XDC: adc_dat_i[0][7]
#set_property -dict { PACKAGE_PIN W13   IOSTANDARD LVCMOS18   } [get_ports { adc1_dat[8] }]; # RPFPGA_XDC: adc_dat_i[0][8]
#set_property -dict { PACKAGE_PIN V12   IOSTANDARD LVCMOS18   } [get_ports { adc1_dat[9] }]; # RPFPGA_XDC: adc_dat_i[0][9]
#set_property -dict { PACKAGE_PIN V13   IOSTANDARD LVCMOS18   } [get_ports { adc1_dat[10] }]; # RPFPGA_XDC: adc_dat_i[0][10]
#set_property -dict { PACKAGE_PIN T14   IOSTANDARD LVCMOS18   } [get_ports { adc1_dat[11] }]; # RPFPGA_XDC: adc_dat_i[0][11]
#set_property -dict { PACKAGE_PIN T15   IOSTANDARD LVCMOS18   } [get_ports { adc1_dat[12] }]; # RPFPGA_XDC: adc_dat_i[0][12]
#set_property -dict { PACKAGE_PIN V15   IOSTANDARD LVCMOS18   } [get_ports { adc1_dat[13] }]; # RPFPGA_XDC: adc_dat_i[0][13]
#set_property -dict { PACKAGE_PIN T16   IOSTANDARD LVCMOS18   } [get_ports { adc1_dat[14] }]; # RPFPGA_XDC: adc_dat_i[0][14]
#set_property -dict { PACKAGE_PIN V16   IOSTANDARD LVCMOS18   } [get_ports { adc1_dat[15] }]; # RPFPGA_XDC: adc_dat_i[0][15]
#set_property -dict { PACKAGE_PIN T17   IOSTANDARD LVCMOS18   } [get_ports { adc2_dat[0] }]; # RPFPGA_XDC: adc_dat_i[1][0]
#set_property -dict { PACKAGE_PIN R16   IOSTANDARD LVCMOS18   } [get_ports { adc2_dat[1] }]; # RPFPGA_XDC: adc_dat_i[1][1]
#set_property -dict { PACKAGE_PIN R18   IOSTANDARD LVCMOS18   } [get_ports { adc2_dat[2] }]; # RPFPGA_XDC: adc_dat_i[1][2]
#set_property -dict { PACKAGE_PIN P16   IOSTANDARD LVCMOS18   } [get_ports { adc2_dat[3] }]; # RPFPGA_XDC: adc_dat_i[1][3]
#set_property -dict { PACKAGE_PIN P18   IOSTANDARD LVCMOS18   } [get_ports { adc2_dat[4] }]; # RPFPGA_XDC: adc_dat_i[1][4]
#set_property -dict { PACKAGE_PIN N17   IOSTANDARD LVCMOS18   } [get_ports { adc2_dat[5] }]; # RPFPGA_XDC: adc_dat_i[1][5]
#set_property -dict { PACKAGE_PIN R19   IOSTANDARD LVCMOS18   } [get_ports { adc2_dat[6] }]; # RPFPGA_XDC: adc_dat_i[1][6]
#set_property -dict { PACKAGE_PIN T20   IOSTANDARD LVCMOS18   } [get_ports { adc2_dat[7] }]; # RPFPGA_XDC: adc_dat_i[1][7]
#set_property -dict { PACKAGE_PIN T19   IOSTANDARD LVCMOS18   } [get_ports { adc2_dat[8] }]; # RPFPGA_XDC: adc_dat_i[1][8]
#set_property -dict { PACKAGE_PIN U20   IOSTANDARD LVCMOS18   } [get_ports { adc2_dat[9] }]; # RPFPGA_XDC: adc_dat_i[1][9]
#set_property -dict { PACKAGE_PIN V20   IOSTANDARD LVCMOS18   } [get_ports { adc2_dat[10] }]; # RPFPGA_XDC: adc_dat_i[1][10]
#set_property -dict { PACKAGE_PIN W20   IOSTANDARD LVCMOS18   } [get_ports { adc2_dat[11] }]; # RPFPGA_XDC: adc_dat_i[1][11]
#set_property -dict { PACKAGE_PIN W19   IOSTANDARD LVCMOS18   } [get_ports { adc2_dat[12] }]; # RPFPGA_XDC: adc_dat_i[1][12]
#set_property -dict { PACKAGE_PIN Y19   IOSTANDARD LVCMOS18   } [get_ports { adc2_dat[13] }]; # RPFPGA_XDC: adc_dat_i[1][13]
#set_property -dict { PACKAGE_PIN W18   IOSTANDARD LVCMOS18   } [get_ports { adc2_dat[14] }]; # RPFPGA_XDC: adc_dat_i[1][14]
#set_property -dict { PACKAGE_PIN Y18   IOSTANDARD LVCMOS18   } [get_ports { adc2_dat[15] }]; # RPFPGA_XDC: adc_dat_i[1][15]

## ADC clock duty-cycle stabiliser
#set_property -dict { PACKAGE_PIN V18   IOSTANDARD LVCMOS18   } [get_ports { adc_cdcs_o }]; # RPFPGA_XDC: adc_cdcs_o

## Fast DAC (AD9767), LVCMOS33
#set_property -dict { PACKAGE_PIN M19   IOSTANDARD LVCMOS33   } [get_ports { dac_dat_o[0] }]; # RPFPGA_XDC: dac_dat_o[0]
#set_property -dict { PACKAGE_PIN M20   IOSTANDARD LVCMOS33   } [get_ports { dac_dat_o[1] }]; # RPFPGA_XDC: dac_dat_o[1]
#set_property -dict { PACKAGE_PIN L19   IOSTANDARD LVCMOS33   } [get_ports { dac_dat_o[2] }]; # RPFPGA_XDC: dac_dat_o[2]
#set_property -dict { PACKAGE_PIN L20   IOSTANDARD LVCMOS33   } [get_ports { dac_dat_o[3] }]; # RPFPGA_XDC: dac_dat_o[3]
#set_property -dict { PACKAGE_PIN K19   IOSTANDARD LVCMOS33   } [get_ports { dac_dat_o[4] }]; # RPFPGA_XDC: dac_dat_o[4]
#set_property -dict { PACKAGE_PIN J19   IOSTANDARD LVCMOS33   } [get_ports { dac_dat_o[5] }]; # RPFPGA_XDC: dac_dat_o[5]
#set_property -dict { PACKAGE_PIN J20   IOSTANDARD LVCMOS33   } [get_ports { dac_dat_o[6] }]; # RPFPGA_XDC: dac_dat_o[6]
#set_property -dict { PACKAGE_PIN H20   IOSTANDARD LVCMOS33   } [get_ports { dac_dat_o[7] }]; # RPFPGA_XDC: dac_dat_o[7]
#set_property -dict { PACKAGE_PIN G19   IOSTANDARD LVCMOS33   } [get_ports { dac_dat_o[8] }]; # RPFPGA_XDC: dac_dat_o[8]
#set_property -dict { PACKAGE_PIN G20   IOSTANDARD LVCMOS33   } [get_ports { dac_dat_o[9] }]; # RPFPGA_XDC: dac_dat_o[9]
#set_property -dict { PACKAGE_PIN F19   IOSTANDARD LVCMOS33   } [get_ports { dac_dat_o[10] }]; # RPFPGA_XDC: dac_dat_o[10]
#set_property -dict { PACKAGE_PIN F20   IOSTANDARD LVCMOS33   } [get_ports { dac_dat_o[11] }]; # RPFPGA_XDC: dac_dat_o[11]
#set_property -dict { PACKAGE_PIN D20   IOSTANDARD LVCMOS33   } [get_ports { dac_dat_o[12] }]; # RPFPGA_XDC: dac_dat_o[12]
#set_property -dict { PACKAGE_PIN D19   IOSTANDARD LVCMOS33   } [get_ports { dac_dat_o[13] }]; # RPFPGA_XDC: dac_dat_o[13]
#set_property -dict { PACKAGE_PIN M17   IOSTANDARD LVCMOS33   } [get_ports { dac_wrt_o }]; # RPFPGA_XDC: dac_wrt_o
#set_property -dict { PACKAGE_PIN N16   IOSTANDARD LVCMOS33   } [get_ports { dac_sel_o }]; # RPFPGA_XDC: dac_sel_o
#set_property -dict { PACKAGE_PIN M18   IOSTANDARD LVCMOS33   } [get_ports { dac_clk_o }]; # RPFPGA_XDC: dac_clk_o
#set_property -dict { PACKAGE_PIN N15   IOSTANDARD LVCMOS33   } [get_ports { dac_rst_o }]; # RPFPGA_XDC: dac_rst_o

## XADC inputs (E2 connector slow analogue inputs)
#set_property -dict { PACKAGE_PIN C20   IOSTANDARD LVCMOS33   } [get_ports { vinp_i[1] }]; # RPFPGA_XDC: vinp_i[1]
#set_property -dict { PACKAGE_PIN B20   IOSTANDARD LVCMOS33   } [get_ports { vinn_i[1] }]; # RPFPGA_XDC: vinn_i[1]
#set_property -dict { PACKAGE_PIN E17   IOSTANDARD LVCMOS33   } [get_ports { vinp_i[2] }]; # RPFPGA_XDC: vinp_i[2]
#set_property -dict { PACKAGE_PIN D18   IOSTANDARD LVCMOS33   } [get_ports { vinn_i[2] }]; # RPFPGA_XDC: vinn_i[2]
#set_property -dict { PACKAGE_PIN B19   IOSTANDARD LVCMOS33   } [get_ports { vinp_i[0] }]; # RPFPGA_XDC: vinp_i[0]
#set_property -dict { PACKAGE_PIN A20   IOSTANDARD LVCMOS33   } [get_ports { vinn_i[0] }]; # RPFPGA_XDC: vinn_i[0]
#set_property -dict { PACKAGE_PIN E18   IOSTANDARD LVCMOS33   } [get_ports { vinp_i[3] }]; # RPFPGA_XDC: vinp_i[3]
#set_property -dict { PACKAGE_PIN E19   IOSTANDARD LVCMOS33   } [get_ports { vinn_i[3] }]; # RPFPGA_XDC: vinn_i[3]
#set_property -dict { PACKAGE_PIN K9    IOSTANDARD LVCMOS33   } [get_ports { vinp_i[4] }]; # RPFPGA_XDC: vinp_i[4]
#set_property -dict { PACKAGE_PIN L10   IOSTANDARD LVCMOS33   } [get_ports { vinn_i[4] }]; # RPFPGA_XDC: vinn_i[4]
