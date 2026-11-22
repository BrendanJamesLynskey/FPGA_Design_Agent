// recip_nr: reciprocal by table seed and IT Newton-Raphson iterations, fully pipelined (brief 139c).
//   Latency 1 + 4 * IT register stages (the seed read, then multiply, residual, multiply, add per iteration); one result per clock.
//   F = W + 2 fractional bits inside; the output is the final estimate truncated to W fractional bits (W + 1 bits, at most 2**W).
// Primitive use (intended, not yet measured): the seed ROM and 2 * IT DSP multipliers (one DSP48E1 each when W <= 25 and W + 3 <= 18, more above).
module recip_nr #(
    parameter int W  = 16,
    parameter int A  = 7,
    parameter int IT = 1
) (
    input  logic          clk,
    input  logic          rst,
    input  logic          in_valid,
    output logic          in_ready,
    input  logic [W-1:0]  b,
    output logic          out_valid,
    output logic [W:0]    y
);
    localparam int F  = W + 2;
    localparam int YW = F + 1;
    localparam int NV = 4 * IT + 1;

    logic [F-1:0]  y0;
    logic [YW-1:0] y_s0, y_fin;
    logic [W-1:0]  b_s0, b_fin;
    logic [NV-1:0] v_q;

    assign in_ready = 1'b1;
    recip_seed #(.W(W), .A(A), .F(F)) u_seed (.b, .y(y0));
    always_ff @(posedge clk) begin
        y_s0 <= {1'b0, y0};
        b_s0 <= b;
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
        recip_iter #(.W(W), .A(A), .F(F)) u (.clk, .b(b_in), .y(y_in), .b_o(b_out), .y_o(y_out));
    end
    assign y_fin = g_it[IT-1].y_out;
    assign b_fin = g_it[IT-1].b_out;
    assign y = y_fin[YW-1:2];              // truncate to W fractional bits

    always_ff @(posedge clk) begin
        if (rst) v_q <= '0;
        else     v_q <= {v_q[NV-2:0], in_valid};
    end
    assign out_valid = v_q[NV-1];
    logic unused;
    assign unused = &{1'b0, y_fin[1:0], b_fin};
endmodule
