## Analog Devices ADALM-Pluto (Zynq-7010): PL pins of the radio interface (AD9363), listed from a reference design
## Written by tools/board_pins_import.py from boards/adalm_pluto/pins_import.yaml. Pin locations are facts about the board;
## this file is our own listing of them in one format, not a copy of a vendor file. Sources:
##   PLUTO_XDC: https://raw.githubusercontent.com/analogdevicesinc/hdl/9bac1ed939d4511d0a21596d4adcb7b2b2dbeaed/projects/pluto/system_constr.xdc (sha256 f906143497cb...; Analog Devices BSD-style licence whose use clause limits use to Analog Devices components, so the file is not copied; only pin facts are listed); supplies the PL pins of the radio interface, the radio GPIOs and the PL GPIOs
## Every port is commented out in the vendor style: the agent's board_constraints tool writes the lines a design uses.
## Left out because no source gives its I/O standard (a standard is never invented): fixed_io_ps_clk on C7 (PLUTO_XDC); fixed_io_ps_porb on C9 (PLUTO_XDC); fixed_io_ddr_vrp on H3 (PLUTO_XDC); fixed_io_ddr_vrn on J3 (PLUTO_XDC); ddr_ck_p on N3 (PLUTO_XDC); ddr_ck_n on N2 (PLUTO_XDC); ddr_addr[0] on P1 (PLUTO_XDC); ddr_addr[1] on N1 (PLUTO_XDC); ddr_addr[2] on M1 (PLUTO_XDC); ddr_addr[3] on M4 (PLUTO_XDC); ddr_addr[4] on P3 (PLUTO_XDC); ddr_addr[5] on P4 (PLUTO_XDC); ddr_addr[6] on P5 (PLUTO_XDC); ddr_addr[7] on M5 (PLUTO_XDC); ddr_addr[8] on P6 (PLUTO_XDC); ddr_addr[9] on N4 (PLUTO_XDC); ddr_addr[10] on J1 (PLUTO_XDC); ddr_addr[11] on L2 (PLUTO_XDC); ddr_addr[12] on M2 (PLUTO_XDC); ddr_addr[13] on K2 (PLUTO_XDC); ddr_addr[14] on K1 (PLUTO_XDC); ddr_ba[0] on M6 (PLUTO_XDC); ddr_ba[1] on R1 (PLUTO_XDC); ddr_ba[2] on N6 (PLUTO_XDC); ddr_dq[0] on D4 (PLUTO_XDC); ddr_dq[1] on A2 (PLUTO_XDC); ddr_dq[2] on C4 (PLUTO_XDC); ddr_dq[3] on C1 (PLUTO_XDC); ddr_dq[4] on B4 (PLUTO_XDC); ddr_dq[5] on A4 (PLUTO_XDC); ddr_dq[6] on C3 (PLUTO_XDC); ddr_dq[7] on A3 (PLUTO_XDC); ddr_dq[8] on E1 (PLUTO_XDC); ddr_dq[9] on D1 (PLUTO_XDC); ddr_dq[10] on E2 (PLUTO_XDC); ddr_dq[11] on E3 (PLUTO_XDC); ddr_dq[12] on F3 (PLUTO_XDC); ddr_dq[13] on G1 (PLUTO_XDC); ddr_dq[14] on H1 (PLUTO_XDC); ddr_dq[15] on H2 (PLUTO_XDC); ddr_dm[0] on B1 (PLUTO_XDC); ddr_dm[1] on D3 (PLUTO_XDC); ddr_dqs_p[0] on C2 (PLUTO_XDC); ddr_dqs_n[0] on B2 (PLUTO_XDC); ddr_dqs_p[1] on G2 (PLUTO_XDC); ddr_dqs_n[1] on F2 (PLUTO_XDC)

