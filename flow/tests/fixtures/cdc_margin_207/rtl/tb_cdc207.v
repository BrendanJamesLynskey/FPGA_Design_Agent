// tb_cdc207: functional check of cdc207_top (BAD=0) in Icarus: FIFO order, handshake words, config bus, pulse count,
// reset release. Clocks 100 MHz and 156.25 MHz with an irrational-ish phase. Zero-delay simulation: it checks the
// protocols, not metastability (that is flow/cdc_inject.py's job).
`timescale 1ns/1ps
module tb_cdc207;
    reg clk_a = 0, clk_b = 0;
    always #5.0 clk_a = ~clk_a;
    initial begin #1.37; forever #3.2 clk_b = ~clk_b; end
    reg rst_a = 1, rst_b = 1, arst_n = 0;
    reg lvl_in_a = 0, pls_in_a = 0, wr_a = 0, rd_b = 0, hs_go_a = 0, cfg_we_a = 0;
    reg [7:0] din_a = 0; reg [15:0] hs_data_a = 0, cfg_in_a = 0;
    wire [7:0] lvl_cnt_b, pls_cnt_b, dout_b, rcnt_b; wire full_a, empty_b, hs_busy_a, hs_valid_b;
    wire [15:0] hs_data_b, cfg_b; wire [31:0] fa_acc, fb_acc;
    cdc207_top #(.BAD(0)) dut (.clk_a(clk_a), .clk_b(clk_b), .rst_a(rst_a), .rst_b(rst_b), .arst_n(arst_n),
        .lvl_in_a(lvl_in_a), .pls_in_a(pls_in_a), .lvl_cnt_b(lvl_cnt_b), .pls_cnt_b(pls_cnt_b),
        .din_a(din_a), .wr_a(wr_a), .full_a(full_a), .rd_b(rd_b), .dout_b(dout_b), .empty_b(empty_b),
        .hs_data_a(hs_data_a), .hs_go_a(hs_go_a), .hs_busy_a(hs_busy_a), .hs_data_b(hs_data_b), .hs_valid_b(hs_valid_b),
        .cfg_in_a(cfg_in_a), .cfg_we_a(cfg_we_a), .cfg_b(cfg_b), .rcnt_b(rcnt_b),
        .fa_x(16'd3), .fa_y(16'd5), .fa_acc(fa_acc), .fb_x(16'd7), .fb_y(16'd9), .fb_acc(fb_acc));
    integer errors = 0, nw = 0, nr = 0, nhs = 0, i; reg seen_full = 0;
    reg [7:0] expect_rd = 0;
    // FIFO reader: read whenever not empty; data appears one cycle after the read
    reg rd_d = 0;
    always @(posedge clk_b) begin
        rd_d <= rd_b && !empty_b;
        if (rd_d) begin
            if (dout_b !== expect_rd) begin errors = errors + 1; $display("FIFO: got %0d want %0d", dout_b, expect_rd); end
            expect_rd <= expect_rd + 1; nr = nr + 1;
        end
    end
    always @(posedge clk_b) if (hs_valid_b) begin
        if (hs_data_b !== 16'hA000 + nhs) begin errors = errors + 1; $display("HS: got %h", hs_data_b); end
        nhs = nhs + 1;
    end
    initial begin #200000; $display("FAIL tb_cdc207: timeout nw=%0d nr=%0d nhs=%0d full=%b empty=%b busy=%b", nw, nr, nhs, full_a, empty_b, hs_busy_a); $finish; end
    initial begin
        repeat (4) @(posedge clk_a); rst_a = 0; arst_n = 1;
        @(posedge clk_b); rst_b = 0;
        // FIFO: 300 writes (wraps the 128-deep memory twice), reader on and off
        rd_b = 1;
        while (nw < 300) begin
            @(posedge clk_a);
            if (wr_a && !full_a) begin nw = nw + 1; din_a <= din_a + 1; end
            wr_a <= ($random & 3) != 0;
            if (nw == 100 && !seen_full) rd_b = 0;   // stop reading until the FIFO fills, once
            if (full_a) begin seen_full = 1; rd_b = 1; end
        end
        wr_a <= 0; rd_b = 1;   // same time step as the last counted edge: no extra write
        // handshake: 6 words
        for (i = 0; i < 6; i = i + 1) begin
            @(posedge clk_a); while (hs_busy_a) @(posedge clk_a);
            hs_data_a <= 16'hA000 + i; hs_go_a <= 1; @(posedge clk_a); hs_go_a <= 0;
        end
        // config: two writes, far apart
        @(posedge clk_a); cfg_in_a <= 16'h1234; cfg_we_a <= 1; @(posedge clk_a); cfg_we_a <= 0;
        repeat (20) @(posedge clk_a);
        @(posedge clk_a); cfg_in_a <= 16'hBEEF; cfg_we_a <= 1; @(posedge clk_a); cfg_we_a <= 0;
        // pulses: 10 single-cycle pulses 8 cycles apart
        for (i = 0; i < 10; i = i + 1) begin @(posedge clk_a); pls_in_a <= 1; @(posedge clk_a); pls_in_a <= 0; repeat (6) @(posedge clk_a); end
        repeat (60) @(posedge clk_a);
        if (nr != 300) begin errors = errors + 1; $display("FIFO: read %0d of 300", nr); end
        if (nhs != 6) begin errors = errors + 1; $display("HS: %0d of 6 words", nhs); end
        if (cfg_b !== 16'hBEEF) begin errors = errors + 1; $display("CFG: %h", cfg_b); end
        if (pls_cnt_b !== 8'd10) begin errors = errors + 1; $display("PULSE: %0d of 10", pls_cnt_b); end
        if (rcnt_b == 0) begin errors = errors + 1; $display("RESET: not released"); end
        if (errors == 0) $display("PASS tb_cdc207: 300 FIFO words, 6 handshake words, config, 10 pulses, reset release");
        else $display("FAIL tb_cdc207: %0d errors", errors);
        $finish;
    end
endmodule
