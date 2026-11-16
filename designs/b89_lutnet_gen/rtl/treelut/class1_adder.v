module class1_adder(input wire clk, input wire [73:0] i, output wire [7:0] o);

reg[7:0] o_reg;
assign o = o_reg;

reg [4:0] stage0_adder0;
reg [4:0] stage0_adder1;
reg [4:0] stage0_adder2;
reg [4:0] stage0_adder3;
reg [4:0] stage0_adder4;
reg [4:0] stage0_adder5;
reg [4:0] stage0_adder6;
reg [4:0] stage0_adder7;
reg [4:0] stage0_adder8;
reg [4:0] stage0_adder9;

always @(*) begin
	stage0_adder0 = i[3:0] + i[7:4];
	stage0_adder1 = i[10:8] + i[14:11];
	stage0_adder2 = i[18:15] + i[21:19];
	stage0_adder3 = i[24:22] + i[28:25];
	stage0_adder4 = i[32:29] + i[35:33];
	stage0_adder5 = i[39:36] + i[43:40];
	stage0_adder6 = i[46:44] + i[50:47];
	stage0_adder7 = i[54:51] + i[58:55];
	stage0_adder8 = i[61:59] + i[65:62];
	stage0_adder9 = i[69:66] + i[73:70];
end

reg [5:0] stage1_adder0;
reg [5:0] stage1_adder1;
reg [5:0] stage1_adder2;
reg [5:0] stage1_adder3;
reg [5:0] stage1_adder4;

always @(*) begin
	stage1_adder0 = stage0_adder0 + stage0_adder1;
	stage1_adder1 = stage0_adder2 + stage0_adder3;
	stage1_adder2 = stage0_adder4 + stage0_adder5;
	stage1_adder3 = stage0_adder6 + stage0_adder7;
	stage1_adder4 = stage0_adder8 + stage0_adder9;
end

reg [6:0] stage2_adder0;
reg [6:0] stage2_adder1;
reg [5:0] stage2_adder2;

always @(posedge clk) begin
	stage2_adder0 = stage1_adder0 + stage1_adder1;
	stage2_adder1 = stage1_adder2 + stage1_adder3;
	stage2_adder2 = stage1_adder4;
end

reg [7:0] stage3_adder0;
reg [5:0] stage3_adder1;

always @(*) begin
	stage3_adder0 = stage2_adder0 + stage2_adder1;
	stage3_adder1 = stage2_adder2;
end


always @(*) begin
o_reg = stage3_adder0 + stage3_adder1;
end

endmodule
