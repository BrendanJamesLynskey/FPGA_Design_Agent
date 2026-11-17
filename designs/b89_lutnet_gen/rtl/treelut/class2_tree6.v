module class2_tree6(input wire [183:0] i, output wire [2:0] o);

reg [2:0] o_reg;
assign o = o_reg;

always @(*) begin
	if(((~i[66]) & i[157] & i[91] & (~i[59])))
		o_reg = 0;
	else if((i[128] & i[183] & i[105] & i[59]) | (i[66] & i[157] & i[91] & (~i[59])))
		o_reg = 1;
	else if((i[95] & (~i[92]) & (~i[105]) & i[59]) | (i[142] & i[93] & (~i[91]) & (~i[59])))
		o_reg = 2;
	else if((i[163] & (~i[183]) & i[105] & i[59]) | (i[6] & i[92] & (~i[105]) & i[59]) | (i[117] & (~i[157]) & i[91] & (~i[59])) | ((~i[182]) & (~i[93]) & (~i[91]) & (~i[59])))
		o_reg = 3;
	else if(((~i[128]) & i[183] & i[105] & i[59]) | ((~i[6]) & i[92] & (~i[105]) & i[59]) | ((~i[142]) & i[93] & (~i[91]) & (~i[59])))
		o_reg = 4;
	else if(((~i[163]) & (~i[183]) & i[105] & i[59]))
		o_reg = 5;
	else
		o_reg = 6;
end

endmodule
