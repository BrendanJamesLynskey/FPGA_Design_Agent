// fir_diff_tb: the differential bench for ip_lib/fir. One instance of every variant, each with its own
// handshakes; ip_lib/fir/tb/cocotb_fir.py fir_diff feeds them the same coefficients and samples and compares the outputs.
module fir_diff_tb #(
    parameter int TAPS = 16, parameter int DATA_W = 16, parameter int COEF_W = 16, parameter int FOLD = 4,
    localparam int ACC_W = DATA_W + COEF_W + $clog2(TAPS)
) (
    input logic clk, input logic rst
    , output logic dsp_bram_busy, input logic dsp_bram_c_valid, output logic dsp_bram_c_ready, input logic signed [COEF_W-1:0] dsp_bram_c_data, input logic dsp_bram_c_last
    , input logic dsp_bram_s_valid, output logic dsp_bram_s_ready, input logic signed [DATA_W-1:0] dsp_bram_s_data
    , output logic dsp_bram_m_valid, input logic dsp_bram_m_ready, output logic signed [ACC_W-1:0] dsp_bram_m_data
    , output logic dist_ram_busy, input logic dist_ram_c_valid, output logic dist_ram_c_ready, input logic signed [COEF_W-1:0] dist_ram_c_data, input logic dist_ram_c_last
    , input logic dist_ram_s_valid, output logic dist_ram_s_ready, input logic signed [DATA_W-1:0] dist_ram_s_data
    , output logic dist_ram_m_valid, input logic dist_ram_m_ready, output logic signed [ACC_W-1:0] dist_ram_m_data
    , output logic serial_busy, input logic serial_c_valid, output logic serial_c_ready, input logic signed [COEF_W-1:0] serial_c_data, input logic serial_c_last
    , input logic serial_s_valid, output logic serial_s_ready, input logic signed [DATA_W-1:0] serial_s_data
    , output logic serial_m_valid, input logic serial_m_ready, output logic signed [ACC_W-1:0] serial_m_data
    , output logic lut_mult_busy, input logic lut_mult_c_valid, output logic lut_mult_c_ready, input logic signed [COEF_W-1:0] lut_mult_c_data, input logic lut_mult_c_last
    , input logic lut_mult_s_valid, output logic lut_mult_s_ready, input logic signed [DATA_W-1:0] lut_mult_s_data
    , output logic lut_mult_m_valid, input logic lut_mult_m_ready, output logic signed [ACC_W-1:0] lut_mult_m_data
);
    fir #(.IMPL("dsp_bram"), .TAPS(TAPS), .DATA_W(DATA_W), .COEF_W(COEF_W), .FOLD(FOLD)) u_dsp_bram (
        .clk, .rst, .busy(dsp_bram_busy), .c_valid(dsp_bram_c_valid), .c_ready(dsp_bram_c_ready), .c_data(dsp_bram_c_data), .c_last(dsp_bram_c_last),
        .s_valid(dsp_bram_s_valid), .s_ready(dsp_bram_s_ready), .s_data(dsp_bram_s_data), .m_valid(dsp_bram_m_valid), .m_ready(dsp_bram_m_ready), .m_data(dsp_bram_m_data));
    fir #(.IMPL("dist_ram"), .TAPS(TAPS), .DATA_W(DATA_W), .COEF_W(COEF_W), .FOLD(FOLD)) u_dist_ram (
        .clk, .rst, .busy(dist_ram_busy), .c_valid(dist_ram_c_valid), .c_ready(dist_ram_c_ready), .c_data(dist_ram_c_data), .c_last(dist_ram_c_last),
        .s_valid(dist_ram_s_valid), .s_ready(dist_ram_s_ready), .s_data(dist_ram_s_data), .m_valid(dist_ram_m_valid), .m_ready(dist_ram_m_ready), .m_data(dist_ram_m_data));
    fir #(.IMPL("serial"), .TAPS(TAPS), .DATA_W(DATA_W), .COEF_W(COEF_W), .FOLD(FOLD)) u_serial (
        .clk, .rst, .busy(serial_busy), .c_valid(serial_c_valid), .c_ready(serial_c_ready), .c_data(serial_c_data), .c_last(serial_c_last),
        .s_valid(serial_s_valid), .s_ready(serial_s_ready), .s_data(serial_s_data), .m_valid(serial_m_valid), .m_ready(serial_m_ready), .m_data(serial_m_data));
    fir #(.IMPL("lut_mult"), .TAPS(TAPS), .DATA_W(DATA_W), .COEF_W(COEF_W), .FOLD(FOLD)) u_lut_mult (
        .clk, .rst, .busy(lut_mult_busy), .c_valid(lut_mult_c_valid), .c_ready(lut_mult_c_ready), .c_data(lut_mult_c_data), .c_last(lut_mult_c_last),
        .s_valid(lut_mult_s_valid), .s_ready(lut_mult_s_ready), .s_data(lut_mult_s_data), .m_valid(lut_mult_m_valid), .m_ready(lut_mult_m_ready), .m_data(lut_mult_m_data));
endmodule
