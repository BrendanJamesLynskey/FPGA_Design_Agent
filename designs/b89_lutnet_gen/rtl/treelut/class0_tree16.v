module class0_tree16(input wire [183:0] i, output wire [3:0] o);

reg [3:0] o_reg;
assign o = o_reg;

always @(*) begin
	if(((~i[37]) & i[143] & i[91] & (~i[20])))
		o_reg = 0;
	else if(((~i[97]) & i[119] & (~i[91]) & (~i[20])))
		o_reg = 1;
	else if((i[59] & (~i[143]) & i[91] & (~i[20])))
		o_reg = 2;
	else if(((~i[59]) & (~i[143]) & i[91] & (~i[20])))
		o_reg = 3;
	else if(((~i[111]) & (~i[72]) & i[124] & i[20]) | (i[73] & i[182] & (~i[124]) & i[20]) | (i[109] & (~i[182]) & (~i[124]) & i[20]) | ((~i[109]) & (~i[182]) & (~i[124]) & i[20]) | (i[97] & i[119] & (~i[91]) & (~i[20])) | (i[47] & (~i[119]) & (~i[91]) & (~i[20])))
		o_reg = 4;
	else if((i[92] & i[72] & i[124] & i[20]) | (i[37] & i[143] & i[91] & (~i[20])))
		o_reg = 5;
	else if(((~i[73]) & i[182] & (~i[124]) & i[20]))
		o_reg = 6;
	else if(((~i[92]) & i[72] & i[124] & i[20]))
		o_reg = 8;
	else if((i[111] & (~i[72]) & i[124] & i[20]))
		o_reg = 9;
	else
		o_reg = 11;
end

endmodule
