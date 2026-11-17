module class1_tree0(input wire [183:0] i, output wire [3:0] o);

reg [3:0] o_reg;
assign o = o_reg;

always @(*) begin
	if(((~i[120]) & i[148] & i[92] & (~i[91])) | ((~i[66]) & (~i[148]) & i[92] & (~i[91])) | (i[94] & (~i[93]) & (~i[92]) & (~i[91])))
		o_reg = 0;
	else if((i[66] & (~i[148]) & i[92] & (~i[91])) | ((~i[94]) & (~i[93]) & (~i[92]) & (~i[91])))
		o_reg = 1;
	else if((i[120] & i[148] & i[92] & (~i[91])))
		o_reg = 3;
	else if((i[137] & i[3] & i[7] & i[91]) | (i[53] & i[93] & (~i[92]) & (~i[91])))
		o_reg = 4;
	else if(((~i[137]) & i[3] & i[7] & i[91]) | ((~i[112]) & (~i[3]) & i[7] & i[91]) | (i[48] & i[52] & (~i[7]) & i[91]))
		o_reg = 5;
	else if((i[112] & (~i[3]) & i[7] & i[91]) | ((~i[48]) & i[52] & (~i[7]) & i[91]) | ((~i[53]) & i[93] & (~i[92]) & (~i[91])))
		o_reg = 6;
	else if((i[12] & (~i[52]) & (~i[7]) & i[91]))
		o_reg = 8;
	else
		o_reg = 10;
end

endmodule
