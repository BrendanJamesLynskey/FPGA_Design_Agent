// Brief 208: a safe clock switch around one BUFGCTRL (7 series and UltraScale), written from UG472 ch. 2 / UG572 ch. 2.
// - Select on S (CE tied high): glitch-free whatever the timing of S.
// - IGNORE low in normal use, so the buffer waits for the old clock to go low before handing over.
// - A free-running reference clock watches both inputs. If the clock being left has stopped, the buffer would wait for
//   it forever; then IGNORE for that input is raised before S changes, and lowered once the new clock is selected.
// - A switch to an input that is not running is refused (busy stays high, err pulses), since the output would stop.
// - rst_out asks the logic on the muxed clock to be held in reset across a switch (Altera's condition: reset on switch).
module clk_switch_safe #(parameter DEAD_CYCLES = 16, parameter SETTLE_CYCLES = 32) (
  input  wire clk_ref,          // always running (an oscillator), not one of the switched clocks
  input  wire clk0, input wire clk1,
  input  wire req_sel,          // requested input, in the clk_ref domain
  output wire clk_out,
  output reg  cur_sel = 1'b0,   // the input currently selected
  output reg  busy = 1'b0, output reg err = 1'b0, output reg rst_out = 1'b1);

  // liveness: each input clock toggles a bit; clk_ref looks for changes
  reg t0 = 1'b0, t1 = 1'b0;
  always @(posedge clk0) t0 <= ~t0;
  always @(posedge clk1) t1 <= ~t1;
  (* ASYNC_REG = "TRUE" *) reg [2:0] s0 = 3'b0, s1 = 3'b0;
  reg [7:0] q0 = 8'd0, q1 = 8'd0;
  always @(posedge clk_ref) begin
    s0 <= {s0[1:0], t0};
    s1 <= {s1[1:0], t1};
    q0 <= (s0[2] != s0[1]) ? 8'd0 : (q0 == DEAD_CYCLES ? q0 : q0 + 8'd1);
    q1 <= (s1[2] != s1[1]) ? 8'd0 : (q1 == DEAD_CYCLES ? q1 : q1 + 8'd1);
  end
  wire alive0 = (q0 != DEAD_CYCLES), alive1 = (q1 != DEAD_CYCLES);

  reg s_sel = 1'b0, ign0 = 1'b0, ign1 = 1'b0;
  reg [7:0] wait_cnt = 8'd0;
  localparam IDLE = 2'd0, SWITCH = 2'd1, SETTLE = 2'd2;
  reg [1:0] st = IDLE;
  always @(posedge clk_ref) begin
    err <= 1'b0;
    case (st)
      IDLE: begin
        busy <= 1'b0;
        rst_out <= 1'b0;
        if (req_sel != cur_sel) begin
          if (!(req_sel ? alive1 : alive0)) err <= 1'b1;            // target not running: refuse
          else begin
            busy <= 1'b1; rst_out <= 1'b1;
            if (!(cur_sel ? alive1 : alive0)) begin                  // the clock being left has stopped
              if (cur_sel) ign1 <= 1'b1; else ign0 <= 1'b1;
            end
            st <= SWITCH;
          end
        end
      end
      SWITCH: begin s_sel <= req_sel; wait_cnt <= 8'd0; st <= SETTLE; end
      SETTLE: begin
        wait_cnt <= wait_cnt + 8'd1;
        if (wait_cnt == SETTLE_CYCLES) begin
          ign0 <= 1'b0; ign1 <= 1'b0; cur_sel <= s_sel; st <= IDLE;
        end
      end
      default: st <= IDLE;
    endcase
  end

  BUFGCTRL u_bufgctrl (.I0(clk0), .I1(clk1), .S0(~s_sel), .S1(s_sel), .CE0(1'b1), .CE1(1'b1),
                       .IGNORE0(ign0), .IGNORE1(ign1), .O(clk_out));
endmodule