#set_property -dict { PACKAGE_PIN L12   IOSTANDARD LVCMOS18   } [get_ports { rx_clk_in }]; # PLUTO_XDC: rx_clk_in
#set_property -dict { PACKAGE_PIN N13   IOSTANDARD LVCMOS18   } [get_ports { rx_frame_in }]; # PLUTO_XDC: rx_frame_in
#set_property -dict { PACKAGE_PIN H14   IOSTANDARD LVCMOS18   } [get_ports { rx_data_in[0] }]; # PLUTO_XDC: rx_data_in[0]
#set_property -dict { PACKAGE_PIN J13   IOSTANDARD LVCMOS18   } [get_ports { rx_data_in[1] }]; # PLUTO_XDC: rx_data_in[1]
#set_property -dict { PACKAGE_PIN G14   IOSTANDARD LVCMOS18   } [get_ports { rx_data_in[2] }]; # PLUTO_XDC: rx_data_in[2]
#set_property -dict { PACKAGE_PIN H13   IOSTANDARD LVCMOS18   } [get_ports { rx_data_in[3] }]; # PLUTO_XDC: rx_data_in[3]
#set_property -dict { PACKAGE_PIN G12   IOSTANDARD LVCMOS18   } [get_ports { rx_data_in[4] }]; # PLUTO_XDC: rx_data_in[4]
#set_property -dict { PACKAGE_PIN H12   IOSTANDARD LVCMOS18   } [get_ports { rx_data_in[5] }]; # PLUTO_XDC: rx_data_in[5]
#set_property -dict { PACKAGE_PIN G11   IOSTANDARD LVCMOS18   } [get_ports { rx_data_in[6] }]; # PLUTO_XDC: rx_data_in[6]
#set_property -dict { PACKAGE_PIN J14   IOSTANDARD LVCMOS18   } [get_ports { rx_data_in[7] }]; # PLUTO_XDC: rx_data_in[7]
#set_property -dict { PACKAGE_PIN J15   IOSTANDARD LVCMOS18   } [get_ports { rx_data_in[8] }]; # PLUTO_XDC: rx_data_in[8]
#set_property -dict { PACKAGE_PIN K15   IOSTANDARD LVCMOS18   } [get_ports { rx_data_in[9] }]; # PLUTO_XDC: rx_data_in[9]
#set_property -dict { PACKAGE_PIN H11   IOSTANDARD LVCMOS18   } [get_ports { rx_data_in[10] }]; # PLUTO_XDC: rx_data_in[10]
#set_property -dict { PACKAGE_PIN J11   IOSTANDARD LVCMOS18   } [get_ports { rx_data_in[11] }]; # PLUTO_XDC: rx_data_in[11]
#set_property -dict { PACKAGE_PIN P10   IOSTANDARD LVCMOS18   } [get_ports { tx_clk_out }]; # PLUTO_XDC: tx_clk_out
#set_property -dict { PACKAGE_PIN L14   IOSTANDARD LVCMOS18   } [get_ports { tx_frame_out }]; # PLUTO_XDC: tx_frame_out
#set_property -dict { PACKAGE_PIN P15   IOSTANDARD LVCMOS18   } [get_ports { tx_data_out[0] }]; # PLUTO_XDC: tx_data_out[0]
#set_property -dict { PACKAGE_PIN R13   IOSTANDARD LVCMOS18   } [get_ports { tx_data_out[1] }]; # PLUTO_XDC: tx_data_out[1]
#set_property -dict { PACKAGE_PIN R15   IOSTANDARD LVCMOS18   } [get_ports { tx_data_out[2] }]; # PLUTO_XDC: tx_data_out[2]
#set_property -dict { PACKAGE_PIN P11   IOSTANDARD LVCMOS18   } [get_ports { tx_data_out[3] }]; # PLUTO_XDC: tx_data_out[3]
#set_property -dict { PACKAGE_PIN R11   IOSTANDARD LVCMOS18   } [get_ports { tx_data_out[4] }]; # PLUTO_XDC: tx_data_out[4]
#set_property -dict { PACKAGE_PIN R12   IOSTANDARD LVCMOS18   } [get_ports { tx_data_out[5] }]; # PLUTO_XDC: tx_data_out[5]
#set_property -dict { PACKAGE_PIN P14   IOSTANDARD LVCMOS18   } [get_ports { tx_data_out[6] }]; # PLUTO_XDC: tx_data_out[6]
#set_property -dict { PACKAGE_PIN P13   IOSTANDARD LVCMOS18   } [get_ports { tx_data_out[7] }]; # PLUTO_XDC: tx_data_out[7]
#set_property -dict { PACKAGE_PIN N9    IOSTANDARD LVCMOS18   } [get_ports { tx_data_out[8] }]; # PLUTO_XDC: tx_data_out[8]
#set_property -dict { PACKAGE_PIN M9    IOSTANDARD LVCMOS18   } [get_ports { tx_data_out[9] }]; # PLUTO_XDC: tx_data_out[9]
#set_property -dict { PACKAGE_PIN R8    IOSTANDARD LVCMOS18   } [get_ports { tx_data_out[10] }]; # PLUTO_XDC: tx_data_out[10]
#set_property -dict { PACKAGE_PIN R7    IOSTANDARD LVCMOS18   } [get_ports { tx_data_out[11] }]; # PLUTO_XDC: tx_data_out[11]
#set_property -dict { PACKAGE_PIN L15   IOSTANDARD LVCMOS18   } [get_ports { gpio_status[0] }]; # PLUTO_XDC: gpio_status[0]
#set_property -dict { PACKAGE_PIN M15   IOSTANDARD LVCMOS18   } [get_ports { gpio_status[1] }]; # PLUTO_XDC: gpio_status[1]
#set_property -dict { PACKAGE_PIN N11   IOSTANDARD LVCMOS18   } [get_ports { gpio_status[2] }]; # PLUTO_XDC: gpio_status[2]
#set_property -dict { PACKAGE_PIN N12   IOSTANDARD LVCMOS18   } [get_ports { gpio_status[3] }]; # PLUTO_XDC: gpio_status[3]
#set_property -dict { PACKAGE_PIN M10   IOSTANDARD LVCMOS18   } [get_ports { gpio_status[4] }]; # PLUTO_XDC: gpio_status[4]
#set_property -dict { PACKAGE_PIN M11   IOSTANDARD LVCMOS18   } [get_ports { gpio_status[5] }]; # PLUTO_XDC: gpio_status[5]
#set_property -dict { PACKAGE_PIN N7    IOSTANDARD LVCMOS18   } [get_ports { gpio_status[6] }]; # PLUTO_XDC: gpio_status[6]
#set_property -dict { PACKAGE_PIN N8    IOSTANDARD LVCMOS18   } [get_ports { gpio_status[7] }]; # PLUTO_XDC: gpio_status[7]
#set_property -dict { PACKAGE_PIN F13   IOSTANDARD LVCMOS18   } [get_ports { gpio_ctl[0] }]; # PLUTO_XDC: gpio_ctl[0]
#set_property -dict { PACKAGE_PIN F14   IOSTANDARD LVCMOS18   } [get_ports { gpio_ctl[1] }]; # PLUTO_XDC: gpio_ctl[1]
#set_property -dict { PACKAGE_PIN G15   IOSTANDARD LVCMOS18   } [get_ports { gpio_ctl[2] }]; # PLUTO_XDC: gpio_ctl[2]
#set_property -dict { PACKAGE_PIN F15   IOSTANDARD LVCMOS18   } [get_ports { gpio_ctl[3] }]; # PLUTO_XDC: gpio_ctl[3]
#set_property -dict { PACKAGE_PIN L13   IOSTANDARD LVCMOS18   } [get_ports { gpio_en_agc }]; # PLUTO_XDC: gpio_en_agc
#set_property -dict { PACKAGE_PIN P9    IOSTANDARD LVCMOS18   } [get_ports { gpio_resetb }]; # PLUTO_XDC: gpio_resetb
#set_property -dict { PACKAGE_PIN K12   IOSTANDARD LVCMOS18   } [get_ports { enable }]; # PLUTO_XDC: enable
#set_property -dict { PACKAGE_PIN K11   IOSTANDARD LVCMOS18   } [get_ports { txnrx }]; # PLUTO_XDC: txnrx
#set_property -dict { PACKAGE_PIN E12   IOSTANDARD LVCMOS18   } [get_ports { spi_csn }]; # PLUTO_XDC: spi_csn
#set_property -dict { PACKAGE_PIN E11   IOSTANDARD LVCMOS18   } [get_ports { spi_clk }]; # PLUTO_XDC: spi_clk
#set_property -dict { PACKAGE_PIN E13   IOSTANDARD LVCMOS18   } [get_ports { spi_mosi }]; # PLUTO_XDC: spi_mosi
#set_property -dict { PACKAGE_PIN F12   IOSTANDARD LVCMOS18   } [get_ports { spi_miso }]; # PLUTO_XDC: spi_miso
#set_property -dict { PACKAGE_PIN K13   IOSTANDARD LVCMOS18   } [get_ports { pl_gpio0 }]; # PLUTO_XDC: pl_gpio0
#set_property -dict { PACKAGE_PIN M12   IOSTANDARD LVCMOS18   } [get_ports { pl_gpio1 }]; # PLUTO_XDC: pl_gpio1
#set_property -dict { PACKAGE_PIN R10   IOSTANDARD LVCMOS18   } [get_ports { pl_gpio2 }]; # PLUTO_XDC: pl_gpio2
#set_property -dict { PACKAGE_PIN N14   IOSTANDARD LVCMOS18   } [get_ports { pl_gpio3 }]; # PLUTO_XDC: pl_gpio3
#set_property -dict { PACKAGE_PIN M14   IOSTANDARD LVCMOS18   } [get_ports { pl_gpio4 }]; # PLUTO_XDC: pl_gpio4
#set_property -dict { PACKAGE_PIN P8    IOSTANDARD LVCMOS18   } [get_ports { clk_out }]; # PLUTO_XDC: clk_out
#set_property -dict { PACKAGE_PIN L4    IOSTANDARD SSTL15     } [get_ports { ddr_reset_n }]; # PLUTO_XDC: ddr_reset_n
#set_property -dict { PACKAGE_PIN R2    IOSTANDARD SSTL15     } [get_ports { ddr_cs_n }]; # PLUTO_XDC: ddr_cs_n
#set_property -dict { PACKAGE_PIN R6    IOSTANDARD SSTL15     } [get_ports { ddr_ras_n }]; # PLUTO_XDC: ddr_ras_n
#set_property -dict { PACKAGE_PIN R5    IOSTANDARD SSTL15     } [get_ports { ddr_cas_n }]; # PLUTO_XDC: ddr_cas_n
#set_property -dict { PACKAGE_PIN R3    IOSTANDARD SSTL15     } [get_ports { ddr_we_n }]; # PLUTO_XDC: ddr_we_n
#set_property -dict { PACKAGE_PIN L3    IOSTANDARD SSTL15     } [get_ports { ddr_cke }]; # PLUTO_XDC: ddr_cke
#set_property -dict { PACKAGE_PIN K3    IOSTANDARD SSTL15     } [get_ports { ddr_odt }]; # PLUTO_XDC: ddr_odt
