// Data bus inversion encoder with enable. Reset is applied synchronously (design standard STD-RST-01).
module dbi_enc #(
  parameter int GROUPS        = 5,
  parameter int GROUP_WIDTH   = 8,
  parameter int DBI_THRESHOLD = 4
) (
  input  wire                          rst_n,      // active low, sampled on clk
  input  wire                          clk,
  input  wire                          dbi_enable,
  input  wire [GROUPS*GROUP_WIDTH-1:0] data_in,
  output wire [GROUPS-1:0]             dbi_cntrl,
  output wire [GROUPS*GROUP_WIDTH-1:0] data_out
);
  localparam int N = GROUPS*GROUP_WIDTH;

  reg  [N+GROUPS-1:0] dbi_data_out;
  wire [GROUPS-1:0]   dbi_bits;
  wire [N-1:0]        next_data;

  assign data_out  = dbi_data_out[N-1:0];
  assign dbi_cntrl = dbi_data_out[N+GROUPS-1:N];

  genvar g;
  generate
    for (g = 0; g < GROUPS; g++) begin : g_grp
      wire [GROUP_WIDTH-1:0] cur = data_in[g*GROUP_WIDTH +: GROUP_WIDTH];
      wire [GROUP_WIDTH-1:0] prv = dbi_data_out[g*GROUP_WIDTH +: GROUP_WIDTH];
      wire [GROUP_WIDTH-1:0] dif = cur ^ prv;
      logic [7:0] cnt;
      always_comb begin
        cnt = 8'd0;
        for (int i = 0; i < GROUP_WIDTH; i++) cnt = cnt + 8'(dif[i]);
      end
      assign dbi_bits[g] = dbi_enable && (cnt > 8'(DBI_THRESHOLD));
      assign next_data[g*GROUP_WIDTH +: GROUP_WIDTH] = cur ^ {GROUP_WIDTH{dbi_bits[g]}};
    end
  endgenerate

  always_ff @(posedge clk) begin
    if (!rst_n) dbi_data_out <= '0;
    else        dbi_data_out <= {dbi_bits, next_data};
  end
endmodule
