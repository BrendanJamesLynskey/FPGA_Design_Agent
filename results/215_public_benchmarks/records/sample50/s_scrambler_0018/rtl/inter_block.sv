module inter_block #(
    parameter ROW_COL_WIDTH = 16,
    parameter SUB_BLOCKS    = 4,
    parameter DATA_WIDTH    = ROW_COL_WIDTH*ROW_COL_WIDTH
)(
    input  logic clk,
    input  logic rst_n,
    input  logic i_valid,
    input  logic [DATA_WIDTH-1:0] in_data,
    output logic [DATA_WIDTH-1:0] out_data
);

localparam CHUNK = 8;
localparam NCHUNK = DATA_WIDTH / CHUNK;
localparam NBW_COUNTER = $clog2(SUB_BLOCKS) + 1;
localparam NBW_COUNTER_SUB_OUT = 2;

logic [NBW_COUNTER-1:0] counter_sub_blocks;
logic [NBW_COUNTER_SUB_OUT-1:0] counter_sub_out;

logic [DATA_WIDTH-1:0] in_data_reg [SUB_BLOCKS-1:0];
logic [DATA_WIDTH-1:0] out_data_intra_block [SUB_BLOCKS-1:0];
logic [DATA_WIDTH-1:0] out_data_intra_block_reg [SUB_BLOCKS-1:0];
logic [DATA_WIDTH-1:0] out_data_aux [SUB_BLOCKS-1:0];
logic start_intra;

// Synchronous reset (design standard STD-RST-01)
always_ff @(posedge clk) begin
   if (!rst_n) begin
      counter_sub_blocks <= '0;
      start_intra <= 1'b0;
      for (int i = 0; i < SUB_BLOCKS; i++) begin
         in_data_reg[i] <= '0;
      end
   end
   else begin
      if (i_valid) begin
         if (counter_sub_blocks < NBW_COUNTER'(SUB_BLOCKS)) begin
            in_data_reg[counter_sub_blocks[$clog2(SUB_BLOCKS)-1:0]] <= in_data;
         end

         if (counter_sub_blocks == NBW_COUNTER'(SUB_BLOCKS)) begin
            counter_sub_blocks <= '0;
         end
         else begin
            start_intra <= 1'b0;
            counter_sub_blocks <= counter_sub_blocks + 1'b1;
         end
      end
      else if (counter_sub_blocks == NBW_COUNTER'(SUB_BLOCKS)) begin
         start_intra        <= 1'b1;
         counter_sub_blocks <= '0;
      end
   end
end

genvar k;
generate
   for (k = 0; k < SUB_BLOCKS; k++) begin : g_intra
      intra_block #(
         .ROW_COL_WIDTH(ROW_COL_WIDTH),
         .DATA_WIDTH(DATA_WIDTH)
      ) uu_intra_block (
         .in_data(in_data_reg[k]),
         .out_data(out_data_intra_block[k])
      );
   end
endgenerate

always_ff @(posedge clk) begin
   if (!rst_n) begin
      for (int i = 0; i < SUB_BLOCKS; i++) begin
         out_data_intra_block_reg[i] <= '0;
      end
   end
   else if (start_intra) begin
      for (int i = 0; i < SUB_BLOCKS; i++) begin
         out_data_intra_block_reg[i] <= out_data_intra_block[i];
      end
   end
end

always_ff @(posedge clk) begin
   if (!rst_n) begin
      counter_sub_out <= {NBW_COUNTER_SUB_OUT{1'b1}};
      out_data        <= '0;
      for (int i = 0; i < SUB_BLOCKS; i++) begin
         out_data_aux[i] <= '0;
      end
   end
   else if (start_intra) begin
      // aux[j] = byte-reversed out_data_intra_block_reg[j]
      for (int j = 0; j < SUB_BLOCKS; j++) begin
         for (int i = 0; i < NCHUNK; i++) begin
            out_data_aux[j][i*CHUNK +: CHUNK] <=
               out_data_intra_block_reg[j][(NCHUNK-1-i)*CHUNK +: CHUNK];
         end
      end
      counter_sub_out <= counter_sub_out + 1'b1;
      out_data        <= out_data_aux[counter_sub_out];
   end
end

endmodule
