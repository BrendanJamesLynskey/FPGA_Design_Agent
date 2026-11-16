module class2_tree4(input wire [183:0] i, output wire [2:0] o);

reg [2:0] o_reg;
assign o = o_reg;

always @(*) begin
	if(((~i[63]) & i[159] & i[91] & (~i[58])))
		o_reg = 0;
	else if((i[63] & i[159] & i[91] & (~i[58])) | (i[130] & i[93] & (~i[91]) & (~i[58])))
		o_reg = 1;
	else if(((~i[50]) & i[91] & i[103] & i[58]) | ((~i[65]) & (~i[159]) & i[91] & (~i[58])))
		o_reg = 2;
	else if((i[50] & i[91] & i[103] & i[58]) | ((~i[130]) & i[93] & (~i[91]) & (~i[58])))
		o_reg = 3;
	else if((i[111] & (~i[91]) & i[103] & i[58]) | ((~i[111]) & (~i[91]) & i[103] & i[58]) | (i[161] & i[31] & (~i[103]) & i[58]) | (i[65] & (~i[159]) & i[91] & (~i[58])) | ((~i[94]) & (~i[93]) & (~i[91]) & (~i[58])))
		o_reg = 4;
	else if(((~i[161]) & i[31] & (~i[103]) & i[58]))
		o_reg = 5;
	else if((i[183] & (~i[31]) & (~i[103]) & i[58]))
		o_reg = 6;
	else
		o_reg = 7;
end

endmodule
