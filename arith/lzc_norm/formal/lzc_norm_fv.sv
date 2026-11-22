// lzc_norm_fv: proof harness for the leading-zero / normaliser variants (brief 139b), checked by SymbiYosys with the slang front end.
//   Same structure as divider_fv. The reference is a characterisation: for x = 0, lz = W and y = 0; otherwise lz < W, every bit of x above
//   position W - 1 - lz is zero, bit W - 1 - lz is one, and y = x << lz (W bits), which has its MSB set.
//   P1 timing, P2 value, P3 (VARIANT_B >= 0) the two variants agree.
module lzc_norm_fv #(
    parameter int VARIANT   = 0,
    parameter int VARIANT_B = -1,
    parameter int W         = 8,
    parameter int PIPE      = 1,
    parameter int PIPE_B    = 1,
    parameter int LAT       = 1,
    parameter bit REF       = 1'b1
) (
    input logic         clk,
    input logic         rst,
    input logic         in_valid,
    input logic [W-1:0] in_data
);
    localparam int LW = $clog2(W + 1);
    localparam int OW = W + LW;

    logic first = 1'b1;
    always_ff @(posedge clk) first <= 1'b0;
    always_comb a1_reset_first: assume (first == rst);

    logic          in_ready_a, out_valid_a;
    logic [OW-1:0] out_a;
    lznorm_sel #(.VARIANT(VARIANT), .W(W), .PIPE(PIPE)) dut_a (.clk, .rst, .in_valid, .in_ready(in_ready_a), .in_data, .out_valid(out_valid_a), .out_data(out_a));

    if (VARIANT_B >= 0) begin : g_pair
        logic          in_ready_b, out_valid_b;
        logic [OW-1:0] out_b;
        lznorm_sel #(.VARIANT(VARIANT_B), .W(W), .PIPE(PIPE_B)) dut_b (.clk, .rst, .in_valid, .in_ready(in_ready_b), .in_data, .out_valid(out_valid_b), .out_data(out_b));
        always_comb p3_valid_agree: assert (first || out_valid_a == out_valid_b);
        always_comb p3_data_agree:  assert (first || !out_valid_a || out_a == out_b);
        always_comb a2_ready:       assume (in_ready_a && in_ready_b);
    end

    logic         hv [LAT];
    logic [W-1:0] hd [LAT];
    always_ff @(posedge clk) begin
        hv[0] <= !rst && in_valid && in_ready_a;
        hd[0] <= in_data;
        for (int i = 1; i < LAT; i++) begin
            hv[i] <= hv[i-1] && !rst;
            hd[i] <= hd[i-1];
        end
    end

    logic [LW-1:0] lz;
    logic [W-1:0]  y, x, above;
    logic          ok;
    always_comb begin
        {lz, y} = out_a;
        x       = hd[LAT-1];
        above   = (lz == LW'(0)) ? '0 : (x >> (W - int'(lz)));         // the lz bits above the leading one: all zero
        if (x == '0) ok = (lz == LW'(W)) && (y == '0);
        else         ok = (lz < LW'(W)) && (above == '0) && x[W - 1 - int'(lz)] && (y == (x << lz)) && y[W-1];
    end
    if (REF) begin : g_ref
        always_comb p1_timing: assert (first || out_valid_a == hv[LAT-1]);
        always_comb p2_value:  assert (first || !out_valid_a || ok);
    end
endmodule
