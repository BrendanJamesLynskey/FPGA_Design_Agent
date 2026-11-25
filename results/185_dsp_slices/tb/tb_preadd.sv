// tb_preadd (brief 185): random operands against dsp_preadd; prints the latency at which p matches. (latency = register stages from the inputs to the output; the bench samples at the falling edge, so it adds 1 to the offset it finds)
module tb_preadd;
    parameter int WA = 24, WB = 18, VAR = 0, N = 2000;
    logic clk = 0;
    logic signed [WA-1:0] a, d;
    logic signed [WB-1:0] b;
    logic signed [WA+WB:0] p;
    dsp_preadd #(.WA(WA), .WB(WB), .VAR(VAR)) dut (.clk(clk), .a(a), .d(d), .b(b), .p(p));
    always #5 clk = ~clk;
    logic signed [WA+WB:0] exp_h [0:N+20], got_h [0:N+20];
    integer t, lat, bad [0:15], k;
    initial begin
        for (k = 0; k < 16; k++) bad[k] = 0;
        for (t = 0; t < N + 12; t++) begin
            if (t < N) begin
                a = $urandom; d = $urandom; b = $urandom;
                exp_h[t] = ($signed({a[WA-1], a}) + $signed({d[WA-1], d})) * $signed(b);
            end
            @(negedge clk);
            got_h[t] = p;
        end
        for (lat = 0; lat < 12; lat++)
            for (t = 20; t < N; t++) if (got_h[t + lat] !== exp_h[t]) bad[lat]++;
        for (lat = 0; lat < 12; lat++) if (bad[lat] == 0) $display("MATCH WA=%0d WB=%0d VAR=%0d latency=%0d", WA, WB, VAR, lat + 1);
        $finish;
    end
endmodule
