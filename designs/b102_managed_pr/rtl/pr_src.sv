// pr_src.sv: the stimulus of the managed-project placement demonstration: a 16-bit maximal-length LFSR whose output bit feeds the
// placed-and-routed block's serial input. Owned by the project (the agent may edit it, inside its request's scope).
module pr_src (
    input  logic clk,
    input  logic rst,
    output logic bit_o
);
    logic [15:0] lfsr;
    always_ff @(posedge clk) begin
        if (rst) lfsr <= 16'hACE1;
        else     lfsr <= {lfsr[14:0], lfsr[15] ^ lfsr[13] ^ lfsr[12] ^ lfsr[10]};
    end
    assign bit_o = lfsr[15];
endmodule
