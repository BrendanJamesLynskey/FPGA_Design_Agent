// div_nr_fv: proof harness for the reciprocal-multiply divider variants (brief 139c), checked by SymbiYosys with the slang front end.
//   The inputs are assumed normalised (a and b have their MSB set). The result for the input accepted LAT cycles ago is q (W bits); the exact quotient is
//   a * 2**(W-1) / b and the error is e = a * 2**(W-1) / b - q in units of the last place. The characterisation is a pair of products, so it shares no code with the RTL:
//     upper:  e < UP_NUM / DEN   <=>  a * 2**(W-1) * DEN < (q * DEN + UP_NUM) * b
//     lower:  e > -LO_NUM / DEN  <=>  q * DEN <= LO_NUM  or  (q * DEN - LO_NUM) * b < a * 2**(W-1) * DEN      (LO_NUM = 0: e >= 0, i.e. q * b <= a * 2**(W-1))
//   P1 timing: out_valid is high exactly LAT cycles after an accepted input.
module div_nr_fv #(
    parameter int VARIANT = 0,
    parameter int W       = 8,
    parameter int A       = 3,
    parameter int IT      = 2,
    parameter int LAT     = 10,
    parameter int DEN     = 128,
    parameter int UP_NUM  = 193,
    parameter int LO_NUM  = 0
) (
    input logic           clk,
    input logic           rst,
    input logic           in_valid,
    input logic [2*W-1:0] in_data
);
    localparam int PW = 2 * W + 28;

    logic first = 1'b1;
    always_ff @(posedge clk) first <= 1'b0;
    always_comb a1_reset_first: assume (first == rst);
    always_comb a2_normalised:  assume (in_data[2*W-1] && in_data[W-1]);

    logic         in_ready, out_valid;
    logic [W-1:0] q;
    div_nr_sel #(.VARIANT(VARIANT), .W(W), .A(A), .IT(IT)) dut (.clk, .rst, .in_valid, .in_ready, .in_data, .out_valid, .out_data(q));

    logic           hv [LAT];
    logic [2*W-1:0] hd [LAT];
    always_ff @(posedge clk) begin
        hv[0] <= !rst && in_valid && in_ready;
        hd[0] <= in_data;
        for (int i = 1; i < LAT; i++) begin
            hv[i] <= hv[i-1] && !rst;
            hd[i] <= hd[i-1];
        end
    end

    logic [PW-1:0] a_w, b_w, q_w, num, up_l, up_r, lo_l, lo_r;
    always_comb begin
        a_w  = PW'(hd[LAT-1][2*W-1:W]);
        b_w  = PW'(hd[LAT-1][W-1:0]);
        q_w  = PW'(q);
        num  = (a_w << (W - 1)) * PW'(DEN);
        up_l = num;
        up_r = (q_w * PW'(DEN) + PW'(UP_NUM)) * b_w;
        lo_l = (q_w * PW'(DEN) > PW'(LO_NUM)) ? (q_w * PW'(DEN) - PW'(LO_NUM)) * b_w : '0;
        lo_r = num;
    end
    always_comb p1_timing: assert (first || out_valid == hv[LAT-1]);
    always_comb p2_upper:  assert (first || !out_valid || up_l < up_r);
    always_comb p3_lower:  assert (first || !out_valid || q_w * PW'(DEN) <= PW'(LO_NUM) || lo_l < lo_r);
    always_comb p3_one_sided: assert (first || !out_valid || LO_NUM != 0 || q_w * PW'(DEN) * b_w <= num);
endmodule
