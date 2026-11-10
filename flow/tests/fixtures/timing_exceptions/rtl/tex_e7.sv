// E7: a 4-bit Gray pointer on clk_a crosses to the unrelated clk_b through a 2-flop ASYNC_REG chain.
module tex_e7 (input logic clk_a, input logic clk_b, input logic inc, output logic [3:0] q_out);
    logic [3:0] bin = '0, gray = '0;
    always_ff @(posedge clk_a) if (inc) begin
        bin <= bin + 4'd1;
        gray <= (bin + 4'd1) ^ ((bin + 4'd1) >> 1);
    end
    (* ASYNC_REG = "TRUE" *) logic [3:0] s1 = '0, s2 = '0;
    always_ff @(posedge clk_b) begin
        s1 <= gray;
        s2 <= s1;
    end
    assign q_out = s2;
endmodule
