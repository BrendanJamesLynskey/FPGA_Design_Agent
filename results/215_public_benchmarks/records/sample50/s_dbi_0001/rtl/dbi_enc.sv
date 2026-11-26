// Data Bus Inversion encoder: 40-bit data as two 20-bit groups.
module dbi_enc #(
  parameter int GROUP_WIDTH      = 20,
  parameter int TOGGLE_THRESHOLD = 10
) (
  input  logic                     clk,
  input  logic                     rst_n,
  input  logic [2*GROUP_WIDTH-1:0] data_in,
  output logic [2*GROUP_WIDTH-1:0] data_out,
  output logic [1:0]               dbi_cntrl
);
  logic [1:0] inv;

  always_comb begin
    for (int g = 0; g < 2; g++) begin
      logic [GROUP_WIDTH-1:0] diff;
      int cnt;
      diff = data_in[g*GROUP_WIDTH +: GROUP_WIDTH] ^ data_out[g*GROUP_WIDTH +: GROUP_WIDTH];
      cnt  = 0;
      for (int i = 0; i < GROUP_WIDTH; i++) cnt = cnt + int'(diff[i]);
      inv[g] = (cnt > TOGGLE_THRESHOLD);
    end
  end

  // Synchronous reset (STD-RST-01): rst_n low clears the outputs at the next clk edge.
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      data_out  <= '0;
      dbi_cntrl <= 2'b00;
    end else begin
      dbi_cntrl <= inv;
      for (int g = 0; g < 2; g++)
        data_out[g*GROUP_WIDTH +: GROUP_WIDTH] <=
          data_in[g*GROUP_WIDTH +: GROUP_WIDTH] ^ {GROUP_WIDTH{inv[g]}};
    end
  end
endmodule
