// A fixed-latency pipeline for brief 189 item 7: out_valid follows in_valid by exactly DEPTH clocks (the true latency, from the
// clock edge that samples in_valid to the clock edge at which out_valid is first seen high).
module lat_pipe #(parameter int DEPTH = 3) (input logic clk, input logic in_valid, output logic out_valid);
    logic [DEPTH-1:0] sr = '0;
    always_ff @(posedge clk) sr <= {sr[DEPTH-2:0], in_valid};
    assign out_valid = sr[DEPTH-1];
endmodule
