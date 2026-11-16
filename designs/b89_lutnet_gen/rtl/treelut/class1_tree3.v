module class1_tree3(input wire [183:0] i, output wire [3:0] o);

reg [3:0] o_reg;
assign o = o_reg;

always @(*) begin
	if(((~i[87]) & i[6] & i[91]))
		o_reg = 0;
	else if(((~i[174]) & i[58] & (~i[6]) & i[91]) | (i[117] & i[48] & i[92] & (~i[91])) | ((~i[117]) & i[48] & i[92] & (~i[91])) | (i[6] & (~i[48]) & i[92] & (~i[91])) | ((~i[6]) & (~i[48]) & i[92] & (~i[91])) | (i[94] & (~i[93]) & (~i[92]) & (~i[91])))
		o_reg = 2;
	else if(((~i[94]) & (~i[93]) & (~i[92]) & (~i[91])))
		o_reg = 3;
	else if((i[3] & i[87] & i[6] & i[91]) | (i[50] & i[93] & (~i[92]) & (~i[91])))
		o_reg = 5;
	else if(((~i[3]) & i[87] & i[6] & i[91]) | (i[174] & i[58] & (~i[6]) & i[91]) | ((~i[50]) & i[93] & (~i[92]) & (~i[91])))
		o_reg = 6;
	else if((i[21] & (~i[58]) & (~i[6]) & i[91]))
		o_reg = 7;
	else
		o_reg = 8;
end

endmodule
