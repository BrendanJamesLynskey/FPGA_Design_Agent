module class0_tree12(input wire [183:0] i, output wire [2:0] o);

reg [2:0] o_reg;
assign o = o_reg;

always @(*) begin
	if(((~i[37]) & i[140] & i[91] & (~i[21])) | ((~i[46]) & (~i[44]) & (~i[91]) & (~i[21])))
		o_reg = 0;
	else if(((~i[119]) & (~i[113]) & (~i[167]) & i[21]))
		o_reg = 1;
	else if(((~i[60]) & i[113] & (~i[167]) & i[21]) | (i[59] & (~i[140]) & i[91] & (~i[21])))
		o_reg = 2;
	else if((i[119] & (~i[113]) & (~i[167]) & i[21]) | ((~i[59]) & (~i[140]) & i[91] & (~i[21])))
		o_reg = 3;
	else if(((~i[138]) & i[182] & i[167] & i[21]) | (i[109] & (~i[182]) & i[167] & i[21]) | (i[113] & i[44] & (~i[91]) & (~i[21])) | (i[46] & (~i[44]) & (~i[91]) & (~i[21])))
		o_reg = 4;
	else
		o_reg = 5;
end

endmodule
