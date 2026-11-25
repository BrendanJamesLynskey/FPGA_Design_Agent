// brief 204a fixture: a deep logic path. KEEP stops synthesis merging the levels, so the netlist has LV LUT levels.
module toy_lvl #(parameter LV = 12) (input clk, input [LV:0] d, output reg q);
  (* keep = "true" *) wire [LV:0] w;
  reg [LV:0] r;
  assign w[0] = r[0];
  genvar i;
  generate for (i = 1; i <= LV; i = i + 1) begin : g
    assign w[i] = (i % 2) ? (w[i-1] ^ r[i]) : (w[i-1] & ~r[i]);
  end endgenerate
  always @(posedge clk) begin r <= d; q <= w[LV]; end
endmodule
