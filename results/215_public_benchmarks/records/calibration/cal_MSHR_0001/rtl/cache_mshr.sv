/* verilator lint_off DECLFILENAME */
// Lowest-index set bit finder: cnt = index of lowest 1 in in_bits, found = any bit set.
module leading_zero_cnt #(
    parameter int WIDTH = 32,
    parameter int CNT_WIDTH = 5
) (
    input  logic [WIDTH-1:0]     in_bits,
    output logic [CNT_WIDTH-1:0] cnt,
    output logic                 found
);
    always_comb begin
        cnt   = '0;
        found = 1'b0;
        for (int i = WIDTH - 1; i >= 0; i--) begin
            if (in_bits[i]) begin
                cnt   = CNT_WIDTH'(i);
                found = 1'b1;
            end
        end
    end
endmodule

/* verilator lint_off UNUSEDPARAM */
module cache_mshr #(
    parameter string INSTANCE_ID        = "mo_mshr",
    parameter int MSHR_SIZE             = 32,
    parameter int CS_LINE_ADDR_WIDTH    = 10,
    parameter int WORD_SEL_WIDTH        = 4,
    parameter int WORD_SIZE             = 4,
    parameter int MSHR_ADDR_WIDTH       = 5,
    parameter int TAG_WIDTH             = 16,
    parameter int CS_WORD_WIDTH         = 32,
    parameter int DATA_WIDTH            = 56
) (
    input  logic                            clk,
    input  logic                            reset,
    input  logic                            allocate_valid,
    output logic                            allocate_ready,
    input  logic [CS_LINE_ADDR_WIDTH-1:0]   allocate_addr,
    input  logic                            allocate_rw,
    input  logic [DATA_WIDTH-1:0]           allocate_data,
    output logic [MSHR_ADDR_WIDTH-1:0]      allocate_id,
    output logic                            allocate_pending,
    output logic [MSHR_ADDR_WIDTH-1:0]      allocate_previd,
    input  logic                            finalize_valid,
    input  logic [MSHR_ADDR_WIDTH-1:0]      finalize_id
);
    logic [MSHR_SIZE-1:0]            valid_q;
    logic [MSHR_SIZE-1:0]            next_q;
    logic [CS_LINE_ADDR_WIDTH-1:0]   addr_q [MSHR_SIZE];
    /* verilator lint_off UNUSEDSIGNAL */
    logic                            rw_q   [MSHR_SIZE];
    logic [MSHR_ADDR_WIDTH-1:0]      nidx_q [MSHR_SIZE];
    logic [DATA_WIDTH-1:0]           data_ram [MSHR_SIZE];
    /* verilator lint_on UNUSEDSIGNAL */

    logic [MSHR_SIZE-1:0] match;
    logic                 free_found;

    always_comb begin
        for (int i = 0; i < MSHR_SIZE; i++)
            match[i] = valid_q[i] & ~next_q[i] & (addr_q[i] == allocate_addr);
    end

    leading_zero_cnt #(.WIDTH(MSHR_SIZE), .CNT_WIDTH(MSHR_ADDR_WIDTH)) u_free (
        .in_bits(~valid_q), .cnt(allocate_id), .found(free_found));

    leading_zero_cnt #(.WIDTH(MSHR_SIZE), .CNT_WIDTH(MSHR_ADDR_WIDTH)) u_match (
        .in_bits(match), .cnt(allocate_previd), .found(allocate_pending));

    assign allocate_ready = free_found;

    wire do_alloc = allocate_valid & free_found;

    // control state: valid bits (reset)
    always_ff @(posedge clk) begin
        if (reset) begin
            valid_q <= '0;
        end else begin
            if (finalize_valid && int'(finalize_id) < MSHR_SIZE)
                valid_q[finalize_id] <= 1'b0;
            if (do_alloc)
                valid_q[allocate_id] <= 1'b1;
        end
    end

    // next flags and entry data: no reset needed (qualified by valid)
    always_ff @(posedge clk) begin
        if (do_alloc) begin
            if (allocate_pending) begin
                next_q[allocate_previd] <= 1'b1;
                nidx_q[allocate_previd] <= allocate_id;
            end
            next_q[allocate_id] <= 1'b0;
            addr_q[allocate_id] <= allocate_addr;
            rw_q[allocate_id]   <= allocate_rw;
            data_ram[allocate_id] <= allocate_data;
        end
    end
endmodule
