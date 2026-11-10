// M6a: the same RTL as C6 with no max-delay or bus-skew exception on the Gray bus (see the xdc): the bits may arrive skewed.
module cdcfx_m6a (input logic clk_a, input logic clk_b, input logic run, output logic [7:0] val_out);
    logic [7:0] cnt = '0;
    logic [1:0] div = '0;
    always_ff @(posedge clk_a) if (run) begin div <= div + 1'b1; if (div == 2'd3) cnt <= cnt + 1'b1; end
    logic [7:0] g = '0;
    always_ff @(posedge clk_a) g <= cnt ^ (cnt >> 1);
    (* ASYNC_REG = "TRUE" *) logic [7:0] s1 = '0;
    (* ASYNC_REG = "TRUE" *) logic [7:0] s2 = '0;
    always_ff @(posedge clk_b) begin s1 <= g; s2 <= s1; end
    logic [7:0] b;
    always_comb for (int i = 0; i < 8; i++) b[i] = ^(s2 >> i);
    always_ff @(posedge clk_b) val_out <= b;
endmodule
