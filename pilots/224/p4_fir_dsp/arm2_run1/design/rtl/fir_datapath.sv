// 32-tap symmetric FIR at clk_dp: one sample per cycle, 16 pre-adders, 16 DSP multiplies,
// adder tree, round (+0x4000), shift 15, saturate to 16 bits; run control and counters.
// Pipeline (v[i] is high in the cycle the sample is at stage i+1 after accept):
//   hist -> pre-add -> mult (M) -> prod (P) -> sum8 -> sum4 -> sum2 -> total+round -> shift/sat
module fir_datapath (
    input  logic        clk,
    input  logic        rst,        // active high, synchronous to clk
    input  logic        run,        // one-cycle pulse
    input  logic        clr,        // one-cycle pulse
    // input FIFO (first word fall through)
    output logic        in_rd_en,
    input  logic [15:0] in_dout,
    input  logic        in_empty,
    input  logic [11:0] in_count,
    // output FIFO
    output logic        out_wr_en,
    output logic [15:0] out_din,
    input  logic [11:0] out_count,
    output logic        out_rst,    // reset request for the output FIFO (reset and CLEAR)
    // status
    output logic        busy,
    output logic [31:0] sat_cnt,
    output logic [31:0] done_cnt
);
    function automatic logic signed [15:0] coef(input int k);
        case (k)
            0: coef = 16'h001f;  1: coef = 16'hffdb;  2: coef = 16'hffab;  3: coef = 16'h0000;
            4: coef = 16'h00bd;  5: coef = 16'h00aa;  6: coef = 16'hff0f;  7: coef = 16'hfde6;
            8: coef = 16'h0000;  9: coef = 16'h03d5; 10: coef = 16'h032c; 11: coef = 16'hfbb6;
            12: coef = 16'hf659; 13: coef = 16'h0000; 14: coef = 16'h18cc; default: coef = 16'h2edb;
        endcase
    endfunction

    localparam int LAT = 9;   // accept -> out_wr_en

    // ---------------- run control ----------------
    logic            running;
    logic [10:0]     remaining;
    logic [6:0]      stretch;
    logic [LAT-1:0]  v;
    logic [11:0]     room, n_cand, n_r;
    logic [6:0]      rcnt;
    logic            out_sat;

    assign room   = (out_count >= 12'd1024) ? 12'd0 : (12'd1024 - out_count);
    assign n_cand = (in_count < room) ? in_count : room;

    wire accept = running && (remaining != 11'd0) && !in_empty;
    assign in_rd_en  = accept;
    assign out_wr_en = v[LAT-1];

    always_ff @(posedge clk) begin
        n_r <= n_cand;
        busy <= running || (stretch != 7'd0);
        out_rst <= rst || clr || (rcnt != 7'd0);
        if (rst) rcnt <= 7'd0;
        else if (clr) rcnt <= 7'd64;
        else if (rcnt != 7'd0) rcnt <= rcnt - 7'd1;
        if (rst || clr) begin
            running <= 1'b0; remaining <= '0; v <= '0; stretch <= '0;
            sat_cnt <= '0; done_cnt <= '0;
        end else begin
            v <= {v[LAT-2:0], accept};
            if (run && !running && n_r != 12'd0 && rcnt == 7'd0) begin
                running <= 1'b1; remaining <= n_r[10:0]; stretch <= 7'd64;
            end
            if (accept) remaining <= remaining - 11'd1;
            if (running && remaining == 11'd0 && v == '0) running <= 1'b0;
            if (running) stretch <= 7'd64;
            else if (stretch != 7'd0) stretch <= stretch - 7'd1;
            if (v[LAT-1]) begin
                done_cnt <= done_cnt + 32'd1;
                if (out_sat) sat_cnt <= sat_cnt + 32'd1;
            end
        end
    end

    // ---------------- datapath ----------------
    logic [15:0] hist [0:31];
    always_ff @(posedge clk) begin
        if (rst || clr) begin
            for (int k = 0; k < 32; k++) hist[k] <= '0;
        end else if (accept) begin
            hist[0] <= in_dout;
            for (int k = 1; k < 32; k++) hist[k] <= hist[k-1];
        end
    end

    // samples are taken as unsigned 16-bit words (as the reference model does)
    logic signed [17:0] pa [0:15];
    logic signed [33:0] pm [0:15];
    logic signed [33:0] prod [0:15];
    logic signed [39:0] s1 [0:7];
    logic signed [39:0] s2 [0:3];
    logic signed [39:0] s3 [0:1];
    /* verilator lint_off UNUSEDSIGNAL */
    logic signed [39:0] total;
    /* verilator lint_on UNUSEDSIGNAL */

    // coefficient registers kept (dont_touch) so that all 16 multipliers, including the
    // zero-coefficient taps, stay as DSP blocks as the architecture specifies
    /* verilator lint_off PROCASSINIT */
    (* dont_touch = "true" *) logic signed [15:0] cr [0:15];
    /* verilator lint_on PROCASSINIT */
    for (genvar g = 0; g < 16; g++) begin : g_cr
        initial cr[g] = coef(g);
        always_ff @(posedge clk) cr[g] <= cr[g];
    end

    always_ff @(posedge clk) begin
        for (int k = 0; k < 16; k++) begin
            pa[k]   <= $signed({2'b00, hist[k]}) + $signed({2'b00, hist[31-k]});
            pm[k]   <= pa[k] * cr[k];
            prod[k] <= pm[k];
        end
        for (int i = 0; i < 8; i++) s1[i] <= 40'(prod[2*i]) + 40'(prod[2*i+1]);
        for (int i = 0; i < 4; i++) s2[i] <= s1[2*i] + s1[2*i+1];
        for (int i = 0; i < 2; i++) s3[i] <= s2[2*i] + s2[2*i+1];
        total <= s3[0] + s3[1] + 40'sd16384;
    end

    wire [24:0] y   = total[39:15];
    wire        sat = (y[24:15] != 10'h000) && (y[24:15] != 10'h3ff);
    always_ff @(posedge clk) begin
        out_sat <= sat;
        out_din <= sat ? (y[24] ? 16'h8000 : 16'h7fff) : y[15:0];
    end
endmodule
