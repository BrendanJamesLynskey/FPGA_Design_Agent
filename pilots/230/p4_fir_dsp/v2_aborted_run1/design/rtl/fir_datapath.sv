// 32-tap symmetric FIR: 16 pre-add + multiply stages (DSP48E2), adder tree, round, >>>15, saturate.
// Free-running pipeline tagged with a valid bit; the only state is the 31-sample history, which
// shifts only when a sample is issued. One sample accepted per clock.
module fir_datapath (
    input  logic        clk,
    input  logic        rst,        // synchronous, active high: clears history and valid tags
    input  logic        in_valid,
    input  logic [15:0] x,
    output logic        out_valid,
    output logic [15:0] y,
    output logic        sat,
    output logic        pipe_busy   // any sample still in the pipeline
);
    // unique coefficients h[0..15] (data/coeffs.hex, symmetric)
    function automatic logic signed [15:0] coef(input integer k);
        case (k)
            0:  coef = 16'sh001f;
            1:  coef = 16'shffdb;
            2:  coef = 16'shffab;
            3:  coef = 16'sh0000;
            4:  coef = 16'sh00bd;
            5:  coef = 16'sh00aa;
            6:  coef = 16'shff0f;
            7:  coef = 16'shfde6;
            8:  coef = 16'sh0000;
            9:  coef = 16'sh03d5;
            10: coef = 16'sh032c;
            11: coef = 16'shfbb6;
            12: coef = 16'shf659;
            13: coef = 16'sh0000;
            14: coef = 16'sh18cc;
            default: coef = 16'sh2edb;
        endcase
    endfunction

    logic signed [15:0] d [0:30];       // d[j] = x[n-1-j]
    logic signed [15:0] sa [0:15];
    logic signed [15:0] sb [0:15];
    logic signed [16:0] ad [0:15];
    (* use_dsp = "yes" *) logic signed [32:0] m [0:15];
    logic signed [37:0] t1 [0:7];
    logic signed [37:0] t2 [0:3];
    logic signed [37:0] t3 [0:1];
    logic signed [37:0] t4;
    logic signed [37:0] acc;
    logic [8:0]         v;

    wire signed [15:0] xs = x;
    wire signed [37:0] sh = acc >>> 15;

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int j = 0; j < 31; j++) d[j] <= 16'sd0;
        end else if (in_valid) begin
            d[0] <= xs;
            for (int j = 1; j < 31; j++) d[j] <= d[j-1];
        end
    end

    always_ff @(posedge clk) begin
        sa[0] <= xs;
        sb[0] <= d[30];
        for (int k = 1; k < 16; k++) begin
            sa[k] <= d[k-1];
            sb[k] <= d[30-k];
        end
        for (int k = 0; k < 16; k++) begin
            ad[k] <= 17'(sa[k]) + 17'(sb[k]);
            m[k]  <= ad[k] * coef(k);
        end
        for (int i = 0; i < 8; i++) t1[i] <= 38'(m[2*i]) + 38'(m[2*i+1]);
        for (int i = 0; i < 4; i++) t2[i] <= t1[2*i] + t1[2*i+1];
        for (int i = 0; i < 2; i++) t3[i] <= t2[2*i] + t2[2*i+1];
        t4  <= t3[0] + t3[1];
        acc <= t4 + 38'sd16384;
        if (sh > 38'sd32767) begin
            y   <= 16'h7fff;
            sat <= 1'b1;
        end else if (sh < -38'sd32768) begin
            y   <= 16'h8000;
            sat <= 1'b1;
        end else begin
            y   <= sh[15:0];
            sat <= 1'b0;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) v <= 9'd0;
        else     v <= {v[7:0], in_valid};
    end

    assign out_valid = v[8];
    assign pipe_busy = |v;
endmodule
