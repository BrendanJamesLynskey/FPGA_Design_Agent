// Change-request test (brief 174 pilot): lat_hist's `lost` counter stops at 0xFFFFFFFF instead of wrapping to 0.
// The counter is loaded to 0xFFFFFFFE with a hierarchical deposit, then four samples arrive in consecutive clocks: two are counted
// and two are lost. Wrapping gives 0x00000000, saturating gives 0xFFFFFFFF; the last line says which.
module lat_hist_lost_tb;
    logic clk = 0, rst = 1, clear = 0, s_v = 0;
    logic [31:0] s_val = 0, h_q, count, vmin, vmax, lost;
    logic [47:0] sum;
    logic [7:0]  h_bin = 0;
    logic        busy;
    lat_hist #(.NB(256), .SHIFT(0)) dut (.clk, .rst, .clear, .s_v, .s_val, .h_bin, .h_q, .count, .sum, .vmin, .vmax, .lost, .busy);
    always #4 clk = ~clk;
    initial begin
        repeat (4) @(posedge clk);
        rst <= 0;
        wait (!busy);
        @(posedge clk);
        dut.lost = 32'hFFFF_FFFE;                // deposit
        repeat (4) begin                           // four samples in consecutive clocks
            s_v <= 1; s_val <= 32'd5; @(posedge clk);
        end
        s_v <= 0;
        repeat (4) @(posedge clk);
        $display("lost=%h count=%0d", lost, count);
        if (lost == 32'hFFFF_FFFF) $display("RESULT saturated");
        else if (lost == 32'h0) $display("RESULT wrapped");
        else $display("RESULT other");
        $finish;
    end
endmodule
