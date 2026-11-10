// M3: a binary counter crossed bit by bit through a 2-stage ASYNC_REG chain.
module cdcfx_m3 (input logic clk_a, input logic clk_b, input logic run, output logic [7:0] val_out);
    logic [7:0] cnt = '0;
    logic [1:0] div = '0;
    always_ff @(posedge clk_a) if (run) begin div <= div + 1'b1; if (div == 2'd3) cnt <= cnt + 1'b1; end
    (* ASYNC_REG = "TRUE" *) logic [7:0] s1 = '0;
    (* ASYNC_REG = "TRUE" *) logic [7:0] s2 = '0;
    always_ff @(posedge clk_b) begin s1 <= cnt; s2 <= s1; end
    always_ff @(posedge clk_b) val_out <= s2;
endmodule
