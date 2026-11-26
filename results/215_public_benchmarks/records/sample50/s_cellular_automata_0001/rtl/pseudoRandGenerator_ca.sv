// 16-bit null-boundary cellular automaton PRNG, rules 90/150.
// List order q1..q16 = CA_out[15]..CA_out[0]; R150 cells are CA_out[13,11,9,7,5,3,1].
module pseudoRandGenerator_ca #(
    parameter int CA_WIDTH = 16
) (
    input  logic                  clock,
    input  logic                  reset,
    input  logic [CA_WIDTH-1:0]   CA_seed,
    output logic [CA_WIDTH-1:0]   CA_out
);
    logic [CA_WIDTH+1:0] ext;
    logic [CA_WIDTH-1:0] nxt;

    assign ext = {1'b0, CA_out, 1'b0};

    always_comb begin
        for (int b = 0; b < CA_WIDTH; b++) begin
            nxt[b] = ext[b+2] ^ ext[b];
            if (b % 2 == 1 && b != CA_WIDTH-1) nxt[b] = nxt[b] ^ CA_out[b];
        end
    end

    always_ff @(posedge clock) begin
        if (reset) CA_out <= CA_seed;
        else       CA_out <= nxt;
    end
endmodule
