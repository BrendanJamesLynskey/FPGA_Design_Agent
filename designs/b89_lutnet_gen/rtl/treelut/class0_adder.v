module class0_adder(input wire clk, input wire [70:0] i, output wire [7:0] o);

reg[7:0] o_reg;
assign o = o_reg;

reg [5:0] stage0_adder0;
reg [4:0] stage0_adder1;
reg [3:0] stage0_adder2;
reg [4:0] stage0_adder3;
reg [3:0] stage0_adder4;
reg [4:0] stage0_adder5;
reg [3:0] stage0_adder6;
reg [4:0] stage0_adder7;
reg [4:0] stage0_adder8;
reg [4:0] stage0_adder9;
reg [3:0] stage0_adder10;

always @(*) begin
	stage0_adder0 = 5'd23 + i[3:0];
	stage0_adder1 = i[7:4] + i[10:8];
	stage0_adder2 = i[13:11] + i[16:14];
	stage0_adder3 = i[19:17] + i[23:20];
	stage0_adder4 = i[26:24] + i[29:27];
	stage0_adder5 = i[32:30] + i[36:33];
	stage0_adder6 = i[39:37] + i[42:40];
	stage0_adder7 = i[46:43] + i[50:47];
	stage0_adder8 = i[54:51] + i[58:55];
	stage0_adder9 = i[62:59] + i[66:63];
	stage0_adder10 = i[70:67];
end

reg [6:0] stage1_adder0;
reg [5:0] stage1_adder1;
reg [5:0] stage1_adder2;
reg [5:0] stage1_adder3;
reg [5:0] stage1_adder4;
reg [3:0] stage1_adder5;

always @(*) begin
	stage1_adder0 = stage0_adder0 + stage0_adder1;
	stage1_adder1 = stage0_adder2 + stage0_adder3;
	stage1_adder2 = stage0_adder4 + stage0_adder5;
	stage1_adder3 = stage0_adder6 + stage0_adder7;
	stage1_adder4 = stage0_adder8 + stage0_adder9;
	stage1_adder5 = stage0_adder10;
end

reg [7:0] stage2_adder0;
reg [6:0] stage2_adder1;
reg [6:0] stage2_adder2;

always @(posedge clk) begin
	stage2_adder0 = stage1_adder0 + stage1_adder1;
	stage2_adder1 = stage1_adder2 + stage1_adder3;
	stage2_adder2 = stage1_adder4 + stage1_adder5;
end

reg [8:0] stage3_adder0;
reg [6:0] stage3_adder1;

always @(*) begin
	stage3_adder0 = stage2_adder0 + stage2_adder1;
	stage3_adder1 = stage2_adder2;
end


always @(*) begin
o_reg = stage3_adder0 + stage3_adder1;
end

endmodule
