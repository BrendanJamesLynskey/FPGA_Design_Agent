// E10: slow control FSM on the shared 125 MHz clock, advanced by a 1-in-8 enable; the fast consumer samples it on the enable.
(* use_dsp = "no" *)
module tex_e10 (input logic clk, input logic [15:0] k_in, input logic [15:0] x_in, output logic [31:0] y_out,
               output logic [1:0] st_out);
    // the 1-in-8 enable, from a counter in the same clock: en is 1 on one clock in eight
    logic [2:0] div = '0;
    logic en = 1'b0;
    always_ff @(posedge clk) begin
        div <= div + 3'd1;
        en <= (div == 3'd7);
    end
    // the slow FSM: every register loads only when en is 1 (tagged fda_slow_en for the multicycle)
    typedef enum logic [1:0] {IDLE, RAMP, HOLD, DONE} st_t;
    (* fda_slow_en = "true" *) st_t st = IDLE;
    (* fda_slow_en = "true" *) logic [31:0] gain = '0;
    (* fda_slow_en = "true" *) logic [15:0] k = '0;
    always_ff @(posedge clk) if (en) begin
        k <= k_in;
        case (st)
            IDLE: begin gain <= '0; st <= RAMP; end
            RAMP: begin gain <= gain + k * k; if (gain[31]) st <= HOLD; end
            HOLD: st <= DONE;
            default: st <= IDLE;
        endcase
    end
    // the fast unit, every clock: its copy of the FSM's gain, then a one-clock datapath
    (* fda_slow_en = "true" *) logic [31:0] gain_q = '0;
    logic [31:0] y = '0;
    always_ff @(posedge clk) begin
        if (en) gain_q <= gain;   // qualified: samples the FSM only on the enable
        y <= y + {16'd0, x_in} + gain_q;
    end
    assign y_out = y;
    assign st_out = st;
endmodule
