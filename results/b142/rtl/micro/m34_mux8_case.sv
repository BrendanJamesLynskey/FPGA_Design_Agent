// m34_mux8_case: an 8-to-1, 16-bit multiplexer written as a case statement ($pmux).
module m34_mux8_case (input logic clk, input logic [15:0] d0, d1, d2, d3, d4, d5, d6, d7, input logic [2:0] s, output logic [15:0] y);
    logic [15:0] q0, q1, q2, q3, q4, q5, q6, q7; logic [2:0] sq;
    always_ff @(posedge clk) begin
        q0 <= d0; q1 <= d1; q2 <= d2; q3 <= d3; q4 <= d4; q5 <= d5; q6 <= d6; q7 <= d7; sq <= s;
        case (sq)
            3'd0: y <= q0; 3'd1: y <= q1; 3'd2: y <= q2; 3'd3: y <= q3;
            3'd4: y <= q4; 3'd5: y <= q5; 3'd6: y <= q6; default: y <= q7;
        endcase
    end
endmodule
