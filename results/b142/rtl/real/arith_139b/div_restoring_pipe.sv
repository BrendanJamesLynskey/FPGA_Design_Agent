// div_restoring_pipe: unsigned W-bit restoring divider, unrolled, PIPE quotient bits per pipeline stage (brief 139b).
//   n / d -> q, r; d = 0 gives q = all ones, r = n. One result per clock (in_ready = 1); latency ceil(W / PIPE).
//   PIPE = 1 registers every iteration (shortest path, most flip-flops); PIPE = W is one combinational array and one output register.
// Primitive use (intended, not yet measured): W trial subtractors of W + 1 bits, each ceil((W+1)/4) CARRY4 in series inside a stage
// (the carry-out of one feeds the restore mux select of that iteration and so the next iteration's subtractor input: PIPE carry chains
// and PIPE LUT layers on the stage's path); flip-flops per stage: partial remainder, dividend/quotient register and the divisor.
module div_restoring_pipe #(
    parameter int W    = 8,
    parameter int PIPE = 1                // iterations per register stage, 1 to W
) (
    input  logic         clk,
    input  logic         rst,
    input  logic         in_valid,
    output logic         in_ready,
    input  logic [W-1:0] n,
    input  logic [W-1:0] d,
    output logic         out_valid,
    output logic [W-1:0] q,
    output logic [W-1:0] r
);
    localparam int S = (W + PIPE - 1) / PIPE;

    logic [W-1:0] n_q [S];                // register outputs of stage s (the result of stage s), s = 0 .. S-1
    logic [W-1:0] p_q [S];
    logic [S-1:0] v_q;

    assign in_ready = 1'b1;

    for (genvar s = 0; s < S; s++) begin : g_stage
        localparam int IT = (W - s * PIPE < PIPE) ? (W - s * PIPE) : PIPE;
        logic [W-1:0] n_i, d_i, n_c;          // stage input and stage result (combinational)
        logic [W-1:0] p_i, p_c;
        logic         v_i;
        if (s == 0) begin : g_first
            assign n_i = n;
            assign p_i = '0;
            assign d_i = d;
            assign v_i = in_valid;
        end else begin : g_next
            assign n_i = n_q[s-1];
            assign p_i = p_q[s-1];
            assign d_i = g_stage[s-1].g_d.d_q;
            assign v_i = v_q[s-1];
        end
        always_comb begin : iterate
            logic [W-1:0] rn_v;
            logic [W-1:0] p_v;
            logic [W-1:0] sh_v;               // below 2**W: p is below 2**(iterations done) and fewer than W are done
            logic [W:0]   t_v;
            rn_v = n_i;
            p_v  = p_i;
            for (int k = 0; k < IT; k++) begin
                sh_v = {p_v[W-2:0], rn_v[W-1]};
                t_v  = {1'b0, sh_v} - {1'b0, d_i};
                p_v  = t_v[W] ? sh_v : t_v[W-1:0];
                rn_v = {rn_v[W-2:0], ~t_v[W]};
            end
            n_c = rn_v;
            p_c = p_v;
        end
        if (s != S - 1) begin : g_d            // the last stage has no use for the divisor afterwards
            logic [W-1:0] d_q;
            always_ff @(posedge clk) d_q <= d_i;
        end
        always_ff @(posedge clk) begin
            n_q[s] <= n_c;
            p_q[s] <= p_c;
        end
        always_ff @(posedge clk) begin
            if (rst) v_q[s] <= 1'b0;
            else     v_q[s] <= v_i;
        end
    end

    assign out_valid = v_q[S-1];
    assign q         = n_q[S-1];
    assign r         = p_q[S-1];
endmodule
