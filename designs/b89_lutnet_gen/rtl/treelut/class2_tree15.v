module class2_tree15(input wire [183:0] i, output wire [2:0] o);

reg [2:0] o_reg;
assign o = o_reg;

always @(*) begin
	if((i[113] & (~i[98]) & (~i[91]) & (~i[64])))
		o_reg = 0;
	else if(((~i[78]) & (~i[3]) & i[91] & (~i[64])) | ((~i[85]) & i[98] & (~i[91]) & (~i[64])))
		o_reg = 1;
	else if(((~i[69]) & i[3] & i[91] & (~i[64])))
		o_reg = 2;
	else if((i[69] & i[3] & i[91] & (~i[64])))
		o_reg = 3;
	else if(((~i[58]) & i[117] & i[153] & i[64]) | (i[119] & (~i[117]) & i[153] & i[64]) | (i[5] & (~i[177]) & (~i[153]) & i[64]) | (i[78] & (~i[3]) & i[91] & (~i[64])))
		o_reg = 4;
	else if((i[58] & i[117] & i[153] & i[64]) | (i[119] & i[177] & (~i[153]) & i[64]) | (i[85] & i[98] & (~i[91]) & (~i[64])) | ((~i[113]) & (~i[98]) & (~i[91]) & (~i[64])))
		o_reg = 5;
	else if(((~i[119]) & (~i[117]) & i[153] & i[64]))
		o_reg = 6;
	else
		o_reg = 7;
end

endmodule
