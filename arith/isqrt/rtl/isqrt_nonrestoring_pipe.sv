// isqrt_nonrestoring_pipe: non-restoring integer square root, unrolled, PIPE result bits per stage (brief 139b).
//   x -> root, rem as isqrt_restoring_iter. One result per clock; latency ceil(RW / PIPE). Each step adds or subtracts according to the
//   sign of the remainder; the root bit is the new sign. A final correction (add 2*root + 1 to a negative remainder) is folded into the last stage.
// Primitive use (intended, not yet measured): RW add/subtract carry chains of RW + 3 bits (a LUT per bit selects +{root,11} or -{root,01}
// by the previous sign), no restore multiplexer, one more (RW+1)-bit adder in the last stage. Against isqrt_restoring_pipe it removes the
// restore mux layer and adds the correction adder; whether that wins is for the Vivado runs.
module isqrt_nonrestoring_pipe #(
    parameter int W    = 16,
    parameter int PIPE = 1
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
    localparam int S  = (RW + PIPE - 1) / PIPE;

    logic [RW-1:0]   rt_q [S];
    logic [RW+1:0]   rm_q [S];            // signed remainder, RW + 2 bits
    logic [S-1:0]    v_q;

    assign in_ready = 1'b1;

    for (genvar s = 0; s < S; s++) begin : g_stage
        localparam int IT   = (RW - s * PIPE < PIPE) ? (RW - s * PIPE) : PIPE;
        localparam bit LAST = (s == S - 1);
        logic [2*RW-1:0] xs_i, xs_c;
        logic [RW-1:0]   rt_i, rt_c;
        logic [RW+1:0]   rm_i, rm_c;
        logic            v_i;
        if (s == 0) begin : g_first
            assign xs_i = (2*RW)'(x);
            assign rt_i = '0;
            assign rm_i = '0;
            assign v_i  = in_valid;
        end else begin : g_next
            assign xs_i = g_stage[s-1].g_x.xs_q;
            assign rt_i = rt_q[s-1];
            assign rm_i = rm_q[s-1];
            assign v_i  = v_q[s-1];
        end
        always_comb begin : iterate
            logic [2*RW-1:0] xs_v;
            logic [RW-1:0]   rt_v;
            logic [RW+1:0]   rm_v;
            logic [RW+2:0]   sh_v;        // 4*rem + pair, signed: rem fits RW + 1 bits before every step
            logic [RW:0]     tr_v;        // {root, 2'b11} (rem negative) or {root, 2'b01} (rem not negative)
            logic [RW+2:0]   t_v;
            xs_v = xs_i;
            rt_v = rt_i;
            rm_v = rm_i;
            for (int k = 0; k < IT; k++) begin
                sh_v = {rm_v[RW:0], xs_v[2*RW-1:2*RW-2]};
                tr_v = {rt_v[RW-2:0], rm_v[RW+1], 1'b1};
                t_v  = rm_v[RW+1] ? sh_v + {2'b00, tr_v} : sh_v - {2'b00, tr_v};
                rm_v = t_v[RW+1:0];
                rt_v = {rt_v[RW-2:0], ~t_v[RW+1]};
                xs_v = {xs_v[2*RW-3:0], 2'b00};
            end
            if (LAST && rm_v[RW+1]) rm_v = rm_v + {1'b0, rt_v, 1'b1};
            xs_c = xs_v;
            rt_c = rt_v;
            rm_c = rm_v;
        end
        if (s != S - 1) begin : g_x            // the last stage has no use for the remaining radicand afterwards
            logic [2*RW-1:0] xs_q;
            always_ff @(posedge clk) xs_q <= xs_c;
        end else begin : g_xend
            logic unused;
            assign unused = &{1'b0, xs_c};
        end
        always_ff @(posedge clk) begin
            rt_q[s] <= rt_c;
            rm_q[s] <= rm_c;
        end
        always_ff @(posedge clk) begin
            if (rst) v_q[s] <= 1'b0;
            else     v_q[s] <= v_i;
        end
    end

    assign out_valid = v_q[S-1];
    assign root      = rt_q[S-1];
    assign rem       = rm_q[S-1][RW:0];
    logic unused;
    assign unused = &{1'b0, rm_q[S-1][RW+1]};
endmodule
