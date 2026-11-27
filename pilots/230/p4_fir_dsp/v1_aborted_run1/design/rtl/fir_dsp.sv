// 32-tap symmetric FIR (Q1.15): pre-adder, 16 multipliers, adder tree, round, saturate. One sample per clock.
module fir_dsp (
    input  logic        clk,
    input  logic        clr,        // synchronous: zero history, drop in-flight results
    input  logic        in_valid,
    input  logic [15:0] in_x,
    output logic        out_valid,
    output logic [15:0] out_y,
    output logic        out_sat
);
    // h[0..15] (h[k] = h[31-k]), from data/coeffs.hex
    function automatic logic signed [15:0] coef(input int k);
        case (k)
            0:  coef = 16'h001f;
            1:  coef = 16'hffdb;
            2:  coef = 16'hffab;
            3:  coef = 16'h0000;
            4:  coef = 16'h00bd;
            5:  coef = 16'h00aa;
            6:  coef = 16'hff0f;
            7:  coef = 16'hfde6;
            8:  coef = 16'h0000;
            9:  coef = 16'h03d5;
            10: coef = 16'h032c;
            11: coef = 16'hfbb6;
            12: coef = 16'hf659;
            13: coef = 16'h0000;
            14: coef = 16'h18cc;
            default: coef = 16'h2edb;
        endcase
    endfunction

    logic signed [15:0] hist [32];
    logic signed [16:0] pa [16];
    logic signed [32:0] pr [16];
    logic signed [34:0] s4 [4];
    logic signed [35:0] s5 [2];
    logic signed [37:0] acc;
    logic [5:0]         v;

    always_ff @(posedge clk) begin
        v <= {v[4:0], in_valid};
        if (in_valid) begin
            hist[0] <= $signed(in_x);
            for (int i = 1; i < 32; i++) hist[i] <= hist[i-1];
        end
        if (clr) begin
            v <= '0;
            for (int i = 0; i < 32; i++) hist[i] <= '0;
        end
    end

    always_ff @(posedge clk) begin
        for (int k = 0; k < 16; k++) begin
            pa[k] <= 17'(hist[k]) + 17'(hist[31-k]);
            pr[k] <= pa[k] * coef(k);
        end
        for (int g = 0; g < 4; g++)
            s4[g] <= 35'(pr[4*g]) + 35'(pr[4*g+1]) + 35'(pr[4*g+2]) + 35'(pr[4*g+3]);
        s5[0] <= 36'(s4[0]) + 36'(s4[1]);
        s5[1] <= 36'(s4[2]) + 36'(s4[3]);
        acc   <= 38'(s5[0]) + 38'(s5[1]) + 38'sd16384;
    end

    wire signed [22:0] y = 23'(acc >>> 15);
    always_ff @(posedge clk) begin
        out_valid <= v[5] && !clr;
        if (y > 23'sd32767)       begin out_y <= 16'h7fff; out_sat <= 1'b1; end
        else if (y < -23'sd32768) begin out_y <= 16'h8000; out_sat <= 1'b1; end
        else                      begin out_y <= y[15:0];  out_sat <= 1'b0; end
        if (clr) out_valid <= 1'b0;
    end
endmodule
