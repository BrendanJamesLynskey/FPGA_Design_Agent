module class0_tree0(input wire [183:0] i, output wire [3:0] o);

reg [3:0] o_reg;
assign o = o_reg;

always @(*) begin
	if(((~i[15]) & (~i[102]) & i[91] & (~i[8])))
		o_reg = 0;
	else if((i[15] & (~i[102]) & i[91] & (~i[8])))
		o_reg = 2;
	else if((i[95] & (~i[92]) & (~i[57]) & i[8]) | ((~i[133]) & i[102] & i[91] & (~i[8])))
		o_reg = 3;
	else if((i[91] & i[183] & i[57] & i[8]))
		o_reg = 4;
	else if(((~i[3]) & (~i[183]) & i[57] & i[8]) | ((~i[104]) & i[93] & (~i[91]) & (~i[8])) | (i[111] & (~i[93]) & (~i[91]) & (~i[8])))
		o_reg = 5;
	else if(((~i[91]) & i[183] & i[57] & i[8]))
		o_reg = 6;
	else if((i[3] & (~i[183]) & i[57] & i[8]) | ((~i[95]) & (~i[92]) & (~i[57]) & i[8]) | (i[104] & i[93] & (~i[91]) & (~i[8])))
		o_reg = 7;
	else if(((~i[134]) & i[92] & (~i[57]) & i[8]) | (i[133] & i[102] & i[91] & (~i[8])))
		o_reg = 8;
	else if(((~i[111]) & (~i[93]) & (~i[91]) & (~i[8])))
		o_reg = 9;
	else
		o_reg = 11;
end

endmodule
