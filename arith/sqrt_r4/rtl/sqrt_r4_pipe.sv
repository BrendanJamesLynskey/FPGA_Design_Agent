// sqrt_r4_pipe: radix-4 integer square root, unrolled, PIPE digit steps per pipeline stage (brief 139c).
//   x -> root, rem as sqrt_r4_iter. One result per clock; latency ceil(RP / PIPE), RP = ceil(RW/2), RW = ceil(W/2).
// Primitive use (intended, not yet measured): RP steps of three parallel (QW+4)-bit trial subtractors and one 24q+9 adder each (PIPE steps in
// series between registers); the early steps are narrower than the last (the root grows two bits per step), which synthesis trims to constants.
// Flip-flops per stage: remaining radicand, root and remainder.
module sqrt_r4_pipe #(
    parameter int W    = 16,
    parameter int PIPE = 1                // digit steps per register stage, 1 to RP
) (
    input  logic            clk,
    input  logic            rst,
    input  logic            in_valid,
    output logic            in_ready,
    input  logic [W-1:0]    x,
    output logic            out_valid,
    output logic [(W+1)/2-1:0] root,
    output logic [(W+1)/2:0]   rem
);
    localparam int RW = (W + 1) / 2;
    localparam int RP = (RW + 1) / 2;
    localparam int QW = 2 * RP;
    localparam int S  = (RP + PIPE - 1) / PIPE;

    logic [QW-1:0]   q_q [S];
    logic [QW:0]     r_q [S];
    logic [S-1:0]    v_q;

    assign in_ready = 1'b1;

    for (genvar s = 0; s < S; s++) begin : g_stage
        localparam int IT = (RP - s * PIPE < PIPE) ? (RP - s * PIPE) : PIPE;
        logic [4*RP-1:0] xs_i, xs_c;
        logic [QW-1:0]   q_i, q_c;
        logic [QW:0]     r_i, r_c;
        logic            v_i;
        if (s == 0) begin : g_first
            assign xs_i = (4*RP)'(x);
            assign q_i  = '0;
            assign r_i  = '0;
            assign v_i  = in_valid;
        end else begin : g_next
            assign xs_i = g_stage[s-1].g_x.xs_q;
            assign q_i  = q_q[s-1];
            assign r_i  = r_q[s-1];
            assign v_i  = v_q[s-1];
        end
        always_comb begin : iterate
            logic [4*RP-1:0] xs_v;
            logic [QW-1:0]   q_v;
            logic [QW:0]     r_v;
            logic [QW+2:0]   sh_v, t1_v, t2_v, t3_v;
            logic [QW+3:0]   d1_v, d2_v, d3_v;
            logic [QW-3:0]   qq_v;
            xs_v = xs_i;
            q_v  = q_i;
            r_v  = r_i;
            for (int k = 0; k < IT; k++) begin
                sh_v = {r_v[QW-2:0], xs_v[4*RP-1:4*RP-4]};
                qq_v = q_v[QW-3:0];
                t1_v = {2'b00, qq_v, 3'b001};
                t2_v = {1'b0, qq_v, 4'b0100};
                t3_v = (QW+3)'({qq_v, 4'b0000}) + (QW+3)'({qq_v, 3'b000}) + (QW+3)'(9);
                d1_v = {1'b0, sh_v} - {1'b0, t1_v};
                d2_v = {1'b0, sh_v} - {1'b0, t2_v};
                d3_v = {1'b0, sh_v} - {1'b0, t3_v};
                if (!d3_v[QW+3])      begin r_v = d3_v[QW:0]; q_v = {qq_v, 2'b11}; end
                else if (!d2_v[QW+3]) begin r_v = d2_v[QW:0]; q_v = {qq_v, 2'b10}; end
                else if (!d1_v[QW+3]) begin r_v = d1_v[QW:0]; q_v = {qq_v, 2'b01}; end
                else                  begin r_v = sh_v[QW:0]; q_v = {qq_v, 2'b00}; end
                xs_v = {xs_v[4*RP-5:0], 4'b0000};
            end
            xs_c = xs_v;
            q_c  = q_v;
            r_c  = r_v;
        end
        if (s != S - 1) begin : g_x            // the last stage has no use for the remaining radicand afterwards
            logic [4*RP-1:0] xs_q;
            always_ff @(posedge clk) xs_q <= xs_c;
        end else begin : g_xend
            logic unused;
            assign unused = &{1'b0, xs_c};
        end
        always_ff @(posedge clk) begin
            q_q[s] <= q_c;
            r_q[s] <= r_c;
        end
        always_ff @(posedge clk) begin
            if (rst) v_q[s] <= 1'b0;
            else     v_q[s] <= v_i;
        end
    end

    logic unused_top;
    assign root = q_q[S-1][RW-1:0];
    assign rem  = r_q[S-1][RW:0];
    if (QW > RW) begin : g_un
        assign unused_top = &{1'b0, q_q[S-1][QW-1:RW], r_q[S-1][QW:RW+1]};
    end else begin : g_un
        assign unused_top = 1'b0;
    end
    assign out_valid = v_q[S-1];
endmodule
