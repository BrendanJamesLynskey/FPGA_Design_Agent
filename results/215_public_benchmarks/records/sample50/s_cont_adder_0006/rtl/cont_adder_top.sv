/* verilator lint_off DECLFILENAME */
module continuous_adder #(
    parameter int DATA_WIDTH      = 32,
    parameter int THRESHOLD_VALUE = 100,
    parameter int SIGNED_INPUTS   = 1
) (
    input  logic                  clk,
    input  logic                  reset,      // active high, synchronous
    input  logic [DATA_WIDTH-1:0] data_in,
    input  logic                  data_valid,
    output logic [DATA_WIDTH-1:0] sum_out,
    output logic                  sum_ready
);

    logic [DATA_WIDTH-1:0] sum_accum;
    logic [DATA_WIDTH-1:0] next;
    logic                  hit;

    localparam logic [DATA_WIDTH-1:0] THR  = DATA_WIDTH'(THRESHOLD_VALUE);
    localparam logic [DATA_WIDTH-1:0] NTHR = -THR;

    assign next = sum_accum + data_in;

    always_comb begin
        if (SIGNED_INPUTS != 0)
            hit = ($signed(next) >= $signed(THR)) || ($signed(next) <= $signed(NTHR));
        else
            hit = (next >= THR);
    end

    // Power-up values (spec: sum_out is not cleared by reset)
    initial begin
        sum_accum = '0;
        sum_out   = '0;
        sum_ready = 1'b0;
    end

    always_ff @(posedge clk) begin
        if (reset) begin
            sum_accum <= '0;
            sum_ready <= 1'b0;
        end else if (data_valid) begin
            if (hit) begin
                sum_out   <= next;
                sum_ready <= 1'b1;
                sum_accum <= '0;
            end else begin
                sum_accum <= next;
                sum_ready <= 1'b0;
            end
        end
    end

endmodule
