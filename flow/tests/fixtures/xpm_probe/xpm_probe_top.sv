// Probe for the XPM scoped-constraint check (QR1): two clocks, one xpm_cdc_single, one xpm_cdc_gray.
module xpm_probe_top (
    input  logic clk_a, clk_b, d_in, input logic [3:0] bin_in,
    output logic q_single, output logic [3:0] q_gray
);
    logic a_bit; logic [3:0] a_cnt; logic [3:0] g_dest;
    always_ff @(posedge clk_a) begin a_bit <= d_in; a_cnt <= a_cnt + bin_in; end
    logic s_dest;
    xpm_cdc_single #(.DEST_SYNC_FF(2), .SRC_INPUT_REG(1)) u_single (
        .src_clk(clk_a), .src_in(a_bit), .dest_clk(clk_b), .dest_out(s_dest));
    xpm_cdc_gray #(.DEST_SYNC_FF(2), .WIDTH(4)) u_gray (
        .src_clk(clk_a), .src_in_bin(a_cnt), .dest_clk(clk_b), .dest_out_bin(g_dest));
    always_ff @(posedge clk_b) begin q_single <= s_dest; q_gray <= g_dest; end
endmodule
