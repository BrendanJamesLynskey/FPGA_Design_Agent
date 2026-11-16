module class1_tree2(input wire [183:0] i, output wire [2:0] o);

reg [2:0] o_reg;
assign o = o_reg;

always @(*) begin
	if(((~i[85]) & i[3] & i[6] & i[91]))
		o_reg = 0;
	else if(((~i[0]) & i[55] & i[92] & (~i[91])) | (i[115] & (~i[55]) & i[92] & (~i[91])) | (i[94] & (~i[93]) & (~i[92]) & (~i[91])))
		o_reg = 1;
	else if((i[0] & i[55] & i[92] & (~i[91])) | ((~i[115]) & (~i[55]) & i[92] & (~i[91])) | ((~i[94]) & (~i[93]) & (~i[92]) & (~i[91])))
		o_reg = 2;
	else if(((~i[169]) & i[50] & (~i[6]) & i[91]))
		o_reg = 3;
	else if((i[131] & (~i[3]) & i[6] & i[91]) | (i[18] & i[93] & (~i[92]) & (~i[91])))
		o_reg = 4;
	else if((i[85] & i[3] & i[6] & i[91]) | ((~i[131]) & (~i[3]) & i[6] & i[91]) | (i[169] & i[50] & (~i[6]) & i[91]))
		o_reg = 5;
	else if((i[12] & (~i[50]) & (~i[6]) & i[91]) | ((~i[18]) & i[93] & (~i[92]) & (~i[91])))
		o_reg = 6;
	else
		o_reg = 7;
end

endmodule
