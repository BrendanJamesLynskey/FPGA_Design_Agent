// P15-4 reference RTL: a copy of solutions/p15l04_pq_adc/pq_adc.sv (course exercise p15l04_pq_adc, M = 8, KB = 4).
// Part 15 lesson 4 exercise: a product-quantisation asymmetric-distance (ADC) unit.
//
// A database vector is stored as M codes of KB bits each (default M = 8 codes of 4 bits, so 16 centres per sub-space), packed codes[j*KB +: KB] = code of sub-space j.
// For one query the host computes a distance table: entry T[j][c] = squared distance between the query's j-th sub-vector and centre c of sub-space j, TW bits unsigned.
// The unit holds the table (M * 2^KB words) and, for each database vector, adds up the M entries its codes pick:
//   distance = sum over j of T[j][codes[j]]                        (DW = TW + $clog2(M) bits: no overflow)
// Table write: with t_we high, T[t_m][t_k] <= t_data at the next clock edge (do not present in_valid for a vector that needs that entry in the same clock).
// Lookups: with in_valid high, one clock later (out_valid high, one clock of latency; rst_n synchronous, active low, clears out_valid only) distance holds the sum.
// The table is memory read asynchronously by the lookups (distributed RAM on an FPGA); lesson 4 says what changes with a block RAM (a registered read).
module pq_adc #(
    parameter int M  = 8,
    parameter int KB = 4,
    parameter int TW = 20,
    parameter int DW = TW + $clog2(M)
) (
    input  logic                    clk,
    input  logic                    rst_n,
    input  logic                    t_we,
    input  logic [$clog2(M)-1:0]    t_m,
    input  logic [KB-1:0]           t_k,
    input  logic [TW-1:0]           t_data,
    input  logic                    in_valid,
    input  logic [M*KB-1:0]         codes,
    output logic                    out_valid,
    output logic [DW-1:0]           distance
);
    logic [TW-1:0] tab [0:M*(1<<KB)-1];
    logic [DW-1:0] sum;
    always_comb begin
        sum = '0;
        for (int j = 0; j < M; j++) sum = sum + tab[(j << KB) + int'(codes[j*KB +: KB])];
    end
    always_ff @(posedge clk) begin
        if (t_we) tab[(int'(t_m) << KB) + int'(t_k)] <= t_data;
        if (!rst_n) out_valid <= 1'b0;
        else out_valid <= in_valid;
        if (in_valid) distance <= sum;
    end
endmodule
