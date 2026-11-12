// scan_checker.sv: properties of sevenseg_scan.sv from its ports: spec.yaml behaviour.display.
`include "v_macros.svh"

module scan_checker (
    input logic       clk,
    input logic       rst,
    input logic       enable,
    input logic [7:0] blank,
    input logic [7:0] an
);
    logic past_ok, seen_rst;
    initial begin past_ok = 1'b0; seen_rst = 1'b0; end
    always @(posedge clk) begin past_ok <= 1'b1; if (rst) seen_rst <= 1'b1; end

    // A_SC_ONE_DIGIT: at most one anode is low
    `V_SAME(A_SC_ONE_DIGIT, 1'b1, ((~an) & ((~an) - 8'd1)) == 8'd0)   // req: REQ-04
    // A_SC_BLANK: a digit blank on the previous clock (the anode register lags its inputs by one) is not lit
    `V_SAME(A_SC_BLANK, 1'b1, (~an & $past(blank)) == 8'd0)   // req: REQ-04
    // A_SC_DISABLED: DISPLAY_EN = 0 darkens every digit on the next clock
    `V_NEXT(A_SC_DISABLED, !enable, an == 8'hFF)   // req: REQ-04

    `V_COVER(C_SC_DIGIT_0_LIT, !an[0])   // req: REQ-04
    `V_COVER(C_SC_DIGIT_1_LIT, !an[1])   // req: REQ-04
    `V_COVER(C_SC_DIGIT_2_LIT, !an[2])   // req: REQ-04
    `V_COVER(C_SC_DIGIT_3_LIT, !an[3])   // req: REQ-04
    `V_COVER(C_SC_DIGIT_4_LIT, !an[4])   // req: REQ-04
    `V_COVER(C_SC_DIGIT_5_LIT, !an[5])   // req: REQ-04
    `V_COVER(C_SC_DIGIT_6_LIT, !an[6])   // req: REQ-04
    `V_COVER(C_SC_DIGIT_7_LIT, !an[7])   // req: REQ-04
    `V_COVER(C_SC_ALL_DARK_ENABLED, enable && an == 8'hFF)   // req: REQ-04
endmodule
