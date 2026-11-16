module class0_tree1(input wire [183:0] i, output wire [3:0] o);

reg [3:0] o_reg;
assign o = o_reg;

always @(*) begin
	if(((~i[17]) & (~i[102]) & i[91] & (~i[9])))
		o_reg = 0;
	else if((i[17] & (~i[102]) & i[91] & (~i[9])))
		o_reg = 2;
	else if((i[183] & i[91] & (~i[99]) & i[9]) | ((~i[134]) & i[102] & i[91] & (~i[9])))
		o_reg = 3;
	else if((i[96] & (~i[92]) & i[99] & i[9]) | ((~i[104]) & i[93] & (~i[91]) & (~i[9])))
		o_reg = 4;
	else if((i[50] & i[92] & i[99] & i[9]) | ((~i[183]) & i[91] & (~i[99]) & i[9]) | (i[113] & (~i[91]) & (~i[99]) & i[9]))
		o_reg = 5;
	else if((i[104] & i[93] & (~i[91]) & (~i[9])) | (i[182] & (~i[93]) & (~i[91]) & (~i[9])))
		o_reg = 6;
	else if(((~i[50]) & i[92] & i[99] & i[9]) | ((~i[113]) & (~i[91]) & (~i[99]) & i[9]) | (i[134] & i[102] & i[91] & (~i[9])))
		o_reg = 7;
	else if(((~i[96]) & (~i[92]) & i[99] & i[9]))
		o_reg = 8;
	else
		o_reg = 9;
end

endmodule
