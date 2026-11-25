module pseudoRandGenerator_ca (
    input  logic        clock,    // Clock input
    input  logic        reset,    // Active-high synchronous reset
    input  logic [15:0] CA_seed,  // 16-bit cellular automaton seed
    output logic [15:0] CA_out    // 16-bit cellular automaton state
);

    logic [15:0] nxt;

    // Bit 15 = q1 ... bit 0 = q16; boundaries are 0.
    assign nxt[15] = CA_out[14];
    assign nxt[14] = CA_out[15] ^ CA_out[13];
    assign nxt[13] = CA_out[14] ^ CA_out[13] ^ CA_out[12];
    assign nxt[12] = CA_out[13] ^ CA_out[11];
    assign nxt[11] = CA_out[12] ^ CA_out[11] ^ CA_out[10];
    assign nxt[10] = CA_out[11] ^ CA_out[9];
    assign nxt[9]  = CA_out[10] ^ CA_out[9] ^ CA_out[8];
    assign nxt[8]  = CA_out[9] ^ CA_out[7];
    assign nxt[7]  = CA_out[8] ^ CA_out[7] ^ CA_out[6];
    assign nxt[6]  = CA_out[7] ^ CA_out[5];
    assign nxt[5]  = CA_out[6] ^ CA_out[5] ^ CA_out[4];
    assign nxt[4]  = CA_out[5] ^ CA_out[3];
    assign nxt[3]  = CA_out[4] ^ CA_out[3] ^ CA_out[2];
    assign nxt[2]  = CA_out[3] ^ CA_out[1];
    assign nxt[1]  = CA_out[2] ^ CA_out[1] ^ CA_out[0];
    assign nxt[0]  = CA_out[1];

    always_ff @(posedge clock) begin
        if (reset) CA_out <= CA_seed;
        else       CA_out <= nxt;
    end

endmodule
