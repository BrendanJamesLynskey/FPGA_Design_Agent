// Pipelined binary-tree maximum value and index finder.
// Latency NumLevels+1 clocks, one input set per clock, ties pick the lower index.
// Reset: rst_ni active low. Tree registers use a synchronous reset (STD-RST-01);
// the outputs are additionally forced to 0 combinationally while rst_ni is low,
// so they clear without a clock edge (REQ-09).
module prim_max_find #(
  parameter int NumSrc = 8,
  parameter int Width  = 8,
  localparam int SrcWidth  = $clog2(NumSrc),
  localparam int NumLevels = $clog2(NumSrc),
  localparam int NumNodes  = 2**(NumLevels+1)
) (
  input  wire                  clk_i,
  input  wire                  rst_ni,
  input  wire [Width*NumSrc-1:0] values_i,
  input  wire [NumSrc-1:0]     valid_i,
  output wire [Width-1:0]      max_value_o,
  output wire [SrcWidth-1:0]   max_idx_o,
  output wire                  max_valid_o
);

  // Heap-numbered node storage, index 1..NumNodes-1
  logic [NumNodes-1:0]  vld_tree;
  logic [SrcWidth-1:0]  idx_tree [NumNodes];
  logic [Width-1:0]     val_tree [NumNodes];

  always_comb begin
    vld_tree[0] = 1'b0;
    idx_tree[0] = '0;
    val_tree[0] = '0;
  end

  for (genvar level = 0; level <= NumLevels; level++) begin : gen_tree
    for (genvar offset = 0; offset < 2**level; offset++) begin : gen_level
      localparam int Pa = 2**level + offset;
      if (level == NumLevels) begin : gen_leafs
        if (offset < NumSrc) begin : gen_assign
          always_ff @(posedge clk_i) begin
            if (!rst_ni) begin
              vld_tree[Pa] <= 1'b0;
              idx_tree[Pa] <= '0;
              val_tree[Pa] <= '0;
            end else begin
              vld_tree[Pa] <= valid_i[offset];
              idx_tree[Pa] <= SrcWidth'(offset);
              val_tree[Pa] <= values_i[offset*Width +: Width];
            end
          end
        end else begin : gen_tie_off
          always_comb begin
            vld_tree[Pa] = 1'b0;
            idx_tree[Pa] = '0;
            val_tree[Pa] = '0;
          end
        end
      end else begin : gen_nodes
        localparam int C0 = 2**(level+1) + 2*offset;
        localparam int C1 = C0 + 1;
        logic sel;
        assign sel = (~vld_tree[C0] & vld_tree[C1]) |
                     (vld_tree[C0] & vld_tree[C1] & (val_tree[C1] > val_tree[C0]));
        always_ff @(posedge clk_i) begin
          if (!rst_ni) begin
            vld_tree[Pa] <= 1'b0;
            idx_tree[Pa] <= '0;
            val_tree[Pa] <= '0;
          end else begin
            vld_tree[Pa] <= sel ? vld_tree[C1] : vld_tree[C0];
            idx_tree[Pa] <= sel ? idx_tree[C1] : idx_tree[C0];
            val_tree[Pa] <= sel ? val_tree[C1] : val_tree[C0];
          end
        end
      end
    end
  end

  assign max_valid_o = vld_tree[1] & rst_ni;
  assign max_idx_o   = rst_ni ? idx_tree[1] : '0;
  assign max_value_o = rst_ni ? val_tree[1] : '0;

endmodule
