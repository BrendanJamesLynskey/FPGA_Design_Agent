// div_nr_gs: Goldschmidt division, fully pipelined (brief 139c).
//   a, b: W-bit normalised significands. q approximates a * 2**(W-1) / b (W bits, no remainder). Latency 2 + 2 * IT register stages: the seed read; the two
//   multiplies n = a * y0 and d = b * y0 in parallel; then per iteration the factor r = 2 - d, and the two multiplies n = n * r and d = d * r in parallel
//   (the last iteration needs only n). One result per clock. F = W + 2.
// Primitive use (intended, not yet measured): the seed ROM and 2 * IT + 1 DSP multipliers, but only IT + 1 in series (against 2 * IT + 1 for
// div_nr_newton), so about half the latency at the same DSP count; the errors of the two multiplies do not correct each other, which the measured error bound includes.
module div_nr_gs #(
    parameter int W  = 16,
    parameter int A  = 7,
    parameter int IT = 2
) (
    input  logic          clk,
    input  logic          rst,
    input  logic          in_valid,
    output logic          in_ready,
    input  logic [W-1:0]  a,
    input  logic [W-1:0]  b,
    output logic          out_valid,
    output logic [W-1:0]  q
);
    localparam int F  = W + 2;
    localparam int NW = F + 2;            // n: value below 2 * 2**F
    localparam int DWD = F + 1;           // d and r: about 1.0 * 2**F, below 2 * 2**F
    localparam int NV = 2 * IT + 2;

    logic [F-1:0]  y0;
    logic [F-1:0]  y_s0;
    logic [W-1:0]  a_s0, b_s0;
    logic [NW-1:0] n_s1;
    logic [DWD-1:0] d_s1;
    logic [NV-1:0] v_q;
    logic [W+F-1:0] pa, pb;

    assign in_ready = 1'b1;
    div_nr_seed #(.W(W), .A(A), .F(F)) u_seed (.b, .y(y0));
    assign pa = a_s0 * y_s0;
    assign pb = b_s0 * y_s0;
    always_ff @(posedge clk) begin
        y_s0 <= y0;                                    // stage 1
        a_s0 <= a;
        b_s0 <= b;
        n_s1 <= NW'(pa >> (W - 1));                    // stage 2
        d_s1 <= DWD'(pb >> (W - 1));
    end

    for (genvar k = 0; k < IT; k++) begin : g_it
        logic [NW-1:0]  n_in, n_r, n_out;
        logic [DWD-1:0] d_in, d_r, r_q;
        logic [NW+DWD-1:0] pn;
        if (k == 0) begin : g_in
            assign n_in = n_s1;
            assign d_in = d_s1;
        end else begin : g_in
            assign n_in = g_it[k-1].n_out;
            assign d_in = g_it[k-1].g_d.d_out;
        end
        assign pn = n_r * r_q;
        always_ff @(posedge clk) begin
            r_q <= DWD'({1'b1, {(F+1){1'b0}}} - {1'b0, d_in});  // residual stage: r = 2 - d
            n_r <= n_in;
            d_r <= d_in;
            n_out <= NW'(pn >> F);                     // multiply stage
        end
        if (k < IT - 1) begin : g_d
            logic [DWD-1:0]   d_out;
            logic [2*DWD-1:0] pd;
            assign pd = d_r * r_q;
            always_ff @(posedge clk) d_out <= DWD'(pd >> F);
        end else begin : g_nod
            logic unused_d;
            assign unused_d = &{1'b0, d_r};
        end
    end

    logic [NW-1:0] n_fin;
    assign n_fin = g_it[IT-1].n_out;
    assign q     = n_fin[F-(W-1) +: W];

    always_ff @(posedge clk) begin
        if (rst) v_q <= '0;
        else     v_q <= {v_q[NV-2:0], in_valid};
    end
    assign out_valid = v_q[NV-1];
    logic unused;
    assign unused = &{1'b0, n_fin[F-W:0], n_fin[NW-1:F+1]};
endmodule
