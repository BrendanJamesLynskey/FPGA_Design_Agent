module class2_tree18(input wire [183:0] i, output wire [3:0] o);

reg [3:0] o_reg;
assign o = o_reg;

always @(*) begin
	if((i[3] & (~i[117]) & (~i[73])) | (i[104] & (~i[93]) & (~i[119]) & i[73]) | (i[112] & i[91] & i[117] & (~i[73])) | (i[129] & (~i[91]) & i[117] & (~i[73])) | ((~i[92]) & (~i[3]) & (~i[117]) & (~i[73])))
		o_reg = 0;
	else if(((~i[29]) & i[93] & (~i[119]) & i[73]) | ((~i[112]) & i[91] & i[117] & (~i[73])))
		o_reg = 2;
	else if(((~i[104]) & (~i[93]) & (~i[119]) & i[73]) | ((~i[129]) & (~i[91]) & i[117] & (~i[73])))
		o_reg = 3;
	else if((i[183] & i[181] & i[119] & i[73]) | ((~i[183]) & i[181] & i[119] & i[73]))
		o_reg = 4;
	else if((i[29] & i[93] & (~i[119]) & i[73]))
		o_reg = 6;
	else if((i[52] & (~i[181]) & i[119] & i[73]))
		o_reg = 7;
	else
		o_reg = 11;
end

endmodule
