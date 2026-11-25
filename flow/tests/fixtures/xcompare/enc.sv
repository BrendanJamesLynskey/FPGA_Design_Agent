// A seeded defect for brief 189 item 11: a parity encoder whose output is X for the input 8'hFF (a case the author wrote as a
// don't-care, so simulation gives X there). Every other input is correct.
module enc (input logic clk, input logic [7:0] d, output logic p);
    always_ff @(posedge clk) p <= (d == 8'hFF) ? 1'bx : ^d;
endmodule
