// Brief 206: our own behavioural stand-ins for the encrypted inner modules of two Quartus atom models, so Icarus can
// run the post-fit netlists (owner rule 2026-11-13: own models where the vendor model is limited). Envelope: buffers and
// clock enables only, always enabled, no timing; written from the port lists of the wrappers in Quartus 25.1std
// eda/sim_lib (not from the encrypted code). Register behaviour (dffeas, power_up) is the vendor's own model, unchanged.
module fiftyfivenm_io_obuf_encrypted (input i, input oe, input [15:0] seriesterminationcontrol, input devoe, output o, output obar);
  parameter open_drain_output = "false";
  parameter bus_hold = "false";
  parameter lpm_type = "fiftyfivenm_io_obuf";
  assign o = oe ? i : 1'bz;
  assign obar = ~o;
endmodule
module cyclonev_clkena_encrypted (input inclk, input ena, output enaout, output outclk);
  parameter clock_type = "auto";
  parameter ena_register_mode = "always enabled";
  parameter lpm_type = "cyclonev_clkena";
  parameter ena_register_power_up = "high";
  parameter disable_mode = "low";
  parameter test_syn = "high";
  assign enaout = ena;
  assign outclk = inclk & ena;
endmodule
module fiftyfivenm_io_ibuf_encrypted (input i, input ibar, input nsleep, output o);
  parameter bus_hold = "false";
  parameter simulate_z_as = "Z";
  parameter listen_to_nsleep_signal = "false";
  parameter differential_mode = "false";
  parameter lpm_type = "fiftyfivenm_io_ibuf";
  assign o = i;
endmodule
// MAX 10 hard blocks Quartus adds to every netlist (user flash, ADC): unconnected in our arms, so the stand-ins drive
// nothing. Port and parameter names copied from the wrappers' instantiations of their encrypted inner modules.
module fiftyfivenm_unvm_encrypted (arclk, arshft, drclk, drshft, drdin, nprogram, nerase, nosc_ena, par_en, xe_ye, se, ardin, busy, osc, bgpbusy, se_pass, sp_pass, drdout);
  parameter addr_range1_end_addr = 0;
  parameter addr_range1_offset = 0;
  parameter addr_range2_end_addr = 0;
  parameter addr_range2_offset = 0;
  parameter addr_range3_offset = 0;
  parameter device_id = 0;
  parameter identifier = 0;
  parameter init_filename = 0;
  parameter init_filename_sim = 0;
  parameter is_compressed_image = 0;
  parameter is_dual_boot = 0;
  parameter is_eram_skip = 0;
  parameter max_ufm_valid_addr = 0;
  parameter max_valid_addr = 0;
  parameter min_ufm_valid_addr = 0;
  parameter min_valid_addr = 0;
  parameter part_name = 0;
  parameter reserve_block = 0;
 input arclk;
 input arshft;
 input drclk;
 input drshft;
 input drdin;
 input nprogram;
 input nerase;
 input nosc_ena;
 input par_en;
 input xe_ye;
 input se;
 input [22:0] ardin;
 output busy;
 output osc;
 output bgpbusy;
 output se_pass;
 output sp_pass;
 output [31:0] drdout;
endmodule
module fiftyfivenm_adcblock_encrypted (clkin_from_pll_c0, usr_pwd, tsen, chsel, soc, eoc, dout, clk_dft);
  parameter analog_input_pin_mask = 0;
  parameter clkdiv = 0;
  parameter device_partname_fivechar_prefix = 0;
  parameter enable_usr_sim = 0;
  parameter is_this_first_or_second_adc = 0;
  parameter prescalar = 0;
  parameter pwd = 0;
  parameter reference_voltage_sim = 0;
  parameter refsel = 0;
  parameter reserve_block = 0;
  parameter simfilename_ch0 = 0;
  parameter simfilename_ch1 = 0;
  parameter simfilename_ch10 = 0;
  parameter simfilename_ch11 = 0;
  parameter simfilename_ch12 = 0;
  parameter simfilename_ch13 = 0;
  parameter simfilename_ch14 = 0;
  parameter simfilename_ch15 = 0;
  parameter simfilename_ch16 = 0;
  parameter simfilename_ch2 = 0;
  parameter simfilename_ch3 = 0;
  parameter simfilename_ch4 = 0;
  parameter simfilename_ch5 = 0;
  parameter simfilename_ch6 = 0;
  parameter simfilename_ch7 = 0;
  parameter simfilename_ch8 = 0;
  parameter simfilename_ch9 = 0;
  parameter testbits = 0;
  parameter tsclkdiv = 0;
  parameter tsclksel = 0;
 input clkin_from_pll_c0;
 input usr_pwd;
 input tsen;
 input [4:0] chsel;
 input soc;
 output eoc;
 output [11:0] dout;
 output clk_dft;
endmodule
