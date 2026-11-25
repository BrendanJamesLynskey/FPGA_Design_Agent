// fxp_round_inc: round and saturate in one clock by shifting first and incrementing after (brief 139b). Latency 1.
// floor = x >>> S; inc = 0 (truncate), x[S-1] (half up), x[S-1] & (|x[S-2:0] | x[S]) (convergent); result = floor + inc.
// Primitive use (intended, not yet measured): an incrementer of W_IN - S + 1 bits (ceil((W_IN-S+1)/4) CARRY4, a shorter chain than
// fxp_round_fold's when S is large) preceded by the increment decision, a LUT tree over the S - 1 low bits for convergent (one LUT level
// for S - 1 up to 4 with the other terms, two above), none for truncate. Trade against fxp_round_fold: a shorter carry chain for a
// wider decision tree that does not exist in the fold form.
module fxp_round_inc #(
    parameter int W_IN  = 16,
    parameter int S     = 4,
    parameter int W_OUT = 12,
    parameter int MODE  = 2,
    parameter bit SAT   = 1'b1
) (
    input  logic             clk,
    input  logic             rst,
    input  logic             in_valid,
    output logic             in_ready,
    input  logic [W_IN-1:0]  x,
    output logic             out_valid,
    output logic [W_OUT-1:0] y
);
    localparam int W_R = W_IN - S + 1;

    logic [W_IN-S-1:0] fl;
    logic              inc;
    logic [W_R-1:0]    r;
    logic [W_OUT-1:0]  y_c;

    assign in_ready = 1'b1;
    assign fl = x[W_IN-1:S];
    if (S == 0 || MODE == 0) begin : g_none
        assign inc = 1'b0;
        if (S > 0) begin : g_un
            logic unused;
            assign unused = &{1'b0, x[S-1:0]};
        end
    end else if (MODE == 1) begin : g_half
        assign inc = x[S-1];
        if (S > 1) begin : g_un
            logic unused;
            assign unused = &{1'b0, x[S-2:0]};
        end
    end else if (S == 1) begin : g_conv1
        assign inc = x[0] & x[1];              // the tie is the only case: round up when the result's LSB is 1
    end else begin : g_conv
        assign inc = x[S-1] & ((|x[S-2:0]) | x[S]);
    end
    assign r = {fl[W_IN-S-1], fl} + {{(W_R-1){1'b0}}, inc};

    fxp_sat #(.W_R(W_R), .W_OUT(W_OUT), .SAT(SAT)) u_sat (.r, .y(y_c));

    always_ff @(posedge clk) begin
        if (rst) out_valid <= 1'b0;
        else     out_valid <= in_valid;
    end
    always_ff @(posedge clk) y <= y_c;
endmodule
