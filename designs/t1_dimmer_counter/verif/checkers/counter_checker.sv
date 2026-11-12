// counter_checker.sv: properties of dimmer_counter.sv (the counter, the registers, the PWM) from the
// signals the bind connects: spec.yaml behaviour.counter and behaviour.pwm.
`include "v_macros.svh"

module counter_checker (
    input logic        clk,
    input logic        rst,
    input logic [15:0] count,
    input logic [7:0]  duty,
    input logic [1:0]  ctrl,
    input logic [7:0]  duty_eff,
    input logic [15:0] led,
    input logic        p_up,
    input logic        p_down,
    input logic        p_clear,
    input logic [7:0]  n_up,
    input logic [7:0]  n_down,
    input logic [7:0]  n_clear,
    input logic        win_wr,
    input logic [6:0]  win_addr,
    input logic [31:0] win_wdata
);
    logic past_ok, seen_rst;
    initial begin past_ok = 1'b0; seen_rst = 1'b0; end
    always @(posedge clk) begin past_ok <= 1'b1; if (rst) seen_rst <= 1'b1; end
    wire wr_count = win_wr && win_addr == 7'h00;

    `V_RST(A_CT_RESET, count == 16'h0 && duty == 8'h40 && ctrl == 2'b10 && n_up == 8'h0 && n_down == 8'h0 && n_clear == 8'h0)   // req: REQ-05
    `V_NEXT(A_CT_CLEAR, p_clear && !wr_count, count == 16'h0)   // req: REQ-01
    `V_NEXT(A_CT_UP, p_up && !p_clear && !wr_count, count == $past(count) + 16'd1)   // req: REQ-01
    `V_NEXT(A_CT_DOWN, p_down && !p_up && !p_clear && !wr_count, count == $past(count) - 16'd1)   // req: REQ-01
    `V_NEXT(A_CT_HOLD, !p_up && !p_down && !p_clear && !wr_count, count == $past(count))   // req: REQ-01
    `V_NEXT(A_CT_WRITE_WINS, wr_count, count == $past(win_wdata[15:0]))   // req: REQ-09
    `V_NEXT(A_CT_PRESS_COUNTED_UP, p_up, n_up == $past(n_up) + 8'd1)   // req: REQ-05
    `V_NEXT(A_CT_PRESS_COUNTED_DOWN, p_down, n_down == $past(n_down) + 8'd1)   // req: REQ-05
    `V_NEXT(A_CT_PRESS_COUNTED_CLEAR, p_clear, n_clear == $past(n_clear) + 8'd1)   // req: REQ-05
    `V_NEXT(A_CT_DUTY_WRITE, win_wr && win_addr == 7'h01, duty == $past(win_wdata[7:0]))   // req: REQ-05
    `V_NEXT(A_CT_CTRL_WRITE, win_wr && win_addr == 7'h02, ctrl == $past(win_wdata[1:0]))   // req: REQ-05
    `V_NEXT(A_CT_RO_IGNORED, win_wr && win_addr > 7'h04 && !p_up && !p_down && !p_clear, count == $past(count))   // req: REQ-05
    // PWM: LED[i] can only be lit where COUNT[i] is 1, and DUTY_EFF = 0 means fully off
    `V_SAME(A_PWM_SUBSET, 1'b1, (led & ~$past(count)) == 16'h0)   // req: REQ-03
    `V_SAME(A_PWM_ZERO_OFF, $past(duty_eff) == 8'h0, led == 16'h0)   // req: REQ-03

    `V_COVER(C_CT_WRAP_UP, p_up && !p_clear && count == 16'hFFFF)   // req: REQ-01
    `V_COVER(C_CT_WRAP_DOWN, p_down && !p_up && !p_clear && count == 16'h0)   // req: REQ-01
    `V_COVER(C_CT_SAME_CLOCK_PRESSES, (p_up && p_down) || (p_clear && (p_up || p_down)))   // req: REQ-01
    `V_COVER(C_CT_WRITE_AND_PRESS, wr_count && (p_up || p_down || p_clear))   // req: REQ-09
    `V_COVER(C_CT_DUTY_FULL, duty_eff == 8'hFF)   // req: REQ-03
endmodule
