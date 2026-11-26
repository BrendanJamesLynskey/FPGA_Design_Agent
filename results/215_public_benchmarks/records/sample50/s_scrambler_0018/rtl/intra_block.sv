// intra_block: spec says it maps in_data_reg[k] to out_data_intra_block[k]
// unchanged (the reference model treats it as a pass-through).
module intra_block #(
    parameter ROW_COL_WIDTH = 16,
    parameter DATA_WIDTH    = ROW_COL_WIDTH*ROW_COL_WIDTH
)(
    input  logic [DATA_WIDTH-1:0] in_data,
    output logic [DATA_WIDTH-1:0] out_data
);
    assign out_data = in_data;
endmodule
