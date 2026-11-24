// recip_seed: reciprocal seed table (brief 139c). y = round(2**F / B_mid) for the interval of B = b / 2**(W-1) selected by the A bits below
// the leading one; the constant is computed at elaboration with integer arithmetic only (the same formula as model.seed):
//   ((2**(F+A+2)) + num) / (2 * num), num = 2**(A+1) + 2*idx + 1.
// Primitive use (intended, not yet measured): a 2**A-entry, F-bit ROM read by an A-bit address: distributed (LUT) ROM at A <= 7, about
// F * 2**(A-6) LUT6 plus output multiplexers; a block RAM (one RAMB18 up to 18 bits wide, A = 9 or 10) only if the tool is told to, which would
// add the RAM's output register to the latency.
module recip_seed #(
    parameter int W = 16,
    parameter int A = 7,
    parameter int F = 18
) (
    input  logic [W-1:0] b,
    output logic [F-1:0] y
);
    localparam int N = 1 << A;
    function automatic logic [N*F-1:0] mk();
        logic [N*F-1:0]  v;
        longint unsigned num;
        for (int i = 0; i < N; i++) begin
            num = (64'd1 << (A + 1)) + 64'(2 * i) + 64'd1;
            v[i*F +: F] = F'(((64'd1 << (F + A + 2)) + num) / (64'd2 * num));
        end
        return v;
    endfunction
    localparam logic [N*F-1:0] TAB = mk();

    logic [A-1:0] idx;
    logic         unused;
    assign idx = b[W-2 -: A];
    assign y   = TAB[int'(idx) * F +: F];
    assign unused = &{1'b0, b[W-1], b[W-2-A:0]};
endmodule
