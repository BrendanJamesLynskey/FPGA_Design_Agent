// mult_fv: formal equivalence of the multiplier variants (arith brief 139a). The reference is mult_dsp with STAGES = 0 (a single `*`, the
// natural expression of the function). The DSP variant (STAGES_D), the LUT array and the Booth multiplier (REG_L, REG_B) are each compared with
// the reference delayed by their own latency, once that many clocks have passed since the start. Inputs are free in every clock.
// Run by tools/run_formal.py (SymbiYosys, slang front end); the parameters are set per job in jobs.yaml.
module mult_fv #(
    parameter int WA       = 8,
    parameter int WB       = 8,
    parameter int SIGNED   = 1,
    parameter int STAGES_D = 3,
    parameter int REG_L    = 1,
    parameter int REG_B    = 1
) (
    input logic          clk,
    input logic [WA-1:0] a,
    input logic [WB-1:0] b
);
    localparam int PW = WA + WB;
    logic [PW-1:0] p_ref, p_d, p_l, p_b;
    mult_dsp       #(.WA(WA), .WB(WB), .SIGNED(SIGNED), .STAGES(0))        u_ref (.clk(clk), .a(a), .b(b), .p(p_ref));
    mult_dsp       #(.WA(WA), .WB(WB), .SIGNED(SIGNED), .STAGES(STAGES_D)) u_d   (.clk(clk), .a(a), .b(b), .p(p_d));
    mult_lut_array #(.WA(WA), .WB(WB), .SIGNED(SIGNED), .REG(REG_L))       u_l   (.clk(clk), .a(a), .b(b), .p(p_l));
    mult_booth_r4  #(.WA(WA), .WB(WB), .SIGNED(SIGNED), .REG(REG_B))       u_b   (.clk(clk), .a(a), .b(b), .p(p_b));

    logic [PW-1:0] d [3];                         // the reference product, delayed 1 .. 3 clocks
    logic [1:0]    warm = 2'd0;                   // clocks since the start, saturating at 3
    always_ff @(posedge clk) begin
        d[0] <= p_ref;
        d[1] <= d[0];
        d[2] <= d[1];
        if (warm != 2'd3) warm <= warm + 2'd1;
    end
    always_comb begin
        P_DSP: assert (STAGES_D == 0 ? p_d == p_ref : (warm < 2'(STAGES_D) || p_d == d[STAGES_D-1]));
        P_LUT: assert (REG_L == 0 ? p_l == p_ref : (warm < 2'(REG_L) || p_l == d[REG_L-1]));
        P_BOOTH: assert (REG_B == 0 ? p_b == p_ref : (warm < 2'(REG_B) || p_b == d[REG_B-1]));
    end
endmodule
