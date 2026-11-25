// deinter_block: 4 x DATA_WIDTH registered inputs, byte-interleaved across the
// sub-blocks and streamed out OUT_DATA_WIDTH bits per clock.
// Reset is synchronous (STD-RST-01); only control
// state and out_data are reset (datapath storage is gated by the control state).
module deinter_block #(
    parameter ROW_COL_WIDTH = 16,
    parameter SUB_BLOCKS    = 4,
    parameter DATA_WIDTH    = ROW_COL_WIDTH*ROW_COL_WIDTH,
    parameter OUT_DATA_WIDTH= 16,
    parameter WAIT_CYCLES   = 5
)(
    input  logic clk,
    input  logic rst_n,
    input  logic i_valid,
    input  logic [DATA_WIDTH-1:0] in_data,
    output logic [OUT_DATA_WIDTH-1:0] out_data
);

localparam NBYTES    = DATA_WIDTH/8;
localparam TOTAL     = SUB_BLOCKS*DATA_WIDTH;
localparam N_CYCLES  = TOTAL/OUT_DATA_WIDTH;
localparam NBW_OUT   = $clog2(N_CYCLES);
localparam NBW_SUB   = $clog2(SUB_BLOCKS);
// start_intra to the cycle that arms the sequencer: WAIT_CYCLES+3 stages
localparam CHAIN     = WAIT_CYCLES + 3;

logic [NBW_SUB-1:0]    counter_sub_blocks;
logic                  start_intra;
logic [CHAIN-1:0]      start_intra_ff;
logic                  enable_output;
logic                  active;
logic [NBW_OUT-1:0]    counter_output;

logic [DATA_WIDTH-1:0] in_data_reg [SUB_BLOCKS];
logic [TOTAL-1:0]      stream;
logic [TOTAL-1:0]      stream_perm;

assign enable_output = start_intra_ff[CHAIN-1];

// byte i of sub-block s lands at stream byte i*SUB_BLOCKS+s
always_comb begin
   for (int i = 0; i < NBYTES; i++)
      for (int s = 0; s < SUB_BLOCKS; s++)
         stream_perm[8*(i*SUB_BLOCKS+s) +: 8] = in_data_reg[s][8*i +: 8];
end

// input registration (storage, no reset)
always_ff @(posedge clk) begin
   if (i_valid)
      in_data_reg[counter_sub_blocks] <= in_data;
end

// control
always_ff @(posedge clk) begin
   if (!rst_n) begin
      counter_sub_blocks <= '0;
      start_intra        <= 1'b0;
      start_intra_ff     <= '0;
      active             <= 1'b0;
      counter_output     <= '0;
      out_data           <= '0;
   end
   else begin
      start_intra <= 1'b0;
      if (i_valid) begin
         if (counter_sub_blocks == NBW_SUB'(SUB_BLOCKS-1)) begin
            counter_sub_blocks <= '0;
            start_intra        <= 1'b1;
         end
         else
            counter_sub_blocks <= counter_sub_blocks + 1'b1;
      end

      start_intra_ff <= {start_intra_ff[CHAIN-2:0], start_intra};

      if (enable_output) begin
         active         <= 1'b1;
         counter_output <= '0;
      end
      else if (active) begin
         counter_output <= counter_output + 1'b1;
         if (counter_output == NBW_OUT'(N_CYCLES-1))
            active <= 1'b0;
      end

      out_data <= active ? stream[OUT_DATA_WIDTH-1:0] : '0;
   end
end

// rearranged stream: loaded when a group completes, shifted while outputting
always_ff @(posedge clk) begin
   if (start_intra)
      stream <= stream_perm;
   else if (active)
      stream <= stream >> OUT_DATA_WIDTH;
end

endmodule
