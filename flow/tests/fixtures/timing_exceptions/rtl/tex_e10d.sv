// E10D: the alternative to E10: the FSM runs on a clock divided by 8 in the fabric (a counter bit through a BUFG), so it
// is a second clock; the fast consumer samples the FSM's gain on the 125 MHz clock, on the enable that follows the divider.
(* use_dsp = "no" *)
module tex_e10d (input logic clk, input logic [15:0] k_in, input logic [15:0] x_in, output logic [31:0] y_out,
                 output logic [1:0] st_out);
    logic [2:0] div = '0;
    logic en = 1'b0;
    always_ff @(posedge clk) begin
        div <= div + 3'd1;
        en <= (div == 3'd7);
    end
    logic clk_slow;
    BUFG bs (.I(div[2]), .O(clk_slow));
    typedef enum logic [1:0] {IDLE, RAMP, HOLD, DONE} st_t;
    st_t st = IDLE;
    logic [31:0] gain = '0;
    logic [15:0] k = '0;
    always_ff @(posedge clk_slow) begin
        k <= k_in;
        case (st)
            IDLE: begin gain <= '0; st <= RAMP; end
            RAMP: begin gain <= gain + k * k; if (gain[31]) st <= HOLD; end
            HOLD: st <= DONE;
            default: st <= IDLE;
        endcase
    end
    logic [31:0] gain_q = '0;
    logic [31:0] y = '0;
    always_ff @(posedge clk) begin
        if (en) gain_q <= gain;
        y <= y + {16'd0, x_in} + gain_q;
    end
    assign y_out = y;
    assign st_out = st;
endmodule
