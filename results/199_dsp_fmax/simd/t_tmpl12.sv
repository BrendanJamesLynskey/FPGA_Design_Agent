(* use_dsp = "simd" *)
module t_tmpl12 (input clk, input [11:0] a [3:0], input [11:0] b [3:0], output logic [11:0] out [3:0]);
integer i;
logic [11:0] a_r [3:0];
logic [11:0] b_r [3:0];
always @(posedge clk) begin
 for (i=0;i<4;i=i+1) begin a_r[i] <= a[i]; b_r[i] <= b[i]; out[i] <= a_r[i] + b_r[i]; end
end
endmodule
