// tb_wide_mul (brief 185): random operands every clock against dsp_wide_mul; prints the latency at which the product matches (clocks from a, b to p). (latency = register stages from the inputs to the output; the bench samples at the falling edge, so it adds 1 to the offset it finds)
// iverilog -g2012 -P tb_wide_mul.WA=32 -P tb_wide_mul.WB=32 -P tb_wide_mul.STYLE=1 -P tb_wide_mul.LB=24 -o t tb_wide_mul.sv ../rtl/dsp_mul_pipe.sv ../rtl/dsp_wide_mul.sv
module tb_wide_mul;
    parameter int WA = 32, WB = 32, STYLE = 0, NA = 1, LB = 24, N = 3000;
    logic clk = 0;
    logic signed [WA-1:0] a;
    logic signed [WB-1:0] b;
    logic signed [WA+WB-1:0] p;
    dsp_wide_mul #(.WA(WA), .WB(WB), .STYLE(STYLE), .NA(NA), .LB(LB)) dut (.clk(clk), .a(a), .b(b), .p(p));
    always #5 clk = ~clk;
    logic signed [WA+WB-1:0] exp_h [0:N+20];
    logic signed [WA+WB-1:0] got_h [0:N+20];
    integer t, lat, bad [0:15], k;
    initial begin
        for (k = 0; k < 16; k++) bad[k] = 0;
        for (t = 0; t < N + 16; t++) begin
            if (t < N) begin
                a = $urandom; b = $urandom;
                if (t % 7 == 0) a = {1'b1, {(WA-1){1'b0}}};          // most negative
                if (t % 11 == 0) b = {1'b1, {(WB-1){1'b0}}};
                if (t % 13 == 0) begin a = {WA{1'b1}}; b = {WB{1'b1}}; end
                if (t % 17 == 0) a = {1'b0, {(WA-1){1'b1}}};
                exp_h[t] = $signed(a) * $signed(b);
            end
            @(negedge clk);
            got_h[t] = p;
        end
        for (lat = 0; lat < 16; lat++)
            for (t = 30; t < N; t++)
                if (got_h[t + lat] !== exp_h[t]) bad[lat]++;
        for (lat = 0; lat < 16; lat++) if (bad[lat] == 0) $display("MATCH WA=%0d WB=%0d STYLE=%0d NA=%0d LB=%0d latency=%0d", WA, WB, STYLE, NA, LB, lat + 1);
        $finish;
    end
endmodule
