// mac_fv: formal equivalence of the multiply-accumulate variants with mac_ref (arith brief 139a). Each variant is compared, in every clock, with the
// reference of its own latency fed the same free inputs (rst, en, clr, a, b), from the reset state of the first clock. P_DSP, P_FAB and P_CAS are the
// three assertions. Run by tools/run_formal.py (SymbiYosys, slang front end); the parameters are set per job in jobs.yaml.
module mac_fv #(
    parameter int WA     = 3,
    parameter int WB     = 3,
    parameter int LANES  = 2,
    parameter int ACCW   = 8,
    parameter int SIGNED = 1,
    parameter int NREG_D = 3,
    parameter int NREG_F = 2
) (
    input logic                clk,
    input logic                rst,
    input logic                en,
    input logic                clr,
    input logic [LANES*WA-1:0] a,
    input logic [LANES*WB-1:0] b
);
    logic [ACCW-1:0] acc_d, acc_f, acc_c, ref_d, ref_f, ref_c;
    mac_dsp         #(.WA(WA), .WB(WB), .LANES(LANES), .ACCW(ACCW), .SIGNED(SIGNED), .NREG(NREG_D)) u_d (.clk(clk), .rst(rst), .en(en), .clr(clr), .a(a), .b(b), .acc(acc_d));
    mac_fabric      #(.WA(WA), .WB(WB), .LANES(LANES), .ACCW(ACCW), .SIGNED(SIGNED), .NREG(NREG_F)) u_f (.clk(clk), .rst(rst), .en(en), .clr(clr), .a(a), .b(b), .acc(acc_f));
    mac_dsp_cascade #(.WA(WA), .WB(WB), .LANES(LANES), .ACCW(ACCW), .SIGNED(SIGNED))                 u_c (.clk(clk), .rst(rst), .en(en), .clr(clr), .a(a), .b(b), .acc(acc_c));
    mac_ref         #(.WA(WA), .WB(WB), .LANES(LANES), .ACCW(ACCW), .SIGNED(SIGNED), .LAT(NREG_D))   r_d (.clk(clk), .rst(rst), .en(en), .clr(clr), .a(a), .b(b), .acc(ref_d));
    mac_ref         #(.WA(WA), .WB(WB), .LANES(LANES), .ACCW(ACCW), .SIGNED(SIGNED), .LAT(NREG_F))   r_f (.clk(clk), .rst(rst), .en(en), .clr(clr), .a(a), .b(b), .acc(ref_f));
    mac_ref         #(.WA(WA), .WB(WB), .LANES(LANES), .ACCW(ACCW), .SIGNED(SIGNED), .LAT(LANES + 1)) r_c (.clk(clk), .rst(rst), .en(en), .clr(clr), .a(a), .b(b), .acc(ref_c));

    // the state after reset: every register of both sides is cleared by a first clock with rst high (the variants have no initial values)
    logic started = 1'b0;
    always_ff @(posedge clk) started <= 1'b1;
    always_comb begin
        if (!started) assume (rst);                   // the first clock is a reset clock
        if (started) begin
            P_DSP: assert (acc_d == ref_d);
            P_FAB: assert (acc_f == ref_f);
            P_CAS: assert (acc_c == ref_c);
        end
    end
endmodule
