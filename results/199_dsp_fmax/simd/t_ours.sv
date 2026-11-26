module t_ours (input clk, input [47:0] a, input [47:0] b, output logic [47:0] y);
logic [47:0] ar, br;
(* use_dsp = "simd" *) logic [47:0] sum;
always_comb for (int k = 0; k < 4; k++) sum[12*k +: 12] = ar[12*k +: 12] + br[12*k +: 12];
always_ff @(posedge clk) begin ar <= a; br <= b; y <= sum; end
endmodule
