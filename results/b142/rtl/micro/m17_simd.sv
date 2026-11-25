// m17_simd: four independent 12-bit adds in one DSP48E2 (SIMD, use_dsp = "simd").
module m17_simd (input logic clk, input logic [47:0] a, b, output logic [47:0] s);
    logic [47:0] aq, bq;
    (* use_dsp = "simd" *) logic [47:0] r;
    always_ff @(posedge clk) begin
        aq <= a; bq <= b;
        s <= r;
    end
    always_comb begin
        for (int i = 0; i < 4; i++) r[12*i +: 12] = aq[12*i +: 12] + bq[12*i +: 12];
    end
endmodule
