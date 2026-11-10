// M7: reconvergence. Two flags set on one source edge are synchronised separately and then compared.
module cdcfx_m7 (input logic clk_a, input logic clk_b, input logic ev_in, output logic ev_out, output logic err_out);
    logic f0 = 1'b0, f1 = 1'b0;
    always_ff @(posedge clk_a) if (ev_in) begin f0 <= ~f0; f1 <= ~f1; end
    (* ASYNC_REG = "TRUE" *) logic [1:0] sa = 2'b00;
    (* ASYNC_REG = "TRUE" *) logic [1:0] sb = 2'b00;
    always_ff @(posedge clk_b) begin sa <= {sa[0], f0}; sb <= {sb[0], f1}; end
    logic prev = 1'b0;
    always_ff @(posedge clk_b) begin prev <= sa[1]; ev_out <= sa[1] ^ prev; err_out <= sa[1] != sb[1]; end
endmodule
