// E9: a quasi-static mode bit (set by software on clk_a, rarely changed) reaches clk_b through a 2-flop ASYNC_REG chain.
module tex_e9 (input logic clk_a, input logic clk_b, input logic wr, input logic wdata, input logic [7:0] d_in,
               output logic [7:0] q_out);
    logic mode = 1'b0;
    always_ff @(posedge clk_a) if (wr) mode <= wdata;
    (* ASYNC_REG = "TRUE" *) logic m1 = 1'b0, m2 = 1'b0;
    always_ff @(posedge clk_b) begin
        m1 <= mode;
        m2 <= m1;
        q_out <= m2 ? ~d_in : d_in;
    end
endmodule
