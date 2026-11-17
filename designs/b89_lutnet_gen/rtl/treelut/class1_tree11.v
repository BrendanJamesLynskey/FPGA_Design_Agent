module class1_tree11(input wire [183:0] i, output wire [3:0] o);

reg [3:0] o_reg;
assign o = o_reg;

always @(*) begin
	if(((~i[18]) & (~i[89]) & i[91]))
		o_reg = 0;
	else if((i[18] & (~i[89]) & i[91]) | ((~i[39]) & i[92] & (~i[91])) | ((~i[36]) & (~i[118]) & i[89] & i[91]))
		o_reg = 5;
	else if((i[151] & i[39] & i[92] & (~i[91])) | (i[94] & (~i[93]) & (~i[92]) & (~i[91])))
		o_reg = 7;
	else if(((~i[151]) & i[39] & i[92] & (~i[91])) | ((~i[94]) & (~i[93]) & (~i[92]) & (~i[91])))
		o_reg = 8;
	else if((i[111] & i[118] & i[89] & i[91]) | ((~i[111]) & i[118] & i[89] & i[91]) | (i[36] & (~i[118]) & i[89] & i[91]) | (i[175] & i[93] & (~i[92]) & (~i[91])))
		o_reg = 9;
	else
		o_reg = 13;
end

endmodule
