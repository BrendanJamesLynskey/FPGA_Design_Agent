module class2_tree0(input wire [183:0] i, output wire [3:0] o);

reg [3:0] o_reg;
assign o = o_reg;

always @(*) begin
	if((i[163] & (~i[60]) & i[91] & (~i[52])))
		o_reg = 0;
	else if((i[102] & i[60] & i[91] & (~i[52])))
		o_reg = 2;
	else if((i[102] & i[91] & i[11] & i[52]) | ((~i[163]) & (~i[60]) & i[91] & (~i[52])))
		o_reg = 3;
	else if((i[95] & (~i[92]) & (~i[11]) & i[52]) | (i[11] & i[93] & (~i[91]) & (~i[52])))
		o_reg = 4;
	else if(((~i[102]) & i[91] & i[11] & i[52]) | ((~i[102]) & i[60] & i[91] & (~i[52])))
		o_reg = 5;
	else if(((~i[182]) & (~i[91]) & i[11] & i[52]) | (i[105] & i[92] & (~i[11]) & i[52]) | ((~i[182]) & (~i[93]) & (~i[91]) & (~i[52])))
		o_reg = 6;
	else if((i[182] & (~i[91]) & i[11] & i[52]) | ((~i[11]) & i[93] & (~i[91]) & (~i[52])))
		o_reg = 7;
	else if(((~i[95]) & (~i[92]) & (~i[11]) & i[52]))
		o_reg = 8;
	else if(((~i[105]) & i[92] & (~i[11]) & i[52]))
		o_reg = 9;
	else
		o_reg = 10;
end

endmodule
