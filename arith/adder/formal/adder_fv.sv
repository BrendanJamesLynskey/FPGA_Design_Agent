// adder_fv: formal equivalence of the adder variants (arith brief 139a). The reference is adder_ripple (a single `+`).
//   carry_select == ripple in the same clock (combinational equivalence)
//   pipelined    == ripple delayed by STAGES clocks (a data-only pipeline: it is compared once STAGES clocks have passed since the start)
// Inputs are free in every clock. Run by tools/run_formal.py (SymbiYosys, slang front end); the parameters are set per job in jobs.yaml.
module adder_fv #(
    parameter int WIDTH  = 8,
    parameter int BLOCK  = 3,
    parameter int STAGES = 3
) (
    input logic             clk,
    input logic [WIDTH-1:0] a,
    input logic [WIDTH-1:0] b,
    input logic             cin,
    input logic             sub
);
    logic [WIDTH-1:0] s_r, s_c, s_p;
    logic             co_r, co_c, co_p, ovf_r, ovf_c, ovf_p;
    adder_ripple #(.WIDTH(WIDTH)) u_r (.clk(clk), .a(a), .b(b), .cin(cin), .sub(sub), .s(s_r), .co(co_r), .ovf(ovf_r));
    adder_carry_select #(.WIDTH(WIDTH), .BLOCK(BLOCK)) u_c (.clk(clk), .a(a), .b(b), .cin(cin), .sub(sub), .s(s_c), .co(co_c), .ovf(ovf_c));
    adder_pipelined #(.WIDTH(WIDTH), .STAGES(STAGES)) u_p (.clk(clk), .a(a), .b(b), .cin(cin), .sub(sub), .s(s_p), .co(co_p), .ovf(ovf_p));

    always_comb begin
        P_CS_SUM: assert (s_c == s_r);
        P_CS_CO:  assert (co_c == co_r);
        P_CS_OVF: assert (ovf_c == ovf_r);
    end

    logic [WIDTH+1:0] d [STAGES];                // the reference result, delayed 1 .. STAGES clocks
    logic [7:0]       warm = 8'd0;               // clocks since the start, saturating at STAGES
    always_ff @(posedge clk) begin
        d[0] <= {ovf_r, co_r, s_r};
        for (int j = 1; j < STAGES; j++) d[j] <= d[j-1];
        if (warm != STAGES[7:0]) warm <= warm + 8'd1;
    end
    always_comb begin
        if (warm == STAGES[7:0]) begin
            P_PL: assert ({ovf_p, co_p, s_p} == d[STAGES-1]);
        end
    end
endmodule
