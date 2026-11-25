// brief 204a fixture: one enable net with FO loads
module toy_fo #(parameter FO = 6000) (input clk, input en, input [FO-1:0] d, output [FO-1:0] q);
  (* keep = "true" *) reg en_r;
  reg [FO-1:0] r;
  always @(posedge clk) begin en_r <= en; if (en_r) r <= d; end
  assign q = r;
endmodule
