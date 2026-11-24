// div_nr_newton: division by Newton-Raphson reciprocal and one final multiply (brief 139c), fully pipelined.
//   a, b: W-bit normalised significands. q approximates a * 2**(W-1) / b (W bits, no remainder). Latency 2 + 4 * IT register stages: the seed read,
//   IT steps of (multiply, residual, multiply, add), then q = (a * y) >> F. One result per clock. F = W + 2.
// Primitive use (intended, not yet measured): the seed ROM and 2 * IT + 1 DSP multipliers in series (one DSP48E1 each when the operands fit 25 x 18,
// more above); a is delayed through the whole pipeline (a shift register of W bits, 4 * IT + 1 deep).
module div_nr_newton #(
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
    localparam int YW = F + 1;
    localparam int NA = 4 * IT + 1;       // a is delayed by this many stages to meet the final estimate
    localparam int NV = 4 * IT + 2;

    logic [F-1:0]  y0;
    logic [YW-1:0] y_s0, y_fin;
    logic [W-1:0]  b_s0, b_fin;
    logic [W-1:0]  a_sr [NA];
    logic [NV-1:0] v_q;
    logic [W+YW-1:0] prod;

    assign in_ready = 1'b1;
    div_nr_seed #(.W(W), .A(A), .F(F)) u_seed (.b, .y(y0));
    always_ff @(posedge clk) begin
        y_s0 <= {1'b0, y0};
        b_s0 <= b;
        a_sr[0] <= a;
        for (int i = 1; i < NA; i++) a_sr[i] <= a_sr[i-1];
    end
    for (genvar k = 0; k < IT; k++) begin : g_it
        logic [YW-1:0] y_in, y_out;
        logic [W-1:0]  b_in, b_out;
        if (k == 0) begin : g_in
            assign y_in = y_s0;
            assign b_in = b_s0;
        end else begin : g_in
            assign y_in = g_it[k-1].y_out;
            assign b_in = g_it[k-1].b_out;
        end
        div_nr_iter #(.W(W), .A(A), .F(F)) u (.clk, .b(b_in), .y(y_in), .b_o(b_out), .y_o(y_out));
    end
    assign y_fin = g_it[IT-1].y_out;
    assign b_fin = g_it[IT-1].b_out;
    assign prod  = a_sr[NA-1] * y_fin;
    always_ff @(posedge clk) q <= prod[F +: W];

    always_ff @(posedge clk) begin
        if (rst) v_q <= '0;
        else     v_q <= {v_q[NV-2:0], in_valid};
    end
    assign out_valid = v_q[NV-1];
    logic unused;
    assign unused = &{1'b0, b_fin, prod[F-1:0], prod[W+YW-1:F+W]};   // the quotient is below 2**W
endmodule
