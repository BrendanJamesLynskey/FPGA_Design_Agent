module class1_tree15(input wire [183:0] i, output wire [3:0] o);

reg [3:0] o_reg;
assign o = o_reg;

always @(*) begin
	if(((~i[89]) & i[91]))
		o_reg = 0;
	else if((i[47] & (~i[117]) & i[92] & (~i[91])))
		o_reg = 2;
	else if((i[179] & i[46] & i[89] & i[91]) | (i[56] & i[117] & i[92] & (~i[91])) | ((~i[56]) & i[117] & i[92] & (~i[91])) | ((~i[47]) & (~i[117]) & i[92] & (~i[91])) | (i[94] & (~i[93]) & (~i[92]) & (~i[91])))
		o_reg = 4;
	else if((i[111] & (~i[46]) & i[89] & i[91]) | ((~i[111]) & (~i[46]) & i[89] & i[91]) | (i[9] & i[93] & (~i[92]) & (~i[91])) | ((~i[94]) & (~i[93]) & (~i[92]) & (~i[91])))
		o_reg = 5;
	else if(((~i[9]) & i[93] & (~i[92]) & (~i[91])))
		o_reg = 6;
	else
		o_reg = 11;
end

endmodule
