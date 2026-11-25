// brief 204a fixture: N registers, each with its own clock enable net (N control sets)
module toy_cs #(parameter N = 900) (input clk, input [7:0] d, output reg [N-1:0] q);
  (* dont_touch = "true" *) reg [N-1:0] en;
  always @(posedge clk) en <= {en[N-2:0], d[0] ^ d[1]};
  genvar i;
  generate for (i = 0; i < N; i = i + 1) begin : g
    always @(posedge clk) if (en[i]) q[i] <= d[i % 8];
  end endgenerate
endmodule
