`timescale 1ns/1ps
// tb_rm_latency.sv (brief 96C, addendum 2): how many core clocks a frame's start block spends in rate_match, from the clock edge that writes it to the clock edge at
// which it is on the output, as a function of the phase between the write clock and the read clock (PH_PS: the read clock lags the write clock by that many ps).
// Self-contained (no cocotb): idle blocks 32 clocks in 33 (the PCS's cadence), a nine-block frame every 200 blocks; prints one line per frame, "LAT <phase ps> <block> <ps>",
// and a summary. The same file runs on the Icarus stand-in of xpm_fifo_async (flow/cdc_models) and on AMD's own macro in xsim: the difference is the point of it.
module tb_rm_latency #(
    parameter int PH_PS = 0,
    parameter int FRAMES = 40,
    parameter int IMPL = 0,        // brief 96E: 0 = rate_match (AMD's xpm_fifo_async), 1 = rate_match_gp (own gray-pointer buffer)
    parameter int HI = 4
);
    localparam real T = 6.206;                 // ns, 161.1328125 MHz
    logic wclk = 1'b0, rclk = 1'b0;
    logic wrst = 1'b1, rrst = 1'b1, w_v = 1'b0, w_lock = 1'b0;
    logic [63:0] w_d = 64'h0707070707070707;
    logic [7:0]  w_c = 8'hFF;
    logic        r_v, r_lock;
    logic [63:0] r_d;
    logic [7:0]  r_c;
    logic [31:0] n_ovf, n_wr, n_ins, n_del, n_stall, n_out, n_drain, fill_min, fill_max;
    always #(T / 2.0) wclk = ~wclk;
    initial begin #(PH_PS / 1000.0); forever #(T / 2.0) rclk = ~rclk; end
    if (IMPL == 0) begin : g_m
        rate_match #(.HI(HI)) u (.wclk, .wrst, .w_v, .w_d, .w_c, .w_os(1'b0), .w_lock, .clr_w(1'b0), .n_ovf, .n_wr,
            .rclk, .rrst, .clr_r(1'b0), .r_v, .r_d, .r_c, .r_lock, .n_ins, .n_del, .n_stall, .n_out, .n_drain, .fill_min, .fill_max);
    end else begin : g_m
        rate_match_gp #(.HI(HI)) u (.wclk, .wrst, .w_v, .w_d, .w_c, .w_os(1'b0), .w_lock, .clr_w(1'b0), .n_ovf, .n_wr,
            .rclk, .rrst, .clr_r(1'b0), .r_v, .r_d, .r_c, .r_lock, .n_ins, .n_del, .n_stall, .n_out, .n_drain, .fill_min, .fill_max);
    end
    // write side: block k of the stream
    int unsigned k = 0, nf = 0;
    real tw [0:FRAMES+4];
    always @(posedge wclk) begin
        if (wrst) begin w_v <= 1'b0; end
        else begin
            k <= k + 1;
            w_v <= ((k % 33) != 32);
            w_d <= 64'h0707070707070707; w_c <= 8'hFF;
            if ((k % 200) == 100) begin w_d <= {32'd0, 24'(nf), 8'hFB}; w_c <= 8'h01; w_v <= 1'b1; tw[nf] = $realtime; end    // the tagged start block (lane 0)
            else if ((k % 200) > 100 && (k % 200) < 109) begin w_d <= 64'h1122334455667788; w_c <= 8'h00; w_v <= 1'b1; end   // data
            else if ((k % 200) == 109) begin w_d <= 64'h00000000000000FD; w_c <= 8'hFF; w_v <= 1'b1; end                         // terminate-like block
            if ((k % 200) == 100) nf <= nf + 1;
        end
    end
    // read side
    int unsigned nr = 0; real sum = 0.0, mn = 1e9, mx = 0.0;
    always @(posedge rclk) begin
        if (r_v && r_c == 8'h01 && r_d[7:0] == 8'hFB) begin
            real lat;
            lat = ($realtime - T) - tw[r_d[31:8]];     // ns (the timescale is 1 ns): tw is the write clock's edge that loads the block into the PCS output register (as the bench's x_price), the output register loaded the edge before this one (as y_price)
            if (nr >= 2) begin sum += lat; if (lat < mn) mn = lat; if (lat > mx) mx = lat; end
            if (nr >= 2) $display("LAT %0d %0d %0.3f", PH_PS, nr, lat);
            nr <= nr + 1;
            if (nr == FRAMES - 1) begin
                $display("SUMMARY phase_ps %0d frames %0d mean_ns %0.3f min_ns %0.3f max_ns %0.3f mean_clocks %0.2f min_clocks %0.2f max_clocks %0.2f fill_min %0d fill_max %0d ins %0d del %0d", PH_PS, nr - 1,
                         sum / (nr - 1), mn, mx, sum / (nr - 1) / T, mn / T, mx / T, fill_min, fill_max, n_ins, n_del);
                $finish;
            end
        end
    end
    initial begin
        repeat (30) @(posedge wclk); wrst = 1'b0; w_lock = 1'b1;
        repeat (10) @(posedge rclk); rrst = 1'b0;
    end
    initial begin #2000000; $display("TIMEOUT frames %0d", nr); $finish; end
endmodule
