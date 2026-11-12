// mini_checker.sv: brief 53 fixture checker.
module mini_checker (input logic clk, input logic rst, input logic en, input logic [7:0] count);
    `V_NEXT(A_COUNT_UP, en, count == $past(count) + 8'd1)   // req: REQ-01
    // req: REQ-02
    `V_NEXT(A_COUNT_HOLD, !en, count == $past(count))
    `V_COVER(C_WRAP, en && count == 8'hFF)                   // req: REQ-01
endmodule
