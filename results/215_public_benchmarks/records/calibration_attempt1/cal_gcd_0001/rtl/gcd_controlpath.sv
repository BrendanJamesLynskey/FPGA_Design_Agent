/* verilator lint_off UNUSEDPARAM */
module gcd_controlpath #(parameter int WIDTH = 4) (
/* verilator lint_on UNUSEDPARAM */
  input  logic       clk,
  input  logic       rst,
  input  logic       go,
  input  logic       equal,
  input  logic       greater_than,
  output logic [1:0] controlpath_state,
  output logic       done
);
  logic [1:0] nxt;

  always_comb begin
    nxt = 2'b00;
    case (controlpath_state)
      2'b00: begin
        if (go) nxt = equal ? 2'b01 : (greater_than ? 2'b10 : 2'b11);
      end
      2'b01: nxt = 2'b00;
      default: nxt = equal ? 2'b01 : (greater_than ? 2'b10 : 2'b11);
    endcase
  end

  always_ff @(posedge clk) begin
    if (rst) begin
      controlpath_state <= 2'b00;
      done              <= 1'b0;
    end else begin
      controlpath_state <= nxt;
      done              <= (nxt == 2'b01);
    end
  end
endmodule
