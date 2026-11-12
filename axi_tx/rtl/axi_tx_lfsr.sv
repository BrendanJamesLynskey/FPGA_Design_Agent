// axi_tx_lfsr: 32-bit Galois LFSR (right shift, feedback mask 0x80200003: x^32 + x^22 + x^2 + x + 1), the transactor's
// seeded source of random fields and throttle decisions. A zero seed loads 1 (the all-zero state never leaves itself).
// Python twin: axi_tx/host/model.py lfsr_next(); the two must stay identical (tests/test_59a_model.py checks a sequence).
module axi_tx_lfsr (
    input  logic        clk,
    input  logic        load,      // state <= seed (or 1 if the seed is 0)
    input  logic [31:0] seed,
    input  logic        step,      // advance one state
    output logic [31:0] state
);
    initial state = 32'h1;
    always_ff @(posedge clk) begin
        if (load)      state <= (seed == 32'h0) ? 32'h1 : seed;
        else if (step) state <= (state >> 1) ^ (state[0] ? 32'h8020_0003 : 32'h0);
    end
endmodule
