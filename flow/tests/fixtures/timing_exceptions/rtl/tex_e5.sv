// E5: an 8-bit counter on clk_a crosses to the unrelated clk_b through 2-flop ASYNC_REG chains, bit by bit.
module tex_e5 (input logic clk_a, input logic clk_b, input logic inc, output logic [7:0] q_out);
    logic [7:0] cnt = '0;
    always_ff @(posedge clk_a) if (inc) cnt <= cnt + 8'd1;
    (* ASYNC_REG = "TRUE" *) logic [7:0] s1 = '0, s2 = '0;
    always_ff @(posedge clk_b) begin
        s1 <= cnt;
        s2 <= s1;
    end
    assign q_out = s2;
endmodule
