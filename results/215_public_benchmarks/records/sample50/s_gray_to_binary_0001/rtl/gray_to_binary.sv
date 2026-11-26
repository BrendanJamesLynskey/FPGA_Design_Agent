// Parameterized Gray to Binary converter with debug mask, parity and valid.
// Purely combinational: no clock, no reset, no state.
module gray_to_binary #(
    parameter int WIDTH      = 4,
    parameter int DEBUG_MODE = 0
) (
    input  logic [WIDTH-1:0] gray_in,
    output logic [WIDTH-1:0] binary_out,
    output logic [WIDTH-1:0] debug_mask,
    output logic             parity,
    output logic             valid
);

  always_comb begin
    binary_out[WIDTH-1] = gray_in[WIDTH-1];
    for (int i = WIDTH - 2; i >= 0; i--) begin
      binary_out[i] = binary_out[i+1] ^ gray_in[i];
    end
  end

  if (DEBUG_MODE != 0) begin : g_dbg
    assign debug_mask = ~binary_out;
  end else begin : g_nodbg
    assign debug_mask = '0;
  end

  assign parity = ^binary_out;
  assign valid  = 1'b1;

endmodule
