// C7: counter through xpm_cdc_gray.
module cdcfx_c7 (input logic clk_a, input logic clk_b, input logic run, output logic [7:0] val_out);
    logic [7:0] cnt = '0;
    logic [1:0] div = '0;
    always_ff @(posedge clk_a) if (run) begin div <= div + 1'b1; if (div == 2'd3) cnt <= cnt + 1'b1; end
    logic [7:0] v;
    xpm_cdc_gray #(.DEST_SYNC_FF(3), .WIDTH(8), .REG_OUTPUT(1)) u_x (.src_clk(clk_a), .src_in_bin(cnt), .dest_clk(clk_b), .dest_out_bin(v));
    assign val_out = v;
endmodule
