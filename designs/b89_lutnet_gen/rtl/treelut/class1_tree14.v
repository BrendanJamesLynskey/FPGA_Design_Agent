module class1_tree14(input wire [183:0] i, output wire [3:0] o);

reg [3:0] o_reg;
assign o = o_reg;

always @(*) begin
	if(((~i[18]) & (~i[89]) & i[91]))
		o_reg = 0;
	else if((i[18] & (~i[89]) & i[91]))
		o_reg = 4;
	else if((i[96] & (~i[95]) & (~i[92]) & (~i[91])))
		o_reg = 5;
	else if(((~i[177]) & (~i[47]) & i[89] & i[91]) | (i[13] & (~i[113]) & i[92] & (~i[91])))
		o_reg = 6;
	else if((i[15] & i[47] & i[89] & i[91]) | ((~i[15]) & i[47] & i[89] & i[91]) | (i[177] & (~i[47]) & i[89] & i[91]) | (i[159] & i[113] & i[92] & (~i[91])) | ((~i[159]) & i[113] & i[92] & (~i[91])) | ((~i[13]) & (~i[113]) & i[92] & (~i[91])) | (i[94] & i[95] & (~i[92]) & (~i[91])) | ((~i[96]) & (~i[95]) & (~i[92]) & (~i[91])))
		o_reg = 7;
	else
		o_reg = 8;
end

endmodule
